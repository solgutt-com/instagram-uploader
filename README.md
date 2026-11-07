# Instagram uploader

Drop photos in a folder and they go out on Instagram by themselves, two a day by default.

**The folder:** `~/Desktop/solgutt.github.io/instagram-uploader/queue/`

This is its own repository, separate from the website. The website's `.gitignore` excludes it, so it never ends up on the site.

## Day to day

1. **Drop photos into `queue/`.** Use finished exports, any size, JPEG/PNG/TIFF.
2. **Wait a few seconds.** Each photo gets a caption file with the same name, e.g. `IMGM3973.txt`:

   ```

   May 23, 2026 · 10:17 AM
   Canon EOS 7D · 40mm · f/4.5 · 1/80s · ISO 160
   solgutt.com (link in bio)
   ```

   A location line is added when the photo has GPS data or a location typed in Lightroom.
3. **Optional:** open the `.txt` and type your own words on the empty first line, or anywhere else. Whatever is in the file is the caption, exactly as written. Hashtags go here too. Save the file and it syncs on its own.
4. Done. Photos post in **alphabetical filename order** at the times in `config.json`. Rename a file and its `.txt` to change the order, e.g. add `00_` in front to post it next.

After a photo is posted, it moves (with its caption) to `posted/`, and `posted/log.csv` records the link to the post.

**Remove a photo before it posts:** delete it and its `.txt` from `queue/`.

## What happens to the photo

When a photo lands in `queue/`, it's replaced by an Instagram-ready copy:

- Converted to sRGB and rotated upright.
- Resized to 1440 px wide.
- Fitted to Instagram's allowed shape: between 4:5 portrait and 1.91:1 landscape. Tall portraits like the 7D's 2:3 get thin white side bars instead of being cropped.
- **All metadata removed**, so GPS coordinates never reach GitHub.

Your untouched original is kept in `originals/`. That folder stays on this Mac and is never uploaded.

## Settings: `config.json`

| Setting | What it does |
|---|---|
| `post_times` | When to post, in 24-hour time. `["09:00", "19:00"]` = 2 a day. Add or remove times to change how many posts go out each day. |
| `timezone` | The time zone for those times. |
| `caption.lines` | Which lines the auto caption has, in order. Remove `"{camera}"` to drop the camera line. Plain text, like `"solgutt.com"`, goes in as written. |
| `caption.date_format` | Date style. `%B %-d, %Y · %-I:%M %p` gives `May 23, 2026 · 10:17 AM`. |
| `caption.camera_format` | Also accepts `{lens}`, e.g. `{model} · {lens} · {focal} · …` |
| `image.too_tall_or_wide` | `"pad"` (white bars) or `"crop"`. |
| `image.pad_color` | Color of the bars, e.g. `"#000000"` for black. |

Caption settings only apply to photos added after the change. Posting times take effect within the hour.

## How it works

- **On this Mac:** a background watcher (`scripts/sync.sh`, installed by `scripts/install-watcher.sh`) runs whenever `queue/` changes, plus every 15 minutes as a backup. It prepares new photos, writes their captions, and syncs the folder with GitHub. Its log is `logs/watcher.log`. The watcher runs through a small helper app, "Instagram Uploader", because macOS only lets background jobs read the Desktop folder after you allow it once.
- **On GitHub:** `.github/workflows/post.yml` runs every hour. When a posting time has passed, it posts the next photo through Instagram's official API and moves it to `posted/`. It runs even when your Mac is off.
  - Only photos that reached GitHub can post, so drop them in while online.
  - A post can land up to about 30 minutes after its set time, because GitHub's hourly runs often start late.
- **Token refresh:** `.github/workflows/refresh-token.yml` renews the Instagram token every week so it never expires.

First-time setup: see [SETUP.md](SETUP.md).

## Handy commands

Run these from this folder:

```bash
bash scripts/sync.sh                       # sync right now
tail -f logs/watcher.log                   # watch the background log
bash scripts/install-watcher.sh --uninstall  # stop the watcher
```
