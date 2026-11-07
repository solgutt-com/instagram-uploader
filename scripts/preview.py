#!/usr/bin/env python3
"""Build preview.html: how @sol_gutt_foto's grid will look, and the posting schedule.

Runs on the Mac after every sync (scripts/sync.sh). Open preview.html in a browser.
Also writes .preview/status.json, which sync.sh uses for the low-queue warning.
"""
import csv
import html
import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps

from common import full_caption, loose_photos, queued_posts, read_caption, upcoming_slots

ROOT = Path(__file__).resolve().parent.parent
QUEUE, ORIGINALS, POSTED = ROOT / "queue", ROOT / "originals", ROOT / "posted"
OUT = ROOT / "preview.html"
CACHE = ROOT / ".preview" / "thumbs"
CONFIG = json.loads((ROOT / "config.json").read_text())


def key_for(name):
    """Same photo, whatever its slide prefix or extension: '2 IMG_1.jpg' -> 'IMG_1'."""
    return re.sub(r"^\d+ ", "", Path(name).stem)


def thumb(src, key):
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"{key}.jpg"
    if not out.exists() and src and src.exists():
        try:
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((720, 900))
                im.save(out, "JPEG", quality=82)
        except Exception:
            return None
    return out if out.exists() else None


def find_original(key):
    if ORIGINALS.exists():
        for p in ORIGINALS.iterdir():
            if p.stem == key:
                return p
    return None


def src_url(path):
    return urllib.parse.quote(path.relative_to(ROOT).as_posix()) if path else ""


def fmt(dt):
    return f"{dt:%a %-d %b} · {dt:%H:%M}"


def build():
    tz = ZoneInfo(CONFIG["timezone"])
    now = datetime.now(tz)
    state = json.loads((ROOT / "state.json").read_text()) if (ROOT / "state.json").exists() else {}
    per_post = int(CONFIG.get("photos_per_post", 3))

    posts = queued_posts(QUEUE)
    slots = upcoming_slots(now, state, CONFIG, len(posts))
    upcoming = []
    for (folder, imgs), when in zip(posts, slots):
        thumbs = [thumb(i, key_for(i.name)) for i in imgs]
        upcoming.append({"name": folder.name, "when": when, "thumbs": thumbs, "count": len(imgs),
                         "caption": full_caption(read_caption(folder), CONFIG)})

    posted = []
    log = POSTED / "log.csv"
    if log.exists():
        with log.open() as f:
            for row in csv.DictReader(f):
                names = row["file"].split(": ", 1)[-1].split(" + ")
                thumbs = []
                for n in names:
                    k = key_for(n)
                    thumbs.append(thumb(None, k) or thumb(find_original(k), k))
                posted.append({"when": datetime.fromisoformat(row["posted_at"]), "thumbs": thumbs,
                               "count": len(names), "link": row.get("permalink", "")})

    waiting = loose_photos(QUEUE)
    waiting_thumbs = [thumb(p, key_for(p.name)) for p in waiting]

    left = len(posts)
    low = left <= CONFIG.get("low_queue_posts", 2)
    runs_out = slots[-1] if slots else None
    status = {"low": low, "posts_left": left, "runs_out": runs_out.isoformat() if runs_out else None,
              "waiting": len(waiting)}
    (ROOT / ".preview").mkdir(exist_ok=True)
    (ROOT / ".preview" / "status.json").write_text(json.dumps(status))

    # ---------- page ----------
    e = html.escape
    def tile(item, upcoming_tile):
        t = item["thumbs"][0] if item["thumbs"] else None
        img = f'<img src="{src_url(t)}" alt="" loading="lazy">' if t else '<div class="noimg"></div>'
        multi = '<span class="multi" title="Carousel">❐</span>' if item["count"] > 1 else ""
        chip = f'<span class="chip">{e(fmt(item["when"]))}</span>' if upcoming_tile else ""
        inner = f"{img}{multi}{chip}"
        if not upcoming_tile and item.get("link"):
            return f'<a class="tile posted" href="{e(item["link"])}" target="_blank">{inner}</a>'
        return f'<div class="tile{" next" if upcoming_tile else " posted"}">{inner}</div>'

    grid = "".join(tile(u, True) for u in reversed(upcoming))
    grid += "".join(tile(p, False) for p in reversed(posted))

    rows = []
    for u in upcoming:
        pics = "".join(f'<img src="{src_url(t)}" alt="">' for t in u["thumbs"] if t)
        rows.append(f"""
      <article class="post">
        <header><b>{e(fmt(u["when"]))}</b><span>{e(u["name"])} · {u["count"]} photo{'s' if u["count"] != 1 else ''}</span></header>
        <div class="pics">{pics}</div>
        <pre class="cap">{e(u["caption"]) or '<i>no caption</i>'}</pre>
      </article>""")
    if not rows:
        rows.append('<p class="empty">Nothing queued. Drop photos into <code>queue/</code>.</p>')

    banners = []
    if low:
        when = f" after {e(fmt(runs_out))}" if runs_out else ""
        banners.append(f'<div class="banner warn"><b>Running low:</b> {left} post{"s" if left != 1 else ""} left'
                       f' – the feed goes quiet{when}. Drop at least {per_post} more photos into <code>queue/</code>.</div>')
    if waiting:
        need = per_post - len(waiting) % per_post
        pics = "".join(f'<img src="{src_url(t)}" alt="">' for t in waiting_thumbs if t)
        banners.append(f'<div class="banner info"><b>{len(waiting)} photo{"s" if len(waiting) != 1 else ""} waiting</b>'
                       f' – add {need} more to make the next post.<div class="pics small">{pics}</div></div>')

    until = f"runs until {e(fmt(runs_out))}" if runs_out else "queue empty"
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Feed preview</title>
<style>
:root {{ --bg:#fafafa; --card:#fff; --ink:#111; --muted:#737373; --line:#dbdbdb;
        --warn-bg:#fff4e5; --warn:#8a4b00; --info-bg:#eef4ff; --info:#1d3f8a; --chip:rgba(0,0,0,.62); }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#000; --card:#121212; --ink:#f5f5f5; --muted:#a8a8a8; --line:#262626;
          --warn-bg:#2b1d08; --warn:#ffcf8a; --info-bg:#0d1a33; --info:#a9c4ff; }} }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--ink);
       font:15px/1.45 -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif; }}
main {{ max-width:935px; margin:0 auto; padding:24px 16px 64px; }}
.profile {{ display:flex; gap:24px; align-items:center; padding:8px 0 24px; border-bottom:1px solid var(--line); }}
.avatar {{ width:77px; height:77px; border-radius:50%; background:var(--line); display:grid; place-items:center;
          font-weight:600; letter-spacing:.04em; flex:none; }}
.profile h1 {{ font-size:20px; font-weight:400; margin:0 0 6px; }}
.profile p {{ margin:0; color:var(--muted); }}
.banner {{ margin:16px 0 0; padding:12px 14px; border-radius:10px; }}
.warn {{ background:var(--warn-bg); color:var(--warn); }}
.info {{ background:var(--info-bg); color:var(--info); }}
h2 {{ font-size:12px; letter-spacing:.12em; text-transform:uppercase; color:var(--muted);
      font-weight:600; margin:32px 0 12px; }}
.grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:3px; }}
.tile {{ position:relative; aspect-ratio:3/4; overflow:hidden; background:var(--line); display:block; }}
.tile img {{ width:100%; height:100%; object-fit:cover; display:block; }}
.tile.posted {{ opacity:.55; }}
.multi {{ position:absolute; top:8px; right:9px; color:#fff; font-size:17px; text-shadow:0 0 4px rgba(0,0,0,.6); }}
.chip {{ position:absolute; left:6px; bottom:6px; background:var(--chip); color:#fff; font-size:11px;
        padding:3px 7px; border-radius:20px; white-space:nowrap; }}
.legend {{ color:var(--muted); font-size:13px; margin:8px 0 0; }}
.post {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; margin:0 0 14px; }}
.post header {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:10px; }}
.post header span {{ color:var(--muted); }}
.pics {{ display:grid; grid-template-columns:repeat(3,1fr); gap:6px; }}
.pics img {{ width:100%; aspect-ratio:4/5; object-fit:contain; background:var(--bg); border-radius:6px; display:block; }}
.pics.small {{ grid-template-columns:repeat(6,1fr); margin-top:10px; }}
.cap {{ white-space:pre-wrap; font:inherit; margin:12px 0 0; max-height:none; }}
.empty {{ color:var(--muted); }}
code {{ font-size:13px; }}
@media (max-width:600px) {{ .profile {{ gap:16px; }} .avatar {{ width:56px; height:56px; }} .chip {{ font-size:10px; }} }}
</style></head><body><main>
  <section class="profile">
    <div class="avatar">SG</div>
    <div><h1>@{e(CONFIG.get("instagram_username", ""))}</h1>
      <p>{left} post{"s" if left != 1 else ""} queued · {until} · posting at {e(", ".join(CONFIG["post_times"]))}</p></div>
  </section>
  {"".join(banners)}
  <h2>Grid</h2>
  <div class="grid">{grid or '<p class="empty">No posts yet.</p>'}</div>
  <p class="legend">Bright tiles are scheduled, with their posting time; faded tiles are already on Instagram (click to open). ❐ = carousel.</p>
  <h2>Schedule</h2>
  {"".join(rows)}
  <p class="legend">Updated {now:%a %-d %b, %H:%M}. Refreshes every minute.</p>
</main></body></html>"""
    OUT.write_text(page, encoding="utf-8")
    return status


if __name__ == "__main__":
    s = build()
    print(json.dumps(s))
