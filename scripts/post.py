#!/usr/bin/env python3
"""Post the next photo in queue/ to Instagram, when a posting time is due.

Runs on GitHub Actions every hour. Uses only the Python standard library.

A "slot" is one of config.json's post_times on today's date. If a slot has
passed and hasn't been used yet, the first photo in queue/ (alphabetical
order) is posted with its .txt as the caption, then moved to posted/.
At most one photo is posted per run, so a missed slot never causes a burst.

Environment:
  IG_ACCESS_TOKEN   Instagram API token (GitHub secret). Either an "IG…" token
                    (Instagram login) or a Meta system-user token (Unified login).
  IG_USER_ID        Instagram account ID – only needed with a system-user token,
                    and only if it can't be found automatically.
  FORCE=true        post now even if no slot is due
  DRY_RUN=true      do everything except actually publishing
"""
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
QUEUE, POSTED = ROOT / "queue", ROOT / "posted"
STATE_FILE = ROOT / "state.json"
CONFIG = json.loads((ROOT / "config.json").read_text())
VERSION = CONFIG.get("graph_api_version", "v24.0")

FORCE = os.environ.get("FORCE", "").lower() == "true"
DRY_RUN = os.environ.get("DRY_RUN", "").lower() == "true"


def die(msg):
    print(f"::error::{msg}")
    sys.exit(1)


def instagram_login_token():
    return os.environ.get("IG_ACCESS_TOKEN", "").startswith("IG")


def api(method, path, quiet=False, **params):
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    data = urllib.parse.urlencode(params).encode()
    host = "graph.instagram.com" if instagram_login_token() else "graph.facebook.com"
    url = f"https://{host}/{VERSION}/{path}"
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if quiet:
            return None
        die(f"Instagram API {method} {path} failed ({e.code}): {e.read().decode(errors='replace')}")


def find_account():
    """Return (instagram account id, username) for the token."""
    if instagram_login_token():
        me = api("GET", "me", fields="user_id,username")
        return me["user_id"], me.get("username")
    uid = os.environ.get("IG_USER_ID", "").strip()
    if not uid:
        # system-user / Facebook-login token: look for the Instagram account it can manage
        found = []
        for edge in ("me/accounts", "me/assigned_pages"):
            res = api("GET", edge, quiet=True, fields="instagram_business_account{id,username}") or {}
            found += [p["instagram_business_account"] for p in res.get("data", [])
                      if "instagram_business_account" in p]
        found = list({a["id"]: a for a in found}.values())
        if len(found) != 1:
            die("Couldn't work out which Instagram account to post to. Add your Instagram "
                "account ID as a repository secret named IG_USER_ID (see SETUP.md).")
        return found[0]["id"], found[0].get("username")
    info = api("GET", uid, fields="username")
    return uid, info.get("username")


def due_slot(now, state):
    """Latest of today's posting times that has passed and hasn't been used."""
    last = state.get("last_slot")
    last = datetime.fromisoformat(last) if last else None
    due = []
    for t in CONFIG["post_times"]:
        hh, mm = (int(x) for x in t.split(":"))
        slot = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if slot <= now and (last is None or slot > last):
            due.append(slot)
    return max(due) if due else None


def check_public(url):
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            kind = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        die(f"Photo isn't publicly reachable ({e.code}): {url}  – is the repository public?")
    if "image" not in kind:
        die(f"Photo URL returned {kind!r} instead of an image: {url}")


def main():
    tz = ZoneInfo(CONFIG["timezone"])
    now = datetime.now(tz)
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

    slot = due_slot(now, state)
    if not slot and not FORCE:
        print(f"{now:%H:%M} – nothing due (times: {', '.join(CONFIG['post_times'])}).")
        return

    photos = sorted(p for p in QUEUE.iterdir() if p.suffix.lower() in (".jpg", ".jpeg"))
    if not photos:
        print("Queue is empty – nothing to post.")
        return
    photo = photos[0]
    txt = photo.with_suffix(".txt")
    caption = txt.read_text(encoding="utf-8").strip() if txt.exists() else ""
    if len(caption) > 2200:
        die(f"{txt.name} is {len(caption)} characters; Instagram allows 2,200.")

    repo, sha = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"]
    url = (f"https://raw.githubusercontent.com/{repo}/{sha}/"
           f"{urllib.parse.quote(photo.relative_to(ROOT).as_posix())}")
    print(f"Posting {photo.name}  ({len(photos) - 1} left after this)")
    print(f"Image: {url}\nCaption:\n{caption}\n")
    check_public(url)

    if not os.environ.get("IG_ACCESS_TOKEN"):
        # Not set up yet: warn instead of failing, so GitHub doesn't email a failure every hour.
        print("::warning::IG_ACCESS_TOKEN secret isn't set yet – nothing posted. See SETUP.md.")
        return
    user_id, username = find_account()
    print(f"Token OK – connected to @{username} (account {user_id})")

    if DRY_RUN:
        print("DRY RUN – stopping before publishing. Nothing was posted or moved.")
        return

    container = api("POST", f"{user_id}/media", image_url=url, caption=caption)["id"]

    for _ in range(30):
        status = api("GET", container, fields="status_code").get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            die(f"Instagram couldn't process {photo.name} (status {status}).")
        time.sleep(4)
    else:
        die("Instagram took too long to process the photo.")

    media_id = api("POST", f"{user_id}/media_publish", creation_id=container)["id"]
    permalink = api("GET", media_id, fields="permalink").get("permalink", "")
    print(f"Posted: {permalink}")

    POSTED.mkdir(exist_ok=True)
    photo.rename(POSTED / photo.name)
    if txt.exists():
        txt.rename(POSTED / txt.name)

    log = POSTED / "log.csv"
    new = not log.exists()
    with log.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["posted_at", "file", "media_id", "permalink"])
        w.writerow([now.isoformat(timespec="minutes"), photo.name, media_id, permalink])

    if slot:
        state["last_slot"] = slot.isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


if __name__ == "__main__":
    main()
