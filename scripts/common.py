"""Shared by post.py (GitHub), prepare.py and preview.py (Mac). Standard library only.

Queue layout:
    queue/Post 001/1 IMG_0001.jpg     <- one folder = one Instagram post
    queue/Post 001/2 IMG_0002.jpg        (a carousel when it has 2+ photos)
    queue/Post 001/3 IMG_0003.jpg
    queue/Post 001/caption.txt
    queue/IMG_0004.jpg + .txt         <- loose photos waiting to fill a post
Posts go out in Finder's order (natural sort: "Post 2" before "Post 10").
"""
import re
from datetime import datetime, timedelta

JPG = (".jpg", ".jpeg")
SPACER = "⠀"  # invisible "braille blank": keeps empty lines in Instagram captions


def natural_key(name):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def post_images(folder):
    return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in JPG
                   and not p.name.startswith(".")), key=lambda p: natural_key(p.name))


def queued_posts(queue):
    """[(folder, [images])] in posting order."""
    if not queue.exists():
        return []
    posts = []
    for d in sorted((d for d in queue.iterdir() if d.is_dir() and not d.name.startswith(".")),
                    key=lambda d: natural_key(d.name)):
        imgs = post_images(d)
        if imgs:
            posts.append((d, imgs))
    return posts


def loose_photos(queue):
    if not queue.exists():
        return []
    return sorted((p for p in queue.iterdir() if p.is_file() and p.suffix.lower() in JPG
                   and not p.name.startswith(".")), key=lambda p: natural_key(p.name))


def read_caption(folder):
    f = folder / "caption.txt"
    if not f.exists():
        txts = sorted(folder.glob("*.txt"), key=lambda p: natural_key(p.name))
        f = txts[0] if txts else None
    return f.read_text(encoding="utf-8").strip() if f else ""


def full_caption(text, config):
    """The caption exactly as it's posted: your text, then hashtags far below it."""
    tags = config.get("hashtags", [])
    if not tags or "#" in text:          # you wrote your own hashtags: leave them alone
        return text
    gap = max(1, int(config.get("hashtag_gap_lines", 10)))
    return (text + "\n" if text else "") + "\n".join([SPACER] * gap) + "\n" + " ".join(tags)


def slot_times(config, tz):
    return [tuple(int(x) for x in t.split(":")) for t in sorted(config["post_times"])]


def due_slot(now, state, config):
    """Latest of today's posting times that has passed and hasn't been used."""
    last = state.get("last_slot")
    last = datetime.fromisoformat(last) if last else None
    due = [now.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in slot_times(config, now.tzinfo)]
    due = [s for s in due if s <= now and (last is None or s > last)]
    return max(due) if due else None


def upcoming_slots(now, state, config, count):
    """When the next `count` posts will go out."""
    slots = []
    first = due_slot(now, state, config)
    if first:
        slots.append(first)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    while len(slots) < count:
        for h, m in slot_times(config, now.tzinfo):
            s = day.replace(hour=h, minute=m)
            if s > now and (not slots or s > slots[-1]) and len(slots) < count:
                slots.append(s)
        day += timedelta(days=1)
    return slots
