#!/bin/bash
# Installs a background job (macOS launchd) that runs sync.sh whenever
# something changes in queue/, plus every 15 minutes. Run once.
# Remove it again with:  scripts/install-watcher.sh --uninstall
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.solgutt.instagram-uploader"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ "${1:-}" = "--uninstall" ]; then rm -f "$PLIST"; echo "Watcher removed."; exit 0; fi

# find a python that has Pillow
PY=""
for p in /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 \
         /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3 || true)"; do
  if [ -x "$p" ] && "$p" -c "import PIL" 2>/dev/null; then PY="$p"; break; fi
done
if [ -z "$PY" ]; then
  echo "No Python with Pillow found. Install it with:  python3 -m pip install --user Pillow"; exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$REPO/scripts/sync.sh</string></array>
  <key>EnvironmentVariables</key>
  <dict><key>PYTHON</key><string>$PY</string></dict>
  <key>WatchPaths</key>
  <array><string>$REPO/queue</string></array>
  <key>StartInterval</key><integer>900</integer>
  <key>RunAtLoad</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
</dict>
</plist>
EOF
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Watcher installed (using $PY). Drop photos into: $REPO/queue"
