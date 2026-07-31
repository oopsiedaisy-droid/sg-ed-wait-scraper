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
   repo, refreshed automatically every 15 minutes by the workflow, and
   re-polled by the page itself on the same cadence.

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

## 3. Current setup: local cron, not the GitHub Actions schedule

Because of the IP-blocking above, this deployment's `schedule:` trigger in
`.github/workflows/scrape.yml` is **paused** (left as `workflow_dispatch`
only, for manual/backup runs). A cron job on a local machine with a normal
residential IP runs instead:

```cron
*/15 * * * * cd /path/to/scraper && .venv/bin/python scrape.py && git add data/wait-times.json && git diff --staged --quiet || (git commit -m "Update ED wait times [skip ci]" && git push)
```

This pushes straight to the same repo GitHub Actions would have, so
`DATA_URL` doesn't need to change. Don't run both the local cron and the
GitHub Actions schedule at once — they'd race to commit/push the same
file.

If you'd rather not rely on a machine staying awake (laptops sleep;
cron/launchd don't fire while asleep), any always-on box works the same
way — a home server, a Raspberry Pi, a free-tier VM, etc. You can also
serve `data/wait-times.json` from somewhere other than a git push (a
simple `python -m http.server`, a static host, S3 with public read) and
point `DATA_URL` there instead.

## 4. Files

| File | Purpose |
|---|---|
| `scrape.py` | The scraper itself |
| `requirements.txt` | Python deps (just Playwright) |
| `data/wait-times.json` | Output — seeded with a snapshot so the dashboard has something to show before the first run |
| `.github/workflows/scrape.yml` | Manual-dispatch workflow (scheduled runs paused — see §3) |

## 5. A caveat worth knowing

GitHub Actions' free-tier scheduled workflows are **not guaranteed to run
exactly every 15 minutes** — GitHub explicitly reserves the right to delay
scheduled runs during high load, sometimes by several minutes to over an
hour. Moot while running via local cron (§3), but worth knowing if you
ever switch back to the GitHub-hosted schedule.
