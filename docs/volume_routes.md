# volume_routes.py - Book Management API

This module provides a RESTful API for managing a book library (manga/comics), including:
- List and navigate books, chapters, and images
- Track reading progress
- Manage bookmarks
- CRUD operations for book metadata
- Manage per-book key/value rows (`BookKeyValue`)
- Image manipulation within chapters
- Download/upload a chapter as a zip archive
- Tag management and guessing
- Processor listing

## Blueprint
```python
volume_blueprint = Blueprint('volume', __name__)
```

---

## Book Retrieval Routes

### `GET /list/books` (POST)
Retrieves a paginated list of books filtered by rating, text, tags, and processor.

**Authentication:** Requires `VIEW_BOOKS` feature flag.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `offset` | int | No | 0 | Pagination offset |
| `limit` | int | No | 20 | Max books per page |
| `rating` | int | No | 0 | Max content rating to include |
| `sort` | string | No | 'AZ' | Sort order: 'AZ', 'ZA' by name; 'DA', 'DD' by date |
| `filter_text` | string | No | '' | Keyword search in book names |
| `filter_tags` | string | No | '' | Comma-separated tags to filter by |
| `filter_type` | string | No | '' | Book type filter |
| `filter_processor` | string | No | '' | Comma-separated processor IDs to filter by (book must match any of them) |

**Response:**
```json
{
  "success": "",
  "data": {
    "books": [
      {
        "id": "book_id",
        "json": "book_id",
        "name": "Book Title",
        "rating": 0,
        "cover": true/false,
        "first": 1,
        "last": 50,
        "active": true,
        "date": "YYYYMMDD",
        "tags": ["tag1", "tag2"],
        "style": "page"|"scroll",
        "recent": {"chapter": "ch_id", "value": "@0.95"}
      }
    ],
    "paging": {"total": 100, "offset": 0}
  }
}
```

---

### `GET /list/chapters` (POST)
Retrieves a list of chapters for a given book with the user's reading progress on each.

**Authentication:** Requires `VIEW_BOOKS` feature flag.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `book_id` | string | Yes | - | Book whose chapters to list |

**Response:**
```json
{
  "success": "",
  "data": {
    "chapters": [{"name": "chapter_id", "value": "@0.95"}],
    "name": "Book Title",
    "style": "page"|"scroll",
    "info_url": ""
  }
}
```

---

### `GET /list/tags` (POST)
Retrieves the full list of available tags.

**Authentication:** Requires `VIEW_BOOKS` feature flag.

**Response:**
```json
{
  "success": "",
  "data": {"tags": ["Action", "Adventure", "Sci-Fi"]}
}
```

---

### `GET /list/images` (POST)
Retrieves a list of image file names for a given chapter, including navigation metadata and optional dimensions.

**Authentication:** Requires `VIEW_BOOKS` feature flag.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `book_id` | string | Yes | - | Book ID |
| `chapter_id` | string | Yes | - | Chapter ID within the book |
| `include_sizes` | boolean (query) | No | false | If true, return each file's pixel dimensions in `"sizes"` |

**Response:**
```json
{
  "success": "",
  "data": {
    "prev": "previous_chapter_id",
    "next": "next_chapter_id",
    "sizes": [{"w": 800, "h": 1200}],
    "files": ["file.png", ...],
    "style": "page"|"scroll"
  }
}
```

---

## Progress Tracking Routes

### `GET /progress` (POST)
Updates the user's reading progress for a given book and chapter.

**Authentication:** Requires `VIEW_BOOKS` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `book_id` | string | Yes | Book ID |
| `chapter_id` | string | Yes | Chapter ID within the book |
| `value` | string | Yes | Current page number or progress. For scroll mode: `"<number>"` or `"@<percent>"`. For page-perfect: `"@0"` or page number. |

**Response:**
```json
{"success": "", "data": {}}
```

---

## Recent History Routes

### `GET /list/history` (POST)
Retrieves the user's recent reading history entries.

**Authentication:** Requires `VIEW_BOOKS` feature flag.

**Response:**
```json
{
  "success": "",
  "data": {
    "history": [
      {
        "name": "Book Title",
        "book": "book_id",
        "chapter": "chapter_id",
        "mode": "page"|"scroll",
        "page": "@0.95",
        "timestamp": "YYYYMMDD"
      }
    ]
  }
}
```

---

## Bookmark Routes

### `GET /bookmarks/list` (POST)
Retrieves a list of bookmarks for the authenticated user.

**Authentication:** Requires `BOOKMARKS \| VIEW_BOOKS` feature flags.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `book_id` | string | Optional: filter by specific book ID |

**Response:**
```json
{
  "success": "",
  "data": {
    "items": [
      {
        "id": 123,
        "book": "book_id",
        "chapter": "chapter_id",
        "page": "42",
        "progress": "@0.75"
      }
    ]
  }
}
```

---

### `GET /bookmarks/add` (POST)
Adds a bookmark for the authenticated user.

**Authentication:** Requires `BOOKMARKS \| VIEW_BOOKS` feature flags.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `book_id` | string | Yes | Book ID |
| `chapter_id` | string | Yes | Chapter ID |
| `page_number` | string | Yes | Page value: `"@<percent>"` for progress or page number |

**Response:**
```json
{"success": "", "data": {}}
```

---

### `GET /bookmarks/remove` (POST)
Removes a bookmark for the authenticated user.

**Authentication:** Requires `BOOKMARKS \| VIEW_BOOKS` feature flags.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `row_id` | string | Yes | Bookmark row ID (must be integer) |

**Response:**
```json
{"success": "", "data": {}} OR {"failure": "bookmark not found"}
```

---

## Book Metadata & CRUD Routes

### `GET /details` (POST)
Retrieves details of a specific book.

**Authentication:** Requires user authentication.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `book_id` | string | Yes | Book ID |

**Response:**
```json
{
  "success": "",
  "data": {
    "info": {
      "id": "book_id",
      "name": "Book Title",
      "alt_name": "Alternate Title",
      "processor": "processor_id",
      "active": true,
      "info_url": "",
      "rss_url": "",
      "extra_url": "",
      "start_chapter": "1",
      "skip": "chapter_id",
      "rating": 0,
      "tags": ["tag1"],
      "style": "page"|"scroll"
    }
  }
}
```

---

### `GET /new` (POST)
Adds a new book to the library.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Parameters:** All fields from `BOOK_FIELDS`:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | Book ID (lowercase, valid format) |
| `name` | string | Yes | Book name |
| `alt_name` | string | No | Alternate name |
| `processor` | string | Yes | Processor ID or `'@AUTO'` for auto-detection |
| `active` | boolean | Yes | Whether book is active |
| `info_url` | string | Yes | Info URL |
| `rss_url` | string | No | RSS feed URL |
| `extra_url` | string | No | Extra data URL |
| `start_chapter` | string | No | Starting chapter ID |
| `skip` | string | No | Skipped chapters comma-separated |
| `rating` | int | Yes | Content rating |
| `tags` | string | No | Comma-separated tags |
| `style` | string | Yes | `'page'` or `'scroll'` |

**Response:**
```json
{"success": "Book added successfully", "data": {}}
```

---

### `GET /update` (POST)
Updates an existing book in the library.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Parameters:** Same as `/new`.

**Response:**
```json
{"success": "Book updated successfully", "data": {}}
```

---

### `GET /remove` (POST)
Removes a book from the library and deletes its folder.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | Book ID to remove |

**Response:**
```json
{"success": "Book removed successfully", "data": {}}
```

---

## Book Key Value Routes

Manage per-book key/value rows (`BookKeyValue` table). A DB unique constraint enforces at most one row per `(book_id, key, purpose)`. Once a key is created it is locked (like the book ID) and cannot be renamed; only its value and purpose may be updated. `purpose` defaults to `BOOK_KEY_PURPOSE_ALT_VALUE` (`1`, used for the remote scraper `alt` map). All routes resolve the book first and fail if it is missing or the user's rating level disallows viewing it.

### `GET /keys/list` (POST)
Retrieves all key/value rows stored for a book.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `book_id` | string | Yes | Book ID |

**Response:**
```json
{
  "success": "",
  "data": {
    "items": [
      {
        "id": 123,
        "book": "book_id",
        "key": "key_name",
        "value": "key_value",
        "purpose": 1
      }
    ]
  }
}
```

---

### `GET /keys/get` (POST)
Retrieves a single key/value row for a book.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `book_id` | string | Yes | Book ID |
| `row_id` | string | Yes | Key/value row ID (must be integer) |

**Response:**
```json
{
  "success": "",
  "data": {
    "info": {
      "id": 123,
      "book": "book_id",
      "key": "key_name",
      "value": "key_value",
      "purpose": 1
    }
  }
}
```

Fails with `Key not found` if no row matches.

---

### `GET /keys/insert` (POST)
Adds a key/value row for a book.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `book_id` | string | Yes | - | Book ID |
| `key` | string | Yes | - | Key name (locked once created) |
| `value` | string | No | null | Key value |
| `purpose` | int | No | 1 | Purpose code (`BOOK_KEY_PURPOSE_ALT_VALUE`) |

**Response:**
```json
{"success": "Key added successfully", "data": {}}
```

Fails if a row for the same `book_id`/`key`/`purpose` already exists (unique constraint).

---

### `GET /keys/update` (POST)
Updates the value and/or purpose of an existing key/value row for a book. The key cannot be changed.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `book_id` | string | Yes | Book ID |
| `row_id` | string | Yes | Key/value row ID (must be integer) |
| `value` | string | No | New key value (empty clears it) |
| `purpose` | int | No | New purpose code (omitted leaves it unchanged) |

**Response:**
```json
{"success": "Key updated successfully", "data": {}}
```

Fails with `Key not found` if no row matches, or if the change would violate the `(book_id, key, purpose)` unique constraint.

---

### `GET /keys/delete` (POST)
Removes a key/value row for a book.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `book_id` | string | Yes | Book ID |
| `row_id` | string | Yes | Key/value row ID (must be integer) |

**Response:**
```json
{"success": "Key removed successfully", "data": {}} OR {"failure": "Key not found"}
```

---

## Image Editing Routes

### `GET /remove/image` (POST)
Removes an image file within a chapter and regenerates preview if needed.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `book_id` | string | Yes | Book ID |
| `chapter_id` | string | Yes | Chapter ID |
| `file_name` | string | Yes | Image filename to remove |

**Response:**
```json
{"success": "Image removed", "data": {}}
```

---

### `GET /merge/image` (POST)
Merges two images in a chapter into one.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `book_id` | string | Yes | Book ID |
| `chapter_id` | string | Yes | Chapter ID |
| `file_name` | string | Yes | Primary image filename |
| `alt_file_name` | string | Yes | Image to merge into primary (will be removed after) |

**Response:**
```json
{"success": "Image Merged", "data": {}}
```

---

### `GET /split/image` (POST)
Splits an image in a chapter vertically or horizontally, keeping only one half. The image is cropped in-place; no new files are created and the chapter index is not changed.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `book_id` | string | Yes | Book ID |
| `chapter_id` | string | Yes | Chapter ID |
| `file_name` | string | Yes | Image filename to split |
| `position` | int | Yes | Split position (pixel) |
| `is_horizontal` | boolean | Yes | `'true'` for horizontal split, `'false'` for vertical |
| `keep_first` | boolean | Yes | `'true'` to keep first half, `'false'` to keep second |

**Response:**
```json
{"success": "Image adjusted", "data": {}}
```

---

### `POST /split/image/multi`
Splits a single image into multiple pieces at a list of pixel positions, replacing the original file with N new WEBP images. All subsequent images in the chapter are shifted upward to make room, and the chapter DB index is rebuilt.

Use this when a series of pages has been merged into one tall (or wide) image and needs to be restored to individual pages.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `book_id` | string | Yes | Book ID |
| `chapter_id` | string | Yes | Chapter ID |
| `file_name` | string | Yes | Image filename to split (e.g. `0005.webp`) |
| `positions` | string | Yes | Comma-separated pixel cut points (e.g. `"1200,2400,3600"`). Must be strictly increasing and within the image dimension. |
| `is_horizontal` | boolean | Yes | `'true'` to cut by height (horizontal cuts), `'false'` to cut by width (vertical cuts) |

Positions define the boundaries between pieces. N positions produce N+1 output files. Each position must be greater than the previous and less than the relevant image dimension (height for horizontal, width for vertical).

**Example:** positions `"1200,2400,3600"` on a 4800px-tall image produces:

| File | Rows |
|------|------|
| `0005.webp` | 0 → 1200 |
| `0006.webp` | 1200 → 2400 |
| `0007.webp` | 2400 → 3600 |
| `0008.webp` | 3600 → 4800 |

The original `0005.webp` is deleted. Former `0006.webp`, `0007.webp`, etc. are renumbered upward to make room.

**Response:**
```json
{
  "success": "Image split successfully",
  "data": {
    "files": ["0005.webp", "0006.webp", "0007.webp", "0008.webp"]
  }
}
```

`files` contains only the newly created split pieces. All pieces are saved as WEBP lossless. Chapter preview is regenerated if the split target was the first image in the chapter.

---

### `GET /remove/chapter` (POST)
Removes a chapter from the library and deletes its folder.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `book_id` | string | Yes | Book ID |
| `chapter_id` | string | Yes | Chapter ID to remove |

**Response:**
```json
{"success": "chapter removed", "data": {}}
```

---

## Image Serving Routes

### `GET /serve_image/<book_folder>/<chapter_name>/<image_name>` (GET)
Serves an image file from the server. Supports quick mode for thumbnail resizing.

**Authentication:** Requires `VIEW_BOOKS` feature flag with cookie authentication.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `quick` | boolean | false | If true, resizes image to max-width 256px for thumbnails |

---

### `GET /serve_preview/<book_folder>/<chapter_name>` (GET)
Serves a preview image file from the server.

**Authentication:** Requires `VIEW_BOOKS` feature flag with cookie authentication.

---

## Chapter Archive Routes

### `GET /download/chapter/<book_folder>/<chapter_name>` (GET)
Downloads a zip archive (stored, no compression) containing all images of a chapter.

Image names inside the archive are renumbered from `0001` sequentially, keeping each file's original extension (e.g. `0001.webp`, `0002.png`, `0003.jpg`).

The zip is built on disk in the temp folder (UUID-named) and streamed to the client, so memory usage stays flat regardless of chapter size. The temp file is removed once the response is sent.

**Authentication:** Requires `VIEW_BOOKS` feature flag with cookie authentication.

**URL Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `book_folder` | string | Yes | Book ID |
| `chapter_name` | string | Yes | Chapter ID |

**Response:** A zip file attachment named `<book_id>_<chapter_id>.zip` (`application/zip`). Fails with 404 if the book/chapter is missing or the chapter has no images on disk.

---

### `POST /upload/chapter`
Uploads a chapter from a zip archive of images — the inverse of `download_chapter`.

The archive should contain images named `0001.<ext>`, `0002.<ext>`, ... (or `N.<ext>`) where `<ext>` is `.png`, `.webp`, `.jpg` or `.jpeg` (case-insensitive). Members are ordered by their leading number (unnumbered names sort last), renumbered from `1` in that order, and written one page at a time through a temp folder so memory stays flat even for very large zips. Non-image members are skipped (with a log entry); zips containing no supported images are rejected.

Once the archive is validated, any existing chapter with the same id is erased (folder, preview and database row) and replaced by the uploaded pages. No image processing is done here; a chapter scan/repair task can be run afterwards to generate previews and refresh book metadata. On success the new `Chapter` row has `page_count`, the compressed `image_names` string, `sequence` = (max existing sequence for the book) + 1, and date `2005-01-01`.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Parameters (multipart form data):**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `book_id` | string | Yes | Book ID (valid book-id format) |
| `chapter_id` | string | Yes | Chapter ID (`[A-Za-z0-9._-]+`) |
| `file` | file | Yes | Zip archive (`application/zip`) of chapter images |

**Response:**
```json
{
  "success": "chapter uploaded",
  "data": {
    "book_id": "book_id",
    "chapter_id": "chapter_id",
    "page_count": 70
  }
}
```

Fails if any parameter is missing/invalid, the book is not found, the user is disallowed by rating, the archive is not a valid zip, or the archive has no supported images. Erasure or database errors roll back the session and are reported as server errors.

---

## Utility Routes

### `GET /list/processors` (POST)
Retrieves details of all registered processors with their configuration requirements.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Response:**
```json
{
  "success": "",
  "data": {
    "processors": [
      {
        "id": "processor_id",
        "name": "Processor Name",
        "pageDescription": "Page description",
        "startId": true/false,
        "startIdDescription": "Start ID description",
        "baseUrl": true/false,
        "baseUrlDescription": "Base URL description",
        "rss": true/false,
        "rssDescription": "RSS description"
      }
    ]
  }
}
```

---

### `GET /guess/tags` (POST)
Given a space-separated string of words (typically typed by the user), finds matching tags from the database. Words that don't match existing tags become new suggestions in uppercase.

**Authentication:** Requires `VIEW_BOOKS` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `values` | string | Yes | Space-separated words to match against existing tags |

**Response:**
```json
{
  "success": "",
  "data": {"tags": ["Action", "SCIFI"]}
}
```

Matching multi-word tags consume all their component words; unmatched single words are added as-is.

---

### `POST /scan/duplicates`
Scans all chapters of a book for visually duplicate images (e.g. scanlation credits, ads, end-caps that repeat across chapters). Uses perceptual hashing with a sliding window of 10 chapters to keep memory usage low on Raspberry Pi hardware.

**Authentication:** Requires `MANAGE_VOLUME` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `book_id` | string | Yes | Book ID to scan |

**Response:**
```json
{
  "success": "",
  "data": {
    "groups": [
      {
        "items": [
          { "chapter": "0001", "filename": "page001.webp" },
          { "chapter": "0003", "filename": "page001.webp" },
          { "chapter": "0007", "filename": "page002.webp" }
        ]
      }
    ],
    "total_groups": 1,
    "chapters_scanned": 12
  }
}
```

Each entry in `groups` represents one distinct duplicate image identity. The `items` list contains every variant of that image found across chapters — the client can select which items to delete, mirroring the mass-delete component pattern.

**Match criteria:** SHA-256 exact match, or pHash distance ≤ 10 (tolerates resizing, re-encoding, minor edits). Only cross-chapter duplicates are reported; within-chapter repeats are ignored. Only subfolders matching the `####` or `####.#` naming convention are treated as chapters.

---

## Internal Components

### Constants
- `BOOK_FIELDS` - List of book fields: `['id', 'name', 'alt_name', 'processor', 'active', 'info_url', 'rss_url', 'extra_url', 'start_chapter', 'skip', 'rating', 'tags', 'style']`
- `BOOK_REQUIRED_FIELDS` - Required fields for creation/update
- `BOOK_DELETE_FIELDS` - Fields needed for deletion: `['id']`

### Helper Functions
- `acquire_book_fields(book_data)` - Normalizes and validates book data from form fields
- `_acquire_book_for_access(user_details, book_id)` - Resolves a book by ID and verifies rating-level access; returns `(book, None)` on success or `(None, failure_response)` when the book is missing or the user is disallowed
