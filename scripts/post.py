#!/usr/bin/env python3
"""Post the next post in queue/ to Instagram, when a posting time is due.

Runs on GitHub Actions. Uses only the Python standard library.

A "slot" is one of config.json's post_times on today's date. If a slot has
passed and hasn't been used yet, the first post folder in queue/ (Finder
order) is posted: one photo = a single post, 2–10 photos = a carousel, with
its caption.txt plus the hashtags from config.json. The folder is then
deleted and the post recorded in posted/log.csv. At most one post per run,
so a missed slot never causes a burst.

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
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common import due_slot as _due_slot, full_caption, loose_photos, queued_posts, read_caption, slide_texts

ROOT = Path(__file__).resolve().parent.parent
QUEUE, POSTED = ROOT / "queue", ROOT / "posted"
STATE_FILE = ROOT / "state.json"
CONFIG = json.loads((ROOT / "config.json").read_text())
VERSION = CONFIG.get("graph_api_version", "v24.0")

FORCE = os.environ.get("FORCE", "").lower() == "true"
DRY_RUN = os.environ.get("DRY_RUN", "").lower() == "true"
DIAGNOSE = os.environ.get("DIAGNOSE", "").lower() == "true"


def die(msg):
    print(f"::error::{msg}")
    sys.exit(1)


def token():
    return os.environ.get("IG_ACCESS_TOKEN", "").strip().strip('"').strip("'").strip()


def instagram_login_token():
    return token().startswith("IG")


def api(method, path, quiet=False, **params):
    params["access_token"] = token()
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
            try:
                msg = json.loads(e.read()).get("error", {}).get("message", "")
            except Exception:
                msg = ""
            print(f"    ({path}: {e.code} {msg[:160]})")
            return None
        die(f"Instagram API {method} {path} failed ({e.code}): {e.read().decode(errors='replace')}")


def find_account():
    """Return (instagram account id, username) for the token."""
    if instagram_login_token():
        me = api("GET", "me", fields="user_id,username")
        return me["user_id"], me.get("username")
    want = CONFIG.get("instagram_username", "").lower().lstrip("@")
    uid = os.environ.get("IG_USER_ID", "").strip()
    if uid:
        info = api("GET", uid, fields="username")
        return uid, info.get("username")

    # System-user token: search every place Meta might list the Instagram account.
    found = {}

    def collect(label, path, fields, pick=lambda item: item):
        res = api("GET", path, quiet=True, fields=fields)
        if res is None:
            print(f"  lookup {label}: not available")
            return
        items = [pick(i) for i in res.get("data", [])]
        items = [i for i in items if i and i.get("id")]
        print(f"  lookup {label}: {len(items)} found")
        for i in items:
            found.setdefault(i["id"], i)

    ig = "instagram_business_account{id,username}"
    collect("pages", "me/accounts", ig, lambda p: p.get("instagram_business_account"))
    collect("assigned pages", "me/assigned_pages", ig, lambda p: p.get("instagram_business_account"))
    businesses = [CONFIG["meta_business_id"]] if CONFIG.get("meta_business_id") else []
    res = api("GET", "me/businesses", quiet=True, fields="id") or {}
    businesses += [b["id"] for b in res.get("data", []) if b["id"] not in businesses]
    for biz in businesses:
        for edge in ("instagram_business_accounts", "owned_instagram_accounts", "instagram_accounts"):
            collect(f"business {edge}", f"{biz}/{edge}", "id,username")

    # keep only IDs that work as Instagram accounts we can publish to
    usable = []
    for i in found.values():
        info = api("GET", i["id"], quiet=True, fields="id,username")
        if info and info.get("username"):
            usable.append(info)
    print("  usable accounts: " + (", ".join(f"@{a['username']} ({a['id']})" for a in usable) or "none"))
    if want:
        usable = [a for a in usable if a["username"].lower() == want]
    if len(usable) != 1:
        die("Couldn't work out which Instagram account to post to. Add your Instagram "
            "account ID as a repository secret named IG_USER_ID (see SETUP.md).")
    return usable[0]["id"], usable[0]["username"]


def due_slot(now, state):
    return _due_slot(now, state, CONFIG)


def check_public(url):
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            kind = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        die(f"Photo isn't publicly reachable ({e.code}): {url}  – is the repository public?")
    if "image" not in kind:
        die(f"Photo URL returned {kind!r} instead of an image: {url}")


def raw_call(path, version=None, **params):
    """GET without dying; returns (status, short text) for the diagnostics."""
    params["access_token"] = token()
    host = "graph.instagram.com" if instagram_login_token() else "graph.facebook.com"
    url = f"https://{host}/{version or VERSION}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, r.read().decode()[:300]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:400]


def diagnose():
    t = token()
    print(f"Token: {len(t)} characters, starts with {t[:3]!r}; API {VERSION}")
    uid = os.environ.get("IG_USER_ID", "").strip()
    checks = [
        ("who the token belongs to", "me", {"fields": "id,name"}),
        ("token permissions", "me/permissions", {}),
        ("the app", "app", {"fields": "id,name"}),
        ("the Instagram account", uid or "IG_USER_ID-missing", {"fields": "id,username"}),
        ("Instagram publishing limit", f"{uid}/content_publishing_limit", {"fields": "quota_usage,config"}),
    ]
    for label, path, params in checks:
        status, body = raw_call(path, **params)
        body = body.replace(uid, "<ig-id>") if uid else body
        print(f"\n[{'OK ' if status == 200 else 'BLOCKED' if 'blocked' in body.lower() else 'ERR'}] {label} ({status})\n    {body}")
    # also try the newest API version, in case only this version is affected
    status, body = raw_call("me", version="v25.0", fields="id")
    print(f"\n[{'OK ' if status == 200 else 'ERR'}] same check on v25.0 ({status})\n    {body}")


def main():
    if DIAGNOSE:
        return diagnose()
    tz = ZoneInfo(CONFIG["timezone"])
    now = datetime.now(tz)
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

    slot = due_slot(now, state)
    posts = queued_posts(QUEUE)
    if "--due" in sys.argv:
        # used by the Mac watcher: print the due slot if a post should go out now
        if slot and posts:
            print(slot.isoformat())
            return
        sys.exit(1)

    if not slot and not FORCE:
        print(f"{now:%H:%M} – nothing due (times: {', '.join(CONFIG['post_times'])}).")
        return

    if not posts:
        waiting = len(loose_photos(QUEUE))
        print("::warning::Queue is empty – nothing to post."
              + (f" {waiting} photo(s) are waiting for a full post." if waiting else ""))
        return
    folder, images = posts[0]
    if len(images) > 10:
        die(f"'{folder.name}' has {len(images)} photos; a carousel can have at most 10.")
    texts = slide_texts(images) if len(images) > 1 else []
    caption = full_caption(read_caption(folder), CONFIG, texts)
    use_alt = CONFIG.get("slide_text", "caption_and_alt") in ("caption_and_alt", "alt_only")
    if len(caption) > 2200:
        die(f"The caption for '{folder.name}' is {len(caption)} characters; Instagram allows 2,200.")

    # the commit actually checked out (the workflow checks out the latest main)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                         text=True).stdout.strip() or os.environ["GITHUB_SHA"]
    repo = os.environ["GITHUB_REPOSITORY"]
    urls = [f"https://raw.githubusercontent.com/{repo}/{sha}/"
            f"{urllib.parse.quote(img.relative_to(ROOT).as_posix())}" for img in images]
    kind = "carousel of " + str(len(images)) if len(images) > 1 else "single photo"
    print(f"Posting '{folder.name}' ({kind}) – {len(posts) - 1} post(s) left after this")
    for i, (img, url) in enumerate(zip(images, urls)):
        alt = texts[i] if texts and use_alt else ""
        print(f"  {img.name}: {url}" + (f"\n      alt text: {alt}" if alt else ""))
    print(f"Caption:\n{caption}\n")
    for url in urls:
        check_public(url)

    t = token()
    print(f"Token check: {len(t)} characters, starts with {t[:3]!r}"
          + (", contains spaces/line breaks" if any(c.isspace() for c in t) else ""))
    if not t:
        # Not set up yet: warn instead of failing, so GitHub doesn't email a failure every hour.
        print("::warning::IG_ACCESS_TOKEN secret isn't set yet – nothing posted. See SETUP.md.")
        return
    user_id, username = find_account()
    print(f"Token OK – connected to @{username} (account {user_id})")
    want = CONFIG.get("instagram_username", "").lower().lstrip("@")
    if want and (username or "").lower() != want:
        die(f"Token reaches @{username}, but config.json says to post to @{want}. Stopping.")

    if DRY_RUN:
        print("DRY RUN – stopping before publishing. Nothing was posted or moved.")
        return

    if len(images) == 1:
        container = api("POST", f"{user_id}/media", image_url=urls[0], caption=caption)["id"]
    else:
        children = []
        for i, (img, url) in enumerate(zip(images, urls)):
            extra = {"alt_text": texts[i][:1000]} if texts and use_alt and texts[i] else {}
            child = api("POST", f"{user_id}/media", image_url=url, is_carousel_item="true", **extra)["id"]
            wait_until_ready(child, img.name)
            children.append(child)
        container = api("POST", f"{user_id}/media", media_type="CAROUSEL",
                        children=",".join(children), caption=caption)["id"]
    wait_until_ready(container, folder.name)

    media_id = api("POST", f"{user_id}/media_publish", creation_id=container)["id"]

    # It's live: take it out of the queue and mark the slot used before anything
    # else can fail, so a retry never posts it a second time.
    shutil.rmtree(folder)
    if slot:
        state["last_slot"] = slot.isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"folder={folder.name}\n")

    permalink = (api("GET", media_id, quiet=True, fields="permalink") or {}).get("permalink", "")
    print(f"Posted: {permalink or media_id}")
    POSTED.mkdir(exist_ok=True)
    log = POSTED / "log.csv"
    new = not log.exists()
    with log.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["posted_at", "file", "media_id", "permalink"])
        w.writerow([now.isoformat(timespec="minutes"),
                    f"{folder.name}: " + " + ".join(i.name for i in images), media_id, permalink])

    left = len(posts) - 1
    if left <= CONFIG.get("low_queue_posts", 2):
        print(f"::warning::Only {left} post(s) left in the queue – add more photos.")


def wait_until_ready(container, label):
    for _ in range(30):
        status = api("GET", container, fields="status_code").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            die(f"Instagram couldn't process {label} (status {status}).")
        time.sleep(4)
    die(f"Instagram took too long to process {label}.")


if __name__ == "__main__":
    main()
