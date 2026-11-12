# Instagram uploader

Drop photos in a folder and they go out on **@sol_gutt_foto** by themselves at 09:00 and 19:00: single photos or carousels of up to 5.

**The folder:** `~/Desktop/solgutt.github.io/instagram-uploader/queue/`
**The preview:** open `instagram-uploader/preview.html` in your browser.

This is its own repository, separate from the website. The website's `.gitignore` excludes it, so it never ends up on the site.

## Day to day

1. **Drop photos into `queue/`.** Use finished exports, any size, JPEG/PNG/TIFF.
2. **Wait a few seconds.** Each photo gets its own post folder, numbered in the order Finder shows them. Left alone, every photo is a single post.
3. **To make a carousel, drag photos into one folder.** A post can have 1 to 5 photos:

   ```
   queue/
     Post 001/
       1 BW_2.jpg        ← slide 1 (also the grid thumbnail)
       1 BW_2.txt        ← optional words for slide 1
       2 BW_3.jpg  + .txt
       3 BW_5.jpg  + .txt
       caption.txt       ← the post's caption
     Post 004/
       1 BW_NL.jpg       ← a single post
       caption.txt
   ```

   The folders you emptied are removed automatically, unless you typed something into their `caption.txt`. If a folder ends up with more than 5 photos, the extras move into a new post right after it, e.g. `Post 001 (2)`.

   Each `caption.txt` is written from that post's first photo:

   ```

   May 23, 2026 · 10:17 AM
   Canon EOS 7D · 40mm · f/4.5 · 1/80s · ISO 160
   solgutt.com (link in bio)
   ```

   A location line is added when the photo has GPS data or a location typed in Lightroom.
4. **Optional:** open `caption.txt` and type your own words on the empty first line, or anywhere else. Whatever is in the file is the caption, exactly as written. Save the file and it syncs on its own.
   **Per-slide words:** type them into that slide's `.txt`. They appear at the top of the caption as `1/ …`, `2/ …`, and become that slide's alt text. Instagram's API can't use the app's "multiple captions" toggle, so this is the closest it allows.
5. Done. Check `preview.html` to see how the grid will look and when each post goes out.

**After a post goes out,** its folder is deleted. `posted/log.csv` keeps the date, the file names and the link to the post.

### Hashtags
The three hashtags in `config.json` are added automatically, 10 invisible lines below the caption, so they sit out of sight under "more". To use different ones for a single post, type your own `#hashtags` in its `caption.txt`. The automatic ones are then left out.

### Changing things before they post
- **Order of posts:** rename the folders. `Post 003` → `Post 000` posts it next.
- **Order of slides:** change the number at the front of the photo names. Duplicates or gaps (`1, 1, 3` or `2, 3`) are fixed automatically: slides are renumbered 1, 2, 3, keeping your order. When two share a number, they're put in name order. Slide 1 is the thumbnail in the grid.
- **Move a photo between posts:** drag it to another folder. 1 to 5 photos per post.
- **Remove a post:** delete its folder.

## What happens to each photo

When a photo lands in `queue/`, it's replaced by an Instagram-ready copy:

- Converted to sRGB and rotated upright.
- Resized to 1440 px wide.
- **Carousels are always 3:2 landscape.** Portrait photos get white bars at the sides; nothing is cropped. Every slide gets the same shape, because Instagram crops all slides to the first one's shape. Each slide is rebuilt from your original, so moving photos around never pads anything twice.
- A single-photo post keeps its own shape, between 4:5 and 1.91:1.
- **All metadata removed**, so GPS coordinates never reach GitHub. Anything that couldn't be prepared (an iPhone HEIC, a RAW file, a broken photo) stays in `queue/` on this Mac and is never uploaded; `logs/watcher.log` says `not uploaded`. Export it as JPEG and drop it in again.
- If a different photo already had the same file name, the new one is renamed `name-2`, so the two never get mixed up.

Your untouched original is kept in `originals/`. That folder stays on this Mac and is never uploaded. Delete old ones whenever you like.

## Feed preview and low-queue warning

`preview.html` is rebuilt every time the folder syncs:

- **Grid:** how your profile will look once the queued posts are out. Scheduled tiles show their posting time; faded tiles are already posted.
- **Schedule:** each post in order, with its time, all its slides and the exact caption.
- **Warnings:** a banner shows when the queue is running low, and when photos are still being prepared.

When 2 or fewer posts are left, your Mac also shows a notification, at most once a day.

## Settings: `config.json`

| Setting | What it does |
|---|---|
| `post_times` | When to post, in 24-hour time. `["09:00", "19:00"]` = 2 posts a day = 6 photos a day. |
| `max_photos_per_post` | Most photos in one post (default 5). Extras move to a new post. |
| `carousel_shape` | `"landscape"` (always 3:2), `"portrait"` (always 4:5) or `"first_photo"` (slide 1 decides). |
| `slide_text` | What a slide's `.txt` does: `"caption_and_alt"`, `"caption_only"` or `"alt_only"`. |
| `low_queue_posts` | Warn when this many posts or fewer are left (default 2). |
| `hashtags` / `hashtag_gap_lines` | The automatic hashtags, and how many blank lines go above them. |
| `caption.lines` | Which lines the auto caption has, in order. Plain text, like `"solgutt.com (link in bio)"`, goes in as written. |
| `caption.date_format` | Date style. `%B %-d, %Y · %-I:%M %p` gives `May 23, 2026 · 10:17 AM`. |
| `caption.camera_format` | Also accepts `{lens}`, e.g. `{model} · {lens} · {focal} · …` |
| `image.pad_color` | Color of the padding, e.g. `"#000000"` for black. |

Caption settings only apply to photos added after the change. Hashtag and posting-time changes apply right away.

## How it works

- **On this Mac:** a background watcher (`scripts/sync.sh`, installed by `scripts/install-watcher.sh`) runs whenever `queue/` changes, plus every 15 minutes as a backup. It prepares and groups new photos, syncs the folder with GitHub, rebuilds the preview and starts the posting job when a time is due. Its log is `logs/watcher.log`. It runs through a small helper app, "Instagram Uploader", because macOS only lets background jobs read the Desktop folder after you allow it once.
- **On GitHub:** `.github/workflows/post.yml` posts through Instagram's official API, then deletes the folder.
- **What starts the posting job:** three things, so a post goes out even if one fails:
  1. **cron-job.org** at :02 and :32 past each posting hour. Works with the Mac off. See [SETUP.md](SETUP.md#7-posting-with-the-mac-off).
  2. The **Mac watcher**, whenever the Mac is awake.
  3. **GitHub's own timer**, which is unreliable on its own.

  Each time slot posts once, whichever trigger gets there first. A missed slot is never made up on a later day; the queue just moves on.
- Only photos that have reached GitHub can post, so drop them in while online.

First-time setup: see [SETUP.md](SETUP.md).

## Handy commands

Run these from this folder:

```bash
bash scripts/sync.sh                         # sync right now
open preview.html                            # open the feed preview
tail -f logs/watcher.log                     # watch the background log
bash scripts/install-watcher.sh --uninstall  # stop the watcher
```

## When something goes wrong

GitHub emails you when a posting run fails. You can read every run under **Actions → Post to Instagram**.

| What you see | What it means |
|---|---|
| `API access blocked` | Meta has temporarily restricted the app. It happened once, on Nov 6–7 2026, and cleared by itself within a day, with nothing under Required actions. The next slot retries automatically. |
| `Invalid OAuth access token` | The `IG_ACCESS_TOKEN` secret is wrong or was revoked. Generate a new one ([SETUP.md](SETUP.md#3-token-from-a-system-user) step 3). |
| No posts and no runs | cron-job.org's GitHub key has probably expired. Renew it ([SETUP.md](SETUP.md#7-posting-with-the-mac-off) step 7). |
| Captions not appearing in `queue/` | The Mac watcher isn't running. Check `logs/watcher.log`, then run `bash scripts/sync.sh` once, or reinstall the watcher. |

To check Meta's side, go to GitHub → **Actions → Post to Instagram → Run workflow**, tick **diagnose**, and run it. It reports what Meta is allowing (token, permissions, app, account, posting quota) and posts nothing.
