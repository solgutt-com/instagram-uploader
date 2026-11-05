#!/bin/bash
# Runs automatically (via the folder watcher) whenever queue/ changes, and
# every 15 minutes as a backup. Prepares new photos, writes their captions,
# and keeps the folder in sync with GitHub in both directions.
set -u
cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
PYTHON="${PYTHON:-python3}"

mkdir -p logs
exec >>logs/watcher.log 2>&1

# one run at a time
if ! mkdir .sync.lock 2>/dev/null; then
  # stale lock (older than 10 min)? take it over
  if [ -n "$(find .sync.lock -maxdepth 0 -mmin +10 2>/dev/null)" ]; then rm -rf .sync.lock; mkdir .sync.lock; else exit 0; fi
fi
trap 'rm -rf .sync.lock' EXIT

# prepare.py exits 3 while files are still being copied in – wait and retry
for _ in 1 2 3 4 5 6 7 8 9 10; do
  "$PYTHON" scripts/prepare.py
  [ $? -eq 3 ] || break
  sleep 10
done

if [ -n "$(git status --porcelain -- queue)" ]; then
  new=$(git status --porcelain -- queue | grep -ci '\.jpg"\?$')
  git add -A queue
  if [ "$new" -gt 0 ]; then msg="Queue: $new photo(s) added/changed"; else msg="Queue: captions edited"; fi
  git commit -q -m "$msg" && echo "[$(date '+%F %T')] committed: $msg"
fi

if git remote get-url origin >/dev/null 2>&1; then
  if ! git pull -q --rebase --autostash; then
    git rebase --abort 2>/dev/null
    echo "[$(date '+%F %T')] ERROR: couldn't merge changes from GitHub – needs a look"
    osascript -e 'display notification "Couldn'\''t sync with GitHub – check logs/watcher.log" with title "Instagram uploader"' 2>/dev/null
    exit 1
  fi
  git push -q 2>/dev/null || git push -q -u origin main || echo "[$(date '+%F %T')] ERROR: push failed"
fi
