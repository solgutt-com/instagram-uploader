#!/bin/bash
# Runs automatically (via the folder watcher) whenever queue/ changes, and
# every 15 minutes as a backup. Prepares new photos, writes their captions,
# and keeps the folder in sync with GitHub in both directions.
set -u
# Always exit 0: the helper app shows an (invisible) error dialog on any other
# exit code and then stays stuck open, which silently stops the watcher.
# Problems are written to logs/watcher.log instead.
trap 'exit 0' EXIT
cd "$(dirname "$0")/.." || exit 0
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
PYTHON="${PYTHON:-python3}"

mkdir -p logs
exec >>logs/watcher.log 2>&1

# one run at a time
if ! mkdir .sync.lock 2>/dev/null; then
  # stale lock (older than 10 min)? take it over
  if [ -n "$(find .sync.lock -maxdepth 0 -mmin +10 2>/dev/null)" ]; then rm -rf .sync.lock; mkdir .sync.lock; else exit 0; fi
fi
trap 'rm -rf .sync.lock; exit 0' EXIT

# Rebuild preview.html and warn (once a day) when the queue is running low.
update_preview() {
  status=$("$PYTHON" scripts/preview.py 2>>logs/watcher.log) || return
  if echo "$status" | grep -q '"low": true'; then
    today=$(date +%F)
    if [ "$(cat .low_warned 2>/dev/null)" != "$today" ]; then
      left=$(echo "$status" | sed -E 's/.*"posts_left": ([0-9]+).*/\1/')
      osascript -e "display notification \"Only $left post(s) left – drop more photos into queue/\" with title \"Instagram queue running low\"" 2>/dev/null
      echo "$today" > .low_warned
      echo "[$(date '+%F %T')] low-queue warning: $left post(s) left"
    fi
  fi
}

# prepare.py exits 3 while files are still being copied in – wait and retry
for _ in 1 2 3 4 5 6 7 8 9 10; do
  "$PYTHON" scripts/prepare.py
  [ $? -eq 3 ] || break
  sleep 10
done

if [ -n "$(git status --porcelain -- queue)" ]; then
  git add -A queue
  # The repo is public: never upload a file prepare.py hasn't stripped of its
  # metadata (a HEIC or RAW file, a failed photo, one still copying in).
  "$PYTHON" scripts/prepare.py --unprepared | while IFS= read -r f; do
    git reset -q -- "$f"
    echo "[$(date '+%F %T')] not uploaded, not a prepared photo: $f"
  done
  if ! git diff --cached --quiet -- queue; then
    new=$(git diff --cached --name-only -- queue | grep -ci '\.jpg"\?$')
    if [ "$new" -gt 0 ]; then msg="Queue: $new photo(s) added/changed"; else msg="Queue: captions edited"; fi
    git commit -q -m "$msg" && echo "[$(date '+%F %T')] committed: $msg"
  fi
fi

if git remote get-url origin >/dev/null 2>&1; then
  if ! git pull -q --rebase --autostash; then
    git rebase --abort 2>/dev/null
    echo "[$(date '+%F %T')] ERROR: couldn't merge changes from GitHub – needs a look"
    osascript -e 'display notification "Couldn'\''t sync with GitHub – check logs/watcher.log" with title "Instagram uploader"' 2>/dev/null
    update_preview
    exit 1
  fi
  git push -q 2>/dev/null || git push -q -u origin main || echo "[$(date '+%F %T')] ERROR: push failed"

  # Backup trigger for GitHub's unreliable hourly timer: if a posting time has
  # passed and the photo hasn't gone out, start the posting workflow now.
  # Started once per slot; GitHub's hourly schedule retries after that.
  if slot=$("$PYTHON" scripts/post.py --due 2>/dev/null); then
    last=$(cat .last_trigger 2>/dev/null)
    if [ "$last" != "$slot" ]; then
      if gh workflow run post.yml -f dry_run=false >/dev/null 2>&1; then
        echo "$slot" > .last_trigger
        echo "[$(date '+%F %T')] started posting workflow for $slot"
      else
        echo "[$(date '+%F %T')] ERROR: couldn't start the posting workflow (gh)"
      fi
    fi
  fi
fi

update_preview
