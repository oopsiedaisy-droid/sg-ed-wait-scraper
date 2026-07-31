# SG ED Wait Time Scraper

Server-side scraper for the A&E Wait Board dashboard. Runs Playwright
(headless Chromium) against each hospital's page, extracts the wait-time
numbers with regex, and writes `data/wait-times.json`. Because the fetch
happens on a server instead of in the visitor's browser, hospital sites'
CORS restrictions never come into play — that's the whole point of moving
this server-side.

## 1. One-time setup (~5 minutes)

1. Create a new **public** GitHub repo (private also works, but then the
   raw JSON URL needs a token, which is more setup than it's worth here)
   and push this `scraper/` folder's contents to it.
2. GitHub Actions is enabled by default on new repos. Go to the **Actions**
   tab once to confirm it's on, and click **"Run workflow"** on
   *Scrape ED wait times* to trigger a first run manually rather than
   waiting for the schedule.
3. After it runs (~1–2 minutes, mostly spent installing the headless
   browser), check that `data/wait-times.json` was updated with a recent
   `generated_at` timestamp. Note: a run triggered from GitHub's own
   servers will likely only show `"status": "ok"` for `nuhs` — see §2 and
   §3 for why, and how this deployment actually gets full coverage.
4. Copy your repo's raw file URL. It looks like:
   ```
   https://raw.githubusercontent.com/<your-username>/<your-repo>/main/data/wait-times.json
   ```
5. Open `sg-ed-wait-times.html` and paste that URL into the `DATA_URL`
   constant near the top of the `<script>` block at the bottom of the
   file. Reopen the dashboard — it will now pull live numbers from your
   repo, refreshed automatically at :01 and :31 past every hour, and
   re-polled by the page itself on the same schedule.

`raw.githubusercontent.com` sends permissive CORS headers by default, so
the dashboard's browser-side `fetch()` to it will succeed where a direct
fetch to a hospital's own domain would not.

## 2. Why GitHub Actions alone isn't enough here

`parse_skh()` was originally a best-effort guess (the tile lives on
`plumber.gov.sg`, a JS SPA that wasn't reachable for inspection while this
script was written) — that's now fixed; it correctly reads the grid's
`<patients> <consult_min> <bed_hr>` row anchored on the "`<n> row(s)`"
footer text.

The remaining issue isn't the parsing logic — it's *where the scrape runs
from*. GitHub Actions' runners come from a shared datacenter IP range, and
both `nhghealth.com.sg` (TTSH/Woodlands/KTPH) and `plumber.gov.sg` (SKH)
serve a bot-verification challenge page (Vercel Security Checkpoint /
Cloudflare) to that range instead of the real content. Only NUHS comes
back `"status": "ok"` from a GitHub-hosted run. The same code run from an
ordinary residential IP gets all five sources fine — verified by running
`scrape.py --debug` locally.

If you ever see a source you don't expect fail, `python scrape.py --debug`
prints the first 800 characters of scraped text for every source so you
can see what the site actually returned (a real markup change vs. a bot
challenge page look very different).

## 3. Current setup: both GitHub Actions *and* local cron, merged

Two schedulers write to the same `data/wait-times.json`, both on `1,31 * *
* *` (:01 and :31 past every hour):

- **GitHub Actions** (`.github/workflows/scrape.yml`) — always on, no
  machine required, but only reliably gets `nuhs` (see §2).
- **Local cron**, via `scrape_and_push.sh`, on this machine:
  ```cron
  1,31 * * * * /path/to/scraper/scrape_and_push.sh
  ```
  Gets all five sources (ordinary residential IP), but only while the
  machine is on — cron/launchd don't fire while asleep or powered off.

Running both isn't a conflict: `scrape.py` loads the *previous*
`data/wait-times.json` before writing, and only overwrites a source when
today's scrape actually returned `"status": "ok"` — otherwise it keeps
whatever the last successful scrape (from either scheduler) captured. So
even with the laptop off, the GitHub Actions run keeps NUHS current; the
other four sources simply hold their last-known-good value (dashboard
badge shows "cached", not broken) until local cron next runs. Both
scripts also retry through push races (`git fetch` + `rebase`, a few
times with jitter) since two schedulers on the same minute will sometimes
both have something to push.

If you'd rather have full five-source coverage with no dependency on this
machine at all, point the local-cron half at an always-on box instead — a
home server, a Raspberry Pi, a free-tier VM, etc. — running the same
`scrape_and_push.sh`.

## 4. Files

| File | Purpose |
|---|---|
| `scrape.py` | The scraper itself; merges with the previous output (see §3) |
| `scrape_and_push.sh` | Wrapper the local cron job calls: run scraper, commit + push if changed, retry through push races |
| `.venv/` | Local-only virtualenv (gitignored) — the pinned `requirements.txt` version doesn't ship a wheel for this machine's Python, so this venv uses an unpinned Playwright install instead |
| `requirements.txt` | Python deps for the GitHub Actions runner (pinned Playwright version) |
| `data/wait-times.json` | Output — seeded with a snapshot so the dashboard has something to show before the first run |
| `.github/workflows/scrape.yml` | Scheduled + manual-dispatch workflow, same :01/:31 cadence as local cron |

## 5. Cluster-level "origin last updated"

Each hospital page states its own refresh time (e.g. TTSH: "Last updated
at 31/07/2026 18:30:04"). `scrape.py` captures that raw string per source
as `origin_updated`. The dashboard shows it once per **cluster** rather
than per hospital: NUHS's four hospitals share one page (one stamp
already); NHG's three hospitals were observed sharing one backend refresh
clock (identical timestamps across TTSH/Woodlands/KTPH), so the dashboard
just uses whichever of the three parsed; SingHealth shows SKH's row
timestamp. This is the hospital's own stated freshness, which can differ
from `fetched_at` (when our scraper actually ran).

## 6. A caveat worth knowing

GitHub Actions' free-tier scheduled workflows are **not guaranteed to run
exactly on time** — GitHub explicitly reserves the right to delay
scheduled runs during high load, sometimes by several minutes to over an
hour. The local cron job isn't subject to that, which is part of why §3
runs both.
