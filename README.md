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
   `generated_at` timestamp and each source shows `"status": "ok"`.
4. Copy your repo's raw file URL. It looks like:
   ```
   https://raw.githubusercontent.com/<your-username>/<your-repo>/main/data/wait-times.json
   ```
5. Open `sg-ed-wait-times.html` and paste that URL into the `DATA_URL`
   constant near the top of the `<script>` block at the bottom of the
   file. Reopen the dashboard — it will now pull live numbers from your
   repo, refreshed automatically every 30 minutes by the workflow, and
   re-polled by the page itself on the same cadence.

`raw.githubusercontent.com` sends permissive CORS headers by default, so
the dashboard's browser-side `fetch()` to it will succeed where a direct
fetch to a hospital's own domain would not.

## 2. About the SKH parser

The SKH tracker lives on `plumber.gov.sg`, a JS-rendered single-page app
that wasn't reachable for inspection while this script was written (it
sits outside the domains this environment could browse). `parse_skh()` in
`scrape.py` uses the same generic "`<n> patient`" / "`<n> min`" / "`<n>
hour`" pattern-matching used for the other hospitals, which is a
reasonable first guess but may not match the tile's actual field labels.

To fix it if the first run comes back `"status": "error"` for `skh`:

```bash
pip install -r requirements.txt
playwright install chromium
python scrape.py --debug
```

The `--debug` flag prints the first 800 characters of scraped text for
every source, including SKH, straight to your terminal. Read what it
actually says, then adjust the regex in `parse_skh()` to match — most
likely just the label wording needs a tweak, not the general approach.
Commit the fix and the next scheduled run will pick it up.

## 3. Running it yourself instead of GitHub Actions

Any machine with internet access and a 30-minute cron entry works just as
well — a home server, a Raspberry Pi, a free-tier VM, etc:

```cron
*/30 * * * * cd /path/to/scraper && /usr/bin/python3 scrape.py
```

Then serve `data/wait-times.json` however you like (a simple `python -m
http.server`, a static host, S3 with public read, etc.) and point
`DATA_URL` at that instead of a GitHub raw URL.

## 4. Files

| File | Purpose |
|---|---|
| `scrape.py` | The scraper itself |
| `requirements.txt` | Python deps (just Playwright) |
| `data/wait-times.json` | Output — seeded with a snapshot so the dashboard has something to show before the first run |
| `.github/workflows/scrape.yml` | Cron schedule (every 30 min) + commit-back step |

## 5. A caveat worth knowing

GitHub Actions' free-tier scheduled workflows are **not guaranteed to run
exactly every 30 minutes** — GitHub explicitly reserves the right to delay
scheduled runs during high load, sometimes by several minutes to over an
hour. For a personal dashboard this is a non-issue; for anything
safety-critical, self-hosting the cron job (option 3 above) gives you a
harder guarantee.
