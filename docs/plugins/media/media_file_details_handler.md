# File Details

**Action ID:** `action.file.details`
**Plugin class:** `MediaFileDetailsPlugin`
**Type:** Media file
**Feature flag:** `MANAGE_MEDIA`

## Description

Returns a single markdown log entry containing general file details (from the database) followed by format-specific media info (from ffprobe) when the file is a recognised media format. Works on any file type — non-media files (e.g. `.txt`, `.zip`) produce only the general section.

## Arguments

None beyond the implicit file selection.

## What It Does

1. Retrieves the `MediaFile` record from the database and validates user access.
2. Builds a general properties table from the database record: filename, MIME type, file size (KB and bytes), archive flag, and created date.
3. Resolves the file path on disk (`primary` or `archive` storage based on the `archive` flag).
4. Runs `ffprobe` on the file. If ffprobe succeeds, appends a **Media Info** sub-section containing container format, duration, bit rate, and a per-stream breakdown (codec, type, bit rate; plus resolution and frame rate for video streams; channels and sample rate for audio streams).
5. Logs the combined result as a single `_markdown=True` log entry.

## Output

Emits exactly one log entry with `fmt: "md"`. The structure is:

```
## File Details

| Property | Value |
|---|---|
| Filename | `...` |
| MIME Type | `...` |
| File Size | `... KB (... bytes)` |
| Archive | `...` |
| Created | `...` |

### Media Info        ← present only for media files

| Property | Value |
|---|---|
| Format | `...` |
| Duration | `...` |
| Bit Rate | `...` |

#### Streams

##### Stream N (Video|Audio)
| Property | Value |
...
```

## Notes

- Non-media files produce only the **File Details** table; the absence of a **Media Info** section is not an error.
- Runs at `priority = 0` so it is scheduled ahead of lower-priority background jobs.
