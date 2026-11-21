# Changes — 2026.11.21

Squash of the outstanding primary-branch work: 117 files, ~13.6k insertions.
This document is a developer-facing inventory of what changed and where.

---

## 1. AI plugin discovery

* `plugin_system.py`
  * `ActionPlugin` gains `AI_QUICK_DESCRIPTION` / `AI_LONG_DESCRIPTION` class attributes and an `available_to_menu` flag (`is_available_to_menu()`).
  * New helpers: `effective_arg_default()` (honours `PLUGIN.DEFAULT.*` overrides), `build_ai_arg()`, `ai_args_for_plugin()`, `ai_usage_notes()`.
* `plugin_routes.py`
  * New endpoint `POST /plugin/list/ai` — lists every ready, menu-visible, user-authorized plugin with id, name, category, standalone flag, quick description and argument definitions (with effective defaults).
  * New endpoint `POST /plugin/describe` — full AI description + usage notes + args for one plugin by id.
  * `POST /plugin/list` (book actions) now also respects `is_available_to_menu()`.
* Every plugin class across `plugins/` was annotated with `AI_QUICK_DESCRIPTION` and `AI_LONG_DESCRIPTION`.

## 2. Key/value stores and book alt name (data layer)

* `db.py`
  * New models `BookKeyValue` (unique per book+key+purpose) and `MediaFolderKeyValue` (unique per folder+key+purpose), both cascade-deleted with their parent.
  * New `Book.alt_name` column (+ `ensure_schema` migration) and `get_keys_for_purpose()` on both `Book` and `MediaFolder`.
* `constants.py`
  * `BOOK_KEY_PURPOSE_ALT_VALUE = 1`, `MEDIA_FOLDER_KEY_PURPOSE_DEFAULT = 1`.
* `volume_queries.py` / `media_queries.py`
  * New CRUD: `find_book_key_values`, `find_book_key_value`, `add_book_key_value`, `update_book_key_value`, `remove_book_key_value`, and the media-folder equivalents.
* `volume_queries.py`
  * Book search (`_build_books_query`, `_build_books_with_progress_query`, `list_books_for_rating`, `count_books_for_rating`) now also matches `Book.alt_name` and accepts `filter_type` (style) and `processors` filters.
  * `upsert_book()` now requires `alt_name`.

## 3. Volume routes (manual book management)

* `volume_routes.py`
  * New book management endpoints: `/volume/details`, `/volume/new`, `/volume/update`, `/volume/remove`.
  * New book key endpoints: `/volume/keys/list|get|insert|update|delete|gen`.
  * New bookmark endpoints: `/volume/bookmarks/list|add|remove`.
  * New `/volume/list/history`.
  * New image/chapter surgery endpoints: `/volume/remove/image`, `/volume/merge/image`, `/volume/split/image`, `/volume/split/image/multi`, `/volume/remove/chapter`.
  * New `/volume/download/chapter/<book_folder>/<chapter_name>` and `/volume/upload/chapter`.
  * New `/volume/list/processors` and `/volume/scan/duplicates` (pHash duplicate scan).
  * Book listing now supports `filter_type` and `processors` request parameters.

## 4. Media routes

* `media_routes.py`
  * New endpoint `POST /media/list/by-date` — files created within a `start_date`/`end_date` (YYYYMMDD) range, with paging and sorting.
  * New folder key endpoints: `/media/keys/list|get|insert|update|delete` (gated on folder rating + group access via `_acquire_folder_for_access`).
  * `POST /media/file/progress` is now `VIEW_MEDIA` (was `MANAGE_MEDIA`) so viewers can report progress.
  * DA/DD folder sorts now use `MediaFolder.last_date`; folder info includes `id`.
  * File and note uploads now bump the folder's `last_date`.

## 5. Task manager and process routes

* `thread_utils.py`
  * Workers are named (rotating list of 32 names, generation suffix on reuse) and report `status` (idle/running/waiting/dead), `last_seen` and uptime.
  * `TaskManager` now takes a `key_lock_manager`; queue scheduling is lock-aware — a weight-blocked top task blocks the queue (capacity-fill semantics preserved) while lock-blocked tasks are skipped so other workers stay busy.
  * `has_task()` and `get_task_by_id()` now also consider running tasks; new `purge_task()`.
  * `TaskWrapper` gains `ref_folder_name`, `temp_folder_path`, `expected_files_count`, `expected_files_as_progress`, and `get_progress()` (file-count based progress when configured).
  * All log methods accept `_markdown` / `_json` flags; entries are tagged with a `fmt` field (`txt`/`md`/`json`); TRACE lines are also mirrored to the standard logging stream.
* `file_utils.py`
  * `temporary_folder()` now publishes the path on the task wrapper (`temp_folder_path`) so tasks can report progress and the UI can list files.
* `process_routes.py`
  * `POST /process/status/<task_id>` — paged log output (`log_page`/`log_page_size`), `log_total`/`log_pages`, and optional `include_files=1` to list the task's temp-folder contents; tasks now expose `folder_name` and computed progress.
  * New `POST /process/log/download/<task_id>` — downloads the full task log as Markdown (table) or JSON attachment.
  * New `DELETE /process/purge/<task_id>` — removes a finished/queued task.
  * Worker loop uses idle backoff (1s→10s) and proper status transitions; removed the old `position` bookkeeping.

## 6. Book image pipeline (always WEBP)

* `server.py` / `app_queries.py`
  * The `SERVER.VOLUME.FORMAT` app property is removed; volume image format is now hard-coded to `WEBP` everywhere (`get_volume_format()` returns `WEBP`).
* `image_utils.py`
  * `convert_images_to_format()` always rewrites to **lossless WEBP**: RGBA/CMYK → RGB, 1-bit → grayscale when scaling, width > 2048 scaled down, height > 16383 (WebP hard limit) split into uniform slices, then the folder is renumbered sequentially (`0001.webp`, …).
  * Non-image files are purged from chapter folders; leftover `___*` slice temp files from crashed runs are cleaned up; truncated images are tolerated (`LOAD_TRUNCATED_IMAGES`).
  * `Image.MAX_IMAGE_PIXELS = None` (tall book scans no longer trip PIL's decompression-bomb guard).
  * `merge_two_images()` supports horizontal merging and scales mismatched dimensions instead of failing.
  * New `split_image_into_pieces()` (crop at pixel offsets → WEBP temp pieces).
* `image_hashing.py` (new module) — SHA256 + pHash/dHash/aHash image details, chapter scanning, and pHash duplicate matching (`PHASH_DUPLICATE_THRESHOLD = 10`).
* Book processor default storage format changed `PNG` → `WEBP` in `plugin_system.py`, `processor_core.py` and the book plugins.
* `GenericBasicProcessor.py` — falls back through WebP → JPEG → **JPG** image extraction (`extract_jpg_strings`).

## 7. New book plugins

| Plugin | Purpose |
|---|---|
| `plugins/book_audit.py` | Read-only audit: wrong aspect ratios, split images, duplicate books/chapters (pHash), decimal-chapter grouping |
| `plugins/book_auto_split.py` | Splits tall scroll-style images into uniform slices (destructive) |
| `plugins/book_deduplicate_handler.py` | Detects duplicate pages across a book's chapters (pHash) |
| `plugins/book_max_size.py` | Resizes oversized chapter images to a max width/height |
| `plugins/book_merge_images.py` | Stacks listed chapter images into single vertical WEBP pages (destructive) |
| `plugins/book_refresh_chapter.py` | Lossless re-save of one chapter's images to repair corrupt data |

## 8. Remote "limited scraper" support

* `constants.py` / `server.py` / `app_queries.py`
  * New app properties `LIMITED.SCRAPER.HOST` and `LIMITED.SCRAPER.PORT` (+ getters).
* `processors/processor_core.py`
  * New `CustomDownloadInterface` methods: `is_remote_process()`, `get_remote_scrape_key_names()`, `is_valid_url()`, `allow_http2()`.
* `plugins/book_volume_processing.py`
  * Remote book downloads: batches of image URLs are sent to the scraper (batch curl), returned zip archives are extracted, and the book's alt name is stored as a `BookKeyValue` (`BOOK_KEY_PURPOSE_ALT_VALUE`).
* `batch_curl.py` (new) — `download_image_batch()` driving `curl_chrome116` in parallel with per-URL JSON write-out (Linux only), with HTTP/2 support.
* New plugins:
  * `plugins/general_restart_scraper.py` — fire-and-forget restart of the configured scraper.
  * `plugins/general_refresh_scraper_cookies.py` — submits a cookie-refresh job to the scraper.

## 9. Download improvements

* `plugins/media_download_file.py`
  * Multi-URL fallback: `URL`/`Origin` may be `;`-separated lists; each source is tried in order (with a randomised delay between attempts), rejecting Cloudflare blocks and zero-length files; bumps folder `last_date`.
* `plugins/media_download_m3u8.py` — same multi-URL fallback for ffmpeg HLS capture; clearer failure logging.
* `plugins/media_download_m3u8_ex.py`
  * HLS segment batch downloading via `batch_curl` (parallel, optional HTTP/2), downloaded-segment validation, Cloudflare retry path, and tracker-payload logging.
  * New HTTP2 argument on both Ex plugin variants.
* `plugins/media_download_tracker.py`
  * Payload groups may now carry multiple STREAM/SUBTITLE items; new `m3u8_audio` group type; VTT downloads get priority 1 so they land first; `mp3`/`mp4`/`vtt` groups handled as direct files; new standalone (global) variant with a Default Folder argument; HTTP2 argument.
* `plugins/media_download_yt.py` / `media_download_yt_music.py` — bump the destination folder's `last_date` after ingest; AI descriptions.

## 10. Media encoding

* `media_encoder_util.py` (new) — `remote_encode()` / `remote_defreeze()` against the configured encoder service: `MultipartEncoder` upload, ticket polling, streamed result download, task weight dropped to 2 while waiting remotely.
* `ffmpeg_utils.py`
  * New "Max Resolution" encode argument (`src`/4k/2k/1080/720/320) with `_build_scale_filter()`; replaces the old hard-coded 3840 cap (and fixes the inverted subtitles/scale branch).
  * `encode_video()` tries the remote encoder up to 5 times (5–8 s delays) before falling back to local; new `local_only` flag; local encode takes weight 70.
  * New `probe_media()` (raw ffprobe JSON); `get_media_info()` renders a Markdown report when `print_details` is set.
* `plugins/media_file_encode.py` — Max Resolution, Location (primary/archive) and "Local Encoding Only" arguments; preview generation for the new file.
* `plugins/media_file_subtitle.py` — new folder-scope variant; "Local Encoding Only" support.
* `plugins/media_defreeze.py` — tuning arguments (Freeze dB, Silence Noise, Min Duration, Force Encode); submits to the remote encoder when configured, else local `cut_gaps`; weight 20.

## 11. New media plugins

| Plugin | Purpose |
|---|---|
| `plugins/media_file_merge.py` | Merges a set of videos into one H.264 MP4, picking the best video + best audio stream via ffprobe |
| `plugins/media_file_mux.py` | Stream-copies video from one file + audio from another into one MP4 (no re-encode); deletes sources |
| `plugins/media_file_details_handler.py` | ffprobe container/stream report + basic file properties |
| `plugins/media_folder_info.py` | Markdown report of every file in a folder |
| `plugins/media_initialize_keys.py` | Creates the `SSH_PATH` / `SSH_REGEX` key values a folder needs for SFTP sync |
| `plugins/media_normalize_names_folder.py` | Normalizes episode-named filenames in a folder |
| `plugins/media_sync_folders.py` | One-way SFTP sync of every folder with an `SSH_PATH` key (optional `SSH_REGEX` per-folder filter) |
| `plugins/series_action_sync.py` | SFTP push of the whole video-series library (SERIES_OUT / VIDEO_ARCHIVE) to a remote host |

## 12. Auth and app configuration

* `auth_routes.py` / `auth_utils.py` — JWT tokens now carry the user group id (`gid`) on both initial authentication and renewal.
* `app_utils.py` — new `value_is_mac_list()` validator (`NAME@MAC;NAME@MAC`, bare MACs allowed).
* `plugins/general_wake_pc.py` — supports multiple configured PCs; new PC selector argument (`*` = all); property description updated.

## 13. Plugin behaviour updates

* `plugins/book_info.py` — new Mode argument: `export_to_json` (book list as JSON), `top_50_stale` (markdown table), `continue_reading_10` (priority-ranked continue-reading list).
* `plugins/book_update_contents.py` — new Book Scope argument (All / Local / Remote); single-chapter action gains Allow Remote; local books without valid headers are skipped with a `RunReport` instead of failing.
* `plugins/general_test.py` — reports progress over its 60 s run.
* `plugin_methods.py` — new shared `FFMPEG_LOCAL_ONLY` argument; logging/duplicate-checking arguments now carry descriptions.

## 14. Documentation

* New `docs/` reference: `auth_routes.md`, `media_routes.md`, `process_routes.md`, `volume_routes.md`, `plugins.md`, `raspberry.md`, `image_hash.md`, `image_hashing.md`.
* New `docs/plugins/format.md` defining the per-plugin doc format, plus one doc file per plugin under `docs/plugins/{book,media,general}/`.

## 15. Dependencies

* `requirements.txt` — added `requests-toolbelt~=1.0.0` (multipart encoder for the remote encoder) and `imagehash~=4.3.1` (pHash/dHash/aHash).
