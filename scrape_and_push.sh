#!/bin/bash
# Runs the scraper and pushes data/wait-times.json if it changed.
# Invoked by cron at :01 and :31 past every hour — see README.md section 3.
# GitHub Actions runs on the same schedule (it only reliably gets NUHS —
# see scrape.py's merge logic and the workflow's own comments), so this
# script retries through push conflicts the same way that workflow does.
set -e
cd "$(dirname "$0")"

.venv/bin/python scrape.py >> scrape.log 2>&1

git add data/wait-times.json
if git diff --staged --quiet; then
  exit 0
fi
git commit -m "Update ED wait times [skip ci]" -q

for i in 1 2 3; do
  if git push -q; then
    exit 0
  fi
  git fetch -q origin main
  if ! git rebase -q origin/main; then
    git rebase --abort
    echo "$(date): rebase conflict, giving up this run" >> scrape.log
    exit 1
  fi
  sleep $((RANDOM % 10 + 1))
done
echo "$(date): push failed after retries" >> scrape.log
exit 1
