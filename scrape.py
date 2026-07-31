#!/usr/bin/env python3
"""
sg-ed-scraper
-------------
Scrapes Singapore public hospital Emergency Department wait-time pages
server-side (so browser CORS restrictions never come into play) and writes
a single data/wait-times.json file.

Run manually:
    pip install -r requirements.txt
    playwright install chromium
    python scrape.py

Run on a schedule via the included GitHub Actions workflow
(.github/workflows/scrape.yml), which commits data/wait-times.json back to
the repo every 15 minutes. Point the dashboard's DATA_URL at the raw file.

Why Playwright and not plain requests:
NHG's hospital pages (TTSH / Woodlands / KTPH) and the SKH Plumber tile are
JavaScript-rendered. A plain `requests.get()` only sees the pre-hydration
HTML shell. Playwright runs a real (headless) browser so we see the same
numbers a visitor would.
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta

from playwright.sync_api import sync_playwright

SGT = timezone(timedelta(hours=8))

NUHS_URL = "https://www.nuhs.edu.sg/patient-care/emergency-department-wait-times"
TTSH_URL = "https://www.nhghealth.com.sg/ttsh/patients-visitors/emergency-medicine"
WH_URL = "https://www.nhghealth.com.sg/wh/for-patients-visitors/your-emergency-visit"
KTPH_URL = "https://www.nhghealth.com.sg/ktph"
SKH_URL = "https://plumber.gov.sg/tiles/4005364f-073d-4e59-9b9c-c237c816e873/28dba0a5-c239-49e2-b1a7-db708c4981e4"


def clean_text(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def parse_nuhs(text: str) -> dict:
    """
    NUHS publishes one page with a table for Alexandra Hospital (UCC),
    NUH Adult ED, NTFGH Adult ED, then a second table for NUH Children's ED.
    Values appear in reading order as "<n> patient(s)" and "<n> hour(s)".
    The page also states its own refresh time as "Last updated at <date>,
    <time> AM/PM" — that's the one stamp for the whole NUHS cluster.
    """
    waiting = re.findall(r"(\d+)\s*patient\(s\)", text, re.I)
    hours = re.findall(r"(\d+)\s*hour\(s\)", text, re.I)
    updated = re.search(r"Last updated at (\d{1,2} \w+ \d{4},\s*\d{1,2}:\d{2}:\d{2}\s*[AP]M)", text, re.I)

    out = {"status": "error"}
    try:
        if len(waiting) >= 4 and len(hours) >= 6:
            out = {
                "status": "ok",
                "ah": {"waiting": int(waiting[0]), "doctor_hr": int(hours[0]), "bed_hr": int(hours[3])},
                "nuh": {"waiting": int(waiting[1]), "doctor_hr": int(hours[1]), "bed_hr": int(hours[4])},
                "ntfgh": {"waiting": int(waiting[2]), "doctor_hr": int(hours[2]), "bed_hr": int(hours[5])},
            }
            if len(waiting) >= 4 and len(hours) >= 8:
                out["nuhc"] = {
                    "waiting": int(waiting[3]),
                    "doctor_hr": int(hours[6]),
                    "bed_hr": int(hours[7]),
                }
            if updated:
                out["origin_updated"] = updated.group(1)
    except (ValueError, IndexError):
        out = {"status": "error", "reason": "parse failure"}
    return out


def parse_simple_queue(text: str) -> dict:
    """
    Shared parser for TTSH / Woodlands / KTPH widgets, all of which render
    a "<n> Patients" / "<n> min" pair somewhere on the page, plus their own
    "Last updated at DD/MM/YYYY HH:MM:SS" stamp (observed synced across all
    three NHG hospitals, so any one of them stands in for the whole
    NHG cluster on the dashboard).
    """
    patients = re.search(r"(\d+)\s*Patients?", text, re.I)
    minutes = re.search(r"(\d+)\s*min", text, re.I)
    updated = re.search(r"Last updated at (\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})", text)
    if patients and minutes:
        out = {"status": "ok", "waiting": int(patients.group(1)), "doctor_min": int(minutes.group(1))}
        if updated:
            out["origin_updated"] = updated.group(1)
        return out
    return {"status": "error", "reason": "pattern not found", "raw_excerpt": text[:400]}


def parse_skh(text: str) -> dict:
    """
    Parser for the SKH Plumber Tile, a data-grid widget. Its row renders as
    a timestamp followed by plain numbers with no unit words attached —
    "<origin_updated> <patients> <consult_min> <bed_hr>" — immediately
    followed by the grid's own "<n> row(s)" footer text, e.g.
    "...31 Jul 2026 04:47 pm 36 122 18 1 row". Anchoring on both the
    timestamp shape and the footer avoids matching stray numbers elsewhere
    on the page.
    """
    m = re.search(
        r"(\d{1,2} \w{3} \d{4} \d{1,2}:\d{2}\s*[ap]m)\s+(\d+)\s+(\d+)\s+(\d+)\s+\d+\s*rows?\b",
        text,
        re.I,
    )
    if m:
        return {
            "status": "ok",
            "origin_updated": m.group(1),
            "waiting": int(m.group(2)),
            "doctor_min": int(m.group(3)),
            "bed_hr": int(m.group(4)),
        }
    return {"status": "error", "reason": "pattern not found — inspect with --debug", "raw_excerpt": text[:400]}


def fetch_text(page, url: str, wait_ms: int = 4000) -> str:
    page.goto(url, timeout=30000, wait_until="networkidle")
    page.wait_for_timeout(wait_ms)  # let client-side hydration finish
    body_text = page.inner_text("body")
    return clean_text(body_text)


def load_existing_sources(path: str) -> dict:
    """
    Best-effort read of the previous output. Two schedulers write this file
    from different networks (see README §3) — GitHub Actions gets NUHS but
    not the rest (blocked by bot-verification on its IP range), a local
    cron job gets everything. Loading the prior sources lets a run that
    fails on some site keep that site's last known-good value instead of
    stomping it with today's error.
    """
    try:
        with open(path) as f:
            return json.load(f).get("sources", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def main():
    debug = "--debug" in sys.argv
    existing_sources = load_existing_sources("data/wait-times.json")
    data = {
        "generated_at": datetime.now(SGT).isoformat(),
        "sources": {},
    }

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ))

        jobs = [
            ("nuhs", NUHS_URL, parse_nuhs),
            ("ttsh", TTSH_URL, parse_simple_queue),
            ("wh", WH_URL, parse_simple_queue),
            ("ktph", KTPH_URL, parse_simple_queue),
            ("skh", SKH_URL, parse_skh),
        ]

        for key, url, parser in jobs:
            try:
                text = fetch_text(page, url)
                if debug:
                    print(f"\n----- {key} raw text (first 800 chars) -----")
                    print(text[:800])
                parsed = parser(text)
            except Exception as exc:  # noqa: BLE001 - want to keep going on failure
                parsed = {"status": "error", "reason": str(exc)}

            previous = existing_sources.get(key)
            if parsed.get("status") == "ok":
                parsed["fetched_at"] = datetime.now(SGT).isoformat()
                parsed["source_url"] = url
                data["sources"][key] = parsed
                print(f"{key}: ok")
            elif previous and previous.get("status") == "ok":
                data["sources"][key] = previous
                print(f"{key}: {parsed.get('status')} (kept last known-good from {previous.get('fetched_at')})")
            else:
                parsed["fetched_at"] = datetime.now(SGT).isoformat()
                parsed["source_url"] = url
                data["sources"][key] = parsed
                print(f"{key}: {parsed.get('status')}")

        browser.close()

    with open("data/wait-times.json", "w") as f:
        json.dump(data, f, indent=2)

    print("\nWrote data/wait-times.json")


if __name__ == "__main__":
    main()
