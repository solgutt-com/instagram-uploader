#!/bin/bash
# Installs a background job (macOS launchd) that runs sync.sh whenever
# something changes in queue/, plus every 15 minutes. Run once.
# Remove it again with:  scripts/install-watcher.sh --uninstall
#
# macOS blocks background jobs from reading the Desktop folder, so the job
# runs through a tiny helper app, "Instagram Uploader.app". The first time it
# runs, macOS asks whether it may access your Desktop folder: click Allow.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.solgutt.instagram-uploader"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
APPDIR="$HOME/Library/Application Support/instagram-uploader"
APP="$APPDIR/Instagram Uploader.app"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ "${1:-}" = "--uninstall" ]; then
  rm -f "$PLIST"; rm -rf "$APPDIR"; echo "Watcher removed."; exit 0
fi

# find a python that has Pillow
PY=""
for p in /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 \
         /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3 || true)"; do
  if [ -x "$p" ] && "$p" -c "import PIL" 2>/dev/null; then PY="$p"; break; fi
done
if [ -z "$PY" ]; then
  echo "No Python with Pillow found. Install it with:  python3 -m pip install --user Pillow"; exit 1
fi

# helper app: runs sync.sh, has no Dock icon
mkdir -p "$APPDIR"
rm -rf "$APP"
osacompile -o "$APP" \
  -e "do shell script \"PYTHON=\" & quoted form of \"$PY\" & \" /bin/bash \" & quoted form of \"$REPO/scripts/sync.sh\""
INFO="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Delete :CFBundleIdentifier" "$INFO" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string $LABEL" "$INFO"
/usr/libexec/PlistBuddy -c "Delete :LSUIElement" "$INFO" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$INFO"
codesign --force --deep --sign - "$APP" 2>/dev/null

mkdir -p "$HOME/Library/LaunchAgents"
cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/usr/bin/open</string><string>-g</string><string>-j</string><string>-a</string><string>$APP</string></array>
  <key>WatchPaths</key>
  <array><string>$REPO/queue</string></array>
  <key>StartInterval</key><integer>900</integer>
  <key>RunAtLoad</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
</dict>
</plist>
EOF
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Watcher installed (using $PY)."
echo "If macOS asks whether \"Instagram Uploader\" may access your Desktop folder, click Allow."
echo "Drop photos into: $REPO/queue"
