# Update Cache

Two plugins live in this file covering full-library and single-book cache regeneration.

---

## Update All Caches

**Action ID:** `action.book.update.caches`
**Plugin class:** `UpdateAllCaches`
**Type:** General (all books)
**Feature flag:** `MANAGE_VOLUME`

### Description

Rebuilds the database cache and file definitions for every book in the library. Run this after bulk filesystem changes or to repair inconsistent metadata.

### Arguments

| Name | ID | Type | Default | Description |
|---|---|---|---|---|
| Clean Previews | `clean_previews` | select | `n` | `y` = delete and regenerate all chapter preview thumbnails |
| Update Tags | `update_tags` | select | `n` | `y` = sync each book's tags from the processor |

### What It Does

1. Iterates every book folder on disk.
2. For each book, rescans chapter folders, counts pages, regenerates filenames, and updates `Chapter` records.
3. Optionally regenerates WebP preview thumbnails for every chapter.
4. Optionally syncs tags from the configured processor.
5. Updates `Book.last_date`, `Book.first_chapter`, `Book.last_chapter`, and other aggregate fields.

---

## Update Cache

**Action ID:** `action.book.update.cache`
**Plugin class:** `UpdateSingleCache`
**Type:** Book-specific
**Feature flag:** `MANAGE_VOLUME`

### Description

Rebuilds the database cache and file definitions for a single book.

### Arguments

| Name | ID | Type | Required | Default | Description |
|---|---|---|---|---|---|
| Book ID | `book_id` | string | Yes | — | The book to update |
| Clean Previews | `clean_previews` | select | No | `n` | `y` = regenerate chapter preview thumbnails |

### What It Does

Same as Update All Caches but scoped to one book. Rescans the book's chapter folders, updates chapter records, regenerates page counts and filenames, and optionally rebuilds preview thumbnails.
