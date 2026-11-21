# Scan Duplicate Images

**Action ID:** `action.book.deduplicate`
**Plugin class:** `BookDeduplicatePlugin`
**Type:** Book-specific
**Feature flag:** `MANAGE_VOLUME`

## Description

Scans all chapters in a single book for duplicate images using perceptual hashing (pHash). Runs as a background task to avoid REST timeout issues with large books. Results are written to the task log as JSON and can be retrieved via the task status API.

## Arguments

| Name | ID | Type | Required | Description |
|---|---|---|---|---|
| Book ID | `book_id` | string | Yes | The book to scan for duplicate images |

## What It Does

1. Locates the book's folder on disk.
2. Calls `scan_for_duplicate_chapters()` with a sliding window of **15 chapters** and passes itself as the `task_wrapper` for live progress reporting.
3. For each chapter, fingerprints every image with SHA-256 and pHash/dHash/aHash. Two images are considered duplicates if their SHA-256 matches exactly or their pHash distance is ≤ 10.
4. Compares each chapter against:
   - All previously seen (potentially evicted) chapter images tracked in `HitMaster`.
   - Images still in the 15-chapter sliding window.
5. On completion, logs the full result as a JSON string at `INFO` level.
6. Sets `worked` flag if any duplicates were found.

## Progress

| Field | Meaning |
|---|---|
| `progress` | Overall chapter scan progress (0–100%) |
| `percent` | Resets to 0 at start of each chapter, set to 100 when fingerprinting is done |

## Output JSON Shape

```json
{
  "root_folder": "/path/to/book",
  "chapters_scanned": 42,
  "duplicate_count": 3,
  "hits": [
    {
      "source_chapter": "0001",
      "source_filename": "0001.webp",
      "matches": [
        { "chapter": "0005", "filename": "0001.webp", "phash_distance": 0 }
      ]
    }
  ]
}
```

Retrieve results from `GET /process/status/<task_id>` — the JSON is in the `log` array as an `INFO`-level entry.
