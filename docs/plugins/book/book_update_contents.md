# Download Books

Three plugins live in this file covering bulk, single-book, and single-chapter download scenarios.

---

## Download All Books

**Action ID:** `action.books.download`
**Plugin class:** `UpdateAllBooksPlugin`
**Type:** General (all books)
**Feature flag:** `MANAGE_VOLUME`

### Description

Downloads new content for every active book in the library, interleaving books across processors to avoid hammering a single source.

### Arguments

| Name | ID | Type | Default | Description |
|---|---|---|---|---|
| Filter | `filter` | select | `*` | Limit downloads to a specific processor; `*` = all |
| Exclude | `exclude` | string | — | Comma-separated book IDs to skip |
| Clean | `clean` | select | `new` | `new` = only fetch new chapters; `all` = re-fetch everything |
| Headers | `headers` | long string | — | cURL-format headers (e.g. from browser DevTools) for authenticated sources |

### What It Does

1. Queries all active books, optionally filtered/excluded.
2. Groups books by processor and interleaves them (round-robin, randomised within each group) to spread load.
3. Creates one `DownloadBookJob` per book. Each job runs the processor's download logic, then chains an `UpdateSingleBookStats` task to rebuild the cache.

---

## Download Book

**Action ID:** `action.book.download`
**Plugin class:** `UpdateSingleBookPlugin`
**Type:** Book-specific
**Feature flag:** `MANAGE_VOLUME`

### Description

Downloads new or all chapters for a single book.

### Arguments

| Name | ID | Type | Required | Default | Description |
|---|---|---|---|---|---|
| Book ID | `book_id` | string | Yes | — | The book to download |
| Clean | `clean` | select | No | `new` | `new` = new chapters only; `all` = re-fetch everything |
| Headers | `headers` | long string | No | — | cURL-format headers for authenticated sources |

### What It Does

Runs the processor's download logic for the given book. Optionally updates stored request headers first if `headers` is provided. Chains an `UpdateSingleBookStats` task on completion.

---

## Download (Chapter)

**Action ID:** `action.book.download.chapter`
**Plugin class:** `UpdateSingleBookChapterPlugin`
**Type:** Book-specific
**Feature flag:** `MANAGE_VOLUME`

### Description

Downloads a single chapter from an explicit URL, using a specified chapter name.

### Arguments

| Name | ID | Type | Required | Description |
|---|---|---|---|---|
| Book ID | `book_id` | string | Yes | The book to add the chapter to |
| Chapter URL | `chapter_url` | URL | Yes | Direct URL of the chapter to download |
| Chapter Name | `chapter_name` | string | Yes | Name/ID to assign the downloaded chapter |
| Clean | `clean` | select | No | `new` or `all` — passed through to the processor |
| Headers | `headers` | long string | No | cURL-format request headers |

### What It Does

Calls the processor's single-chapter download with the provided URL and name. Optionally updates stored headers first. Chains an `UpdateSingleBookStats` task on completion.
