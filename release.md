# Release — 2026.11.21

Big one. This commit is a squash of everything that piled up on the primary
branch (117 files, ~13.6k lines), so instead of dozens of small commits you get
one big one. If you want the full developer-facing inventory, it's in
`changes.md`. Here's what you actually need to know.

## Books are WEBP now — and only WEBP

The `SERVER.VOLUME.FORMAT` app property is gone. Book images are now always
stored as lossless WEBP, no configuration. The conversion pipeline is stricter:
oversized images get scaled down (width > 2048), images taller than WebP's
hard limit (16383) get split into uniform slices, chapter folders get
renumbered sequentially (`0001.webp`, …), non-image junk gets purged, and
leftover slice temp files from crashed runs get cleaned up. Tall book scans
no longer trip PIL's decompression-bomb guard either.

## Books have alt names, keys, and proper manual management

Each book can carry an `alt_name` (searchable) plus a key/value store for
book-specific data. And there's finally real manual book management: create,
update, and remove books; manage per-book keys and bookmarks; split, merge,
and remove chapter images; upload and download individual chapters; scan for
pHash duplicates; and list books by type and processors.

## Media: date ranges, folder keys, and `last_date`

New `/media/list/by-date` endpoint pulls files created in a date range with
paging and sorting. Media folders get their own key/value store (this is where
`SSH_PATH` / `SSH_REGEX` live for SFTP sync). Folders now track `last_date`,
which gets bumped on file/note uploads and downloads, and DA/DD folder sorts
use it — so "recently active" folders actually sort that way. Viewers can now
report progress on media files (previously a manage-only permission).

## Downloads try harder

Download URLs (`URL` / `Origin`) can now be `;`-separated lists and each
source is tried in order with a randomised delay, rejecting Cloudflare blocks
and zero-length files — same treatment for HLS captures. The Ex HLS plugin can
now batch-download segments in parallel via `curl` (optional HTTP/2) and
validates what it got. Tracker payloads can carry multiple streams/subtitles
per group, VTT files land with priority so they're there first, and there's a
standalone tracker variant with a default folder.

## Encoding: remote-first with a local fallback

Video encoding has a new Max Resolution argument (up to 4K source) and a
"Local Encoding Only" toggle. When an encoder service is configured, encodes
go remote (upload → ticket polling → streamed download), retried up to 5 times
before falling back to local, and the task weight drops while waiting remotely.
Defreeze does the same remote-first treatment when configured, and has proper
tuning arguments now.

## A lot of new plugins

* **Book:** audit (aspect ratios, splits, pHash duplicates), auto-split of
  tall scroll images, cross-chapter duplicate detection, max-size resizer,
  image merger, and lossless chapter refresh for corrupt data.
* **Media:** file merge (best video + best audio via ffprobe), stream-copy
  mux (no re-encode), ffprobe details report, folder info report, SFTP key
  initialiser, filename normaliser, one-way SFTP folder sync, and a whole
  series-library SFTP push.
* **General:** remote scraper restart and cookie-refresh.
* Every existing plugin got AI descriptions, and there are two new endpoints
  (`/plugin/list/ai`, `/plugin/describe`) so an AI agent can discover and
  describe available plugins on its own.

## Task manager you can actually watch

Workers now have names, status, and uptime. Tasks report progress (optionally
based on expected file count) and expose their temp-folder contents. Task logs
are paged in the status endpoint, and there's a new download endpoint that
gives you the full log as a Markdown table or JSON attachment. Finished tasks
can be purged, and the scheduler is lock-aware: a task blocked on a lock gets
skipped so other workers stay busy instead of the whole queue stalling.

## Remote "limited scraper"

New `LIMITED.SCRAPER.HOST` / `LIMITED.SCRAPER.PORT` app properties. Remote
book downloads now send batches of image URLs to the scraper (parallel
`curl_chrome116`, Linux only), the returned zip archives get extracted, and
the book's alt name gets stored as a book key.

## Smaller stuff

* JWT tokens now carry the user group id on auth and renewal.
* Wake-on-LAN supports multiple PCs (`NAME@MAC;NAME@MAC`) with a PC selector
  argument (`*` = all).
* `book_info` gains modes: export the book list as JSON, a top-50-stale
  markdown table, and a priority-ranked continue-reading list.
* `book_update_contents` gains a Book Scope argument (All / Local / Remote)
  and skips local books without valid headers with a report instead of failing.
* New dependencies: `requests-toolbelt` (multipart uploads to the remote
  encoder) and `imagehash` (pHash/dHash/aHash).
* Docs: per-plugin documentation under `docs/plugins/` plus reference pages for
  the auth, media, process, and volume routes.
