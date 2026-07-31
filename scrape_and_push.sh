#!/bin/bash
# Runs the scraper and pushes data/wait-times.json if it changed.
# Invoked by cron every 15 minutes — see README.md section 3.
set -e
cd "$(dirname "$0")"
.venv/bin/python scrape.py >> scrape.log 2>&1
git add data/wait-times.json
git diff --staged --quiet || (git commit -m "Update ED wait times [skip ci]" -q && git push -q)
