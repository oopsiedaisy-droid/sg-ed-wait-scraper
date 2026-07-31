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
    """
    waiting = re.findall(r"(\d+)\s*patient\(s\)", text, re.I)
    hours = re.findall(r"(\d+)\s*hour\(s\)", text, re.I)

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
    except (ValueError, IndexError):
        out = {"status": "error", "reason": "parse failure"}
    return out


def parse_simple_queue(text: str) -> dict:
    """
    Shared parser for TTSH / Woodlands / KTPH widgets, all of which render
    a "<n> Patients" / "<n> min" pair somewhere on the page.
    """
    patients = re.search(r"(\d+)\s*Patients?", text, re.I)
    minutes = re.search(r"(\d+)\s*min", text, re.I)
    if patients and minutes:
        return {"status": "ok", "waiting": int(patients.group(1)), "doctor_min": int(minutes.group(1))}
    return {"status": "error", "reason": "pattern not found", "raw_excerpt": text[:400]}


def parse_skh(text: str) -> dict:
    """
    Parser for the SKH Plumber Tile, a data-grid widget. Its row renders as
    plain numbers with no unit words attached — "<patients> <consult_min>
    <bed_hr>" — immediately followed by the grid's own "<n> row(s)" footer
    text, e.g. "...pm 36 122 18 1 row". That footer is what anchors the
    match: the three numbers right before it are the data.
    """
    m = re.search(r"(\d+)\s+(\d+)\s+(\d+)\s+\d+\s*rows?\b", text, re.I)
    if m:
        return {
            "status": "ok",
            "waiting": int(m.group(1)),
            "doctor_min": int(m.group(2)),
            "bed_hr": int(m.group(3)),
        }
    return {"status": "error", "reason": "pattern not found — inspect with --debug", "raw_excerpt": text[:400]}


def fetch_text(page, url: str, wait_ms: int = 4000) -> str:
    page.goto(url, timeout=30000, wait_until="networkidle")
    page.wait_for_timeout(wait_ms)  # let client-side hydration finish
    body_text = page.inner_text("body")
    return clean_text(body_text)


def main():
    debug = "--debug" in sys.argv
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
