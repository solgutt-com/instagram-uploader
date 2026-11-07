#!/usr/bin/env python3
"""Prepare new photos dropped into queue/ for Instagram.

For every photo that hasn't been prepared yet:
  1. Read its metadata (date/time, GPS or Lightroom location, camera + settings).
  2. Write queue/<name>.txt with an auto caption, unless a .txt already exists.
  3. Back up the untouched original to originals/ (local only, never uploaded).
  4. Replace it in queue/ with an Instagram-ready JPEG: sRGB, rotated upright,
     fitted to Instagram's 4:5 – 1.91:1 range, max 1440 px wide, and with ALL
     metadata removed (so GPS coordinates never land in the public repo).

Exit codes: 0 = done, 3 = some files were still being copied (run again soon).
"""
import io
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageCms, ImageOps

from common import JPG, loose_photos, natural_key

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "queue"
ORIGINALS = ROOT / "originals"
CONFIG = json.loads((ROOT / "config.json").read_text())

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
MARKER = b"prepared-by-instagram-uploader"
SETTLE_SECONDS = 8          # ignore files modified this recently (still copying)
MIN_RATIO, MAX_RATIO = 4 / 5, 1.91


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------- metadata

def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _gps_to_deg(dms, ref):
    try:
        d, m, s = (float(x) for x in dms)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    deg = d + m / 60 + s / 3600
    return -deg if ref in ("S", "W") else deg


def _xmp_value(xmp, tag):
    m = re.search(rf'{tag}="([^"]*)"', xmp) or re.search(rf"<{tag}>([^<]*)</{tag}>", xmp)
    return m.group(1).strip() if m and m.group(1).strip() else None


def read_metadata(path, img):
    exif = img.getexif()
    sub = exif.get_ifd(0x8769)
    gps = exif.get_ifd(0x8825)
    meta = {}

    raw_dt = sub.get(36867) or sub.get(36868) or exif.get(306)
    if raw_dt:
        try:
            meta["taken"] = datetime.strptime(str(raw_dt).strip()[:19], "%Y:%m:%d %H:%M:%S")
        except ValueError:
            pass

    meta["model"] = (exif.get(272) or "").strip() or None
    meta["lens"] = (sub.get(42036) or "").strip() or None
    meta["focal"] = _num(sub.get(37386))
    meta["aperture"] = _num(sub.get(33437))
    meta["shutter"] = _num(sub.get(33434))
    iso = sub.get(34855)
    meta["iso"] = iso[0] if isinstance(iso, tuple) else iso

    if gps.get(2) and gps.get(4):
        lat = _gps_to_deg(gps[2], gps.get(1, "N"))
        lon = _gps_to_deg(gps[4], gps.get(3, "E"))
        if lat is not None and lon is not None:
            meta["gps"] = (lat, lon)

    # Location typed in Lightroom (IPTC/XMP), used when there's no GPS
    data = path.read_bytes()[:400_000]
    i, j = data.find(b"<x:xmpmeta"), data.find(b"</x:xmpmeta>")
    if i != -1 and j != -1:
        xmp = data[i:j].decode("utf-8", "replace")
        parts = [_xmp_value(xmp, t) for t in
                 ("Iptc4xmpCore:Location", "photoshop:City", "photoshop:State", "photoshop:Country")]
        parts = [p for k, p in enumerate(parts) if p and p not in parts[:k]]
        if parts:
            meta["xmp_location"] = ", ".join(parts)
    return meta


def reverse_geocode(lat, lon):
    url = "https://nominatim.openstreetmap.org/reverse?" + urllib.parse.urlencode(
        {"format": "jsonv2", "lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "zoom": 12, "accept-language": "en"})
    req = urllib.request.Request(url, headers={"User-Agent": "instagram-uploader/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            addr = json.load(r).get("address", {})
    except Exception as e:  # offline etc. – caption just goes without a place
        log(f"  location lookup failed ({e})")
        return None
    finally:
        time.sleep(1.1)  # Nominatim's usage policy: max 1 request / second
    place = next((addr[k] for k in ("city", "town", "village", "municipality", "suburb", "county")
                  if addr.get(k)), None)
    region = addr.get("state") if addr.get("country_code") == "us" else None
    parts = [p for p in (place, region, addr.get("country")) if p]
    return ", ".join(dict.fromkeys(parts)) or None


def fmt_shutter(s):
    if s is None:
        return None
    if s >= 1:
        return f"{s:g}s"
    return f"1/{round(1 / s)}s" if s > 0 else None


def build_caption(meta):
    c = CONFIG["caption"]
    values = {"date": "", "location": "", "camera": ""}

    if meta.get("taken"):
        values["date"] = meta["taken"].strftime(c["date_format"])

    if meta.get("gps") and c.get("location_lookup", True):
        values["location"] = reverse_geocode(*meta["gps"]) or ""
    if not values["location"]:
        values["location"] = meta.get("xmp_location") or ""

    if meta.get("model"):
        bits = {
            "model": meta["model"],
            "lens": meta.get("lens") or "",
            "focal": f"{meta['focal']:g}mm" if meta.get("focal") else "",
            "aperture": f"f/{meta['aperture']:g}" if meta.get("aperture") else "",
            "shutter": fmt_shutter(meta.get("shutter")) or "",
            "iso": str(meta["iso"]) if meta.get("iso") else "",
        }
        line = c["camera_format"].format(**bits)
        # tidy up separators left behind by missing values
        line = re.sub(r"ISO\s*(?=·|$)", "", line)
        line = " · ".join(p.strip() for p in line.split("·") if p.strip())
        values["camera"] = line

    lines = [ln.format(**values).strip() for ln in c["lines"]]
    return "\n".join(ln for ln in lines if ln)


# ---------------------------------------------------------------- image

def to_srgb(img):
    icc = img.info.get("icc_profile")
    if not icc:
        return img.convert("RGB")
    try:
        src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        if "srgb" in (ImageCms.getProfileDescription(src) or "").lower():
            return img.convert("RGB")
        return ImageCms.profileToProfile(img.convert("RGB"), src, ImageCms.createProfile("sRGB"),
                                         outputMode="RGB")
    except Exception:
        return img.convert("RGB")


def fit_for_instagram(img):
    cfg = CONFIG["image"]
    w, h = img.size
    ratio = w / h
    if ratio < MIN_RATIO or ratio > MAX_RATIO:
        target = MIN_RATIO if ratio < MIN_RATIO else MAX_RATIO
        if cfg.get("too_tall_or_wide", "pad") == "crop":
            if ratio < target:   # too tall -> trim top/bottom
                nh = round(w / target)
                top = (h - nh) // 2
                img = img.crop((0, top, w, top + nh))
            else:                # too wide -> trim sides
                nw = round(h * target)
                left = (w - nw) // 2
                img = img.crop((left, 0, left + nw, h))
        else:
            if ratio < target:
                canvas = Image.new("RGB", (round(h * target), h), cfg.get("pad_color", "#ffffff"))
            else:
                canvas = Image.new("RGB", (w, round(w / target)), cfg.get("pad_color", "#ffffff"))
            canvas.paste(img, ((canvas.width - w) // 2, (canvas.height - h) // 2))
            img = canvas
    max_w = cfg.get("max_width", 1440)
    if img.width > max_w:
        img = img.resize((max_w, round(img.height * max_w / img.width)), Image.LANCZOS)
    return img


def pad_to_portrait(path):
    """Carousel slides must share one shape (Instagram crops them all to the first
    slide's), so every slide is padded to the same 4:5 frame."""
    cfg = CONFIG["image"]
    with Image.open(path) as img:
        img.load()
        w, h = img.size
        if abs(w / h - MIN_RATIO) < 0.005:
            return
        if w / h > MIN_RATIO:      # wider than 4:5 -> bars top and bottom
            canvas = Image.new("RGB", (w, round(w / MIN_RATIO)), cfg.get("pad_color", "#ffffff"))
        else:
            canvas = Image.new("RGB", (round(h * MIN_RATIO), h), cfg.get("pad_color", "#ffffff"))
        canvas.paste(img.convert("RGB"), ((canvas.width - w) // 2, (canvas.height - h) // 2))
    max_w = cfg.get("max_width", 1440)
    if canvas.width > max_w:
        canvas = canvas.resize((max_w, round(canvas.height * max_w / canvas.width)), Image.LANCZOS)
    canvas.save(path, "JPEG", quality=cfg.get("jpeg_quality", 92), optimize=True,
                progressive=True, comment=MARKER)


def is_prepared(path):
    try:
        with Image.open(path) as im:
            return im.info.get("comment", b"") == MARKER
    except Exception:
        return False


def prepare(path, write_caption=True):
    with Image.open(path) as img:
        img.load()
        meta = read_metadata(path, img)
        upright = ImageOps.exif_transpose(img)
        if upright is None:
            upright = img
        out = fit_for_instagram(to_srgb(upright))

    txt = path.with_suffix(".txt")
    if not write_caption:
        pass
    elif txt.exists():
        log(f"  kept your existing {txt.name}")
    else:
        txt.write_text("\n" + build_caption(meta) + "\n", encoding="utf-8")
        log(f"  wrote {txt.name}")

    ORIGINALS.mkdir(exist_ok=True)
    backup = ORIGINALS / re.sub(r"^\d+ ", "", path.name)
    if backup.exists():
        backup = ORIGINALS / f"{path.stem}-{int(time.time())}{path.suffix}"
    shutil.move(str(path), backup)

    dest = path.with_suffix(".jpg")
    out.save(dest, "JPEG", quality=CONFIG["image"].get("jpeg_quality", 92),
             optimize=True, progressive=True, comment=MARKER)
    if not write_caption:              # dropped into a post folder: it's a carousel slide
        pad_to_portrait(dest)
    log(f"  ready: {dest.name} ({out.width}×{out.height})")


# lines the uploader writes itself (date, camera, website, hashtags, spacers)
AUTO_LINE = re.compile(r"^([A-Z][a-z]+ \d{1,2}, \d{4}.*|.*\s·\s.*|solgutt\.com.*|#.*|\u2800*)$")


def group_into_posts():
    """Bundle loose, prepared photos into post folders of `photos_per_post`."""
    per_post = max(1, int(CONFIG.get("photos_per_post", 3)))
    loose = [p for p in loose_photos(QUEUE) if is_prepared(p)]
    numbers = [int(m.group(1)) for d in QUEUE.iterdir()
               if d.is_dir() and (m := re.match(r"Post (\d+)$", d.name))]
    nxt = max(numbers, default=0) + 1
    while len(loose) >= per_post:
        group, loose = loose[:per_post], loose[per_post:]
        folder = QUEUE / f"Post {nxt:03d}"
        nxt += 1
        folder.mkdir()
        texts = [(p.with_suffix(".txt").read_text(encoding="utf-8")
                  if p.with_suffix(".txt").exists() else "") for p in group]
        caption = texts[0].rstrip()
        # keep anything you typed into the other photos' captions
        extra = []
        for t in texts[1:]:
            for line in t.splitlines():
                line = line.strip()
                if line and not AUTO_LINE.match(line) and line not in caption and line not in extra:
                    extra.append(line)
        if extra:
            caption = "\n".join(extra) + "\n" + caption.lstrip("\n")
        (folder / "caption.txt").write_text(caption + "\n", encoding="utf-8")
        for i, p in enumerate(group, 1):
            dest = folder / f"{i} {p.name}"
            p.rename(dest)
            p.with_suffix(".txt").unlink(missing_ok=True)
            if per_post > 1:
                pad_to_portrait(dest)
        log(f"Grouped into {folder.name}: " + ", ".join(p.name for p in group))
    if loose:
        log(f"{len(loose)} photo(s) waiting for {per_post - len(loose)} more to make a post")


def main():
    QUEUE.mkdir(exist_ok=True)
    pending = False
    # loose photos, plus photos dropped straight into a post folder
    candidates = [(p, True) for p in sorted(QUEUE.iterdir())]
    for d in sorted(QUEUE.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            candidates += [(p, False) for p in sorted(d.iterdir())]
    for path, loose in candidates:
        if path.suffix.lower() not in IMAGE_EXTS or path.name.startswith("."):
            continue
        if is_prepared(path):
            continue
        if time.time() - path.stat().st_mtime < SETTLE_SECONDS:
            pending = True
            continue
        log(f"New photo: {path.relative_to(QUEUE)}")
        try:
            prepare(path, write_caption=loose)
        except Exception as e:
            log(f"  could not prepare {path.name}: {e}")
    if not pending:
        group_into_posts()
    return 3 if pending else 0


if __name__ == "__main__":
    sys.exit(main())
