# Image Fingerprinting and Duplicate Detection System

## Overview

This system provides image-level fingerprinting and cross-chapter duplicate detection for a media library.

**Primary goals:**

1. Detect duplicate images across chapters of the same book.
2. Detect unwanted recurring images (scanlation credits, ads, end-caps) so they can be reviewed and removed.
3. Detect visually identical images despite:
   - Different file formats (PNG / JPG / WEBP)
   - Resizing
   - Compression differences
   - Minor brightness or editing changes
4. Run efficiently on Raspberry Pi hardware.

The system operates on the final WEBP images served by the media server.

---

## Current Implementation

The live implementation lives in two files:

| File | Role |
|------|------|
| `image_hashing.py` | Fingerprinting utilities and duplicate scan engine |
| `volume_routes.py` | Flask route `POST /scan/duplicates` that exposes the scan to clients |

See `docs/image_hashing.md` for the full API reference and `docs/volume_routes.md` for the route contract.

---

## Fingerprinting Strategy

### 1. Exact Hash

**Algorithm:** SHA-256 over raw file bytes.

**Use:** Detects byte-identical files instantly with zero false positives. Checked before perceptual hashing.

---

### 2. Perceptual Hashing (Primary)

Three hashes are computed and stored per image:

| Hash | Algorithm | Strength |
|------|-----------|----------|
| `phash` | pHash (DCT-based) | Robust to resize, re-encode, minor edits |
| `dhash` | dHash (gradient) | Fast; good for crop/shift detection |
| `ahash` | Average hash | Simple baseline |

**Match criterion:** pHash Hamming distance ≤ `PHASH_DUPLICATE_THRESHOLD` (default `10`).

**Handles:** PNG vs WEBP, different compression levels, resizing, minor brightness changes.

---

### 3. Feature Matching (Future)

OpenCV ORB for confirming uncertain matches. Not yet implemented. Only intended for cases where pHash distance exceeds the threshold but a possible duplicate exists.

---

## Scan Algorithm

### Inputs

- A book's root folder containing chapter subfolders named `####` or `####.#` (e.g. `0001`, `0012.5`).
- Optional `chapter_filter`: a set of chapter names to restrict the scan.
- `queue_size` (default `6`): sliding window depth.

### Memory Model

A `deque` of `queue_size` chapters is kept in RAM at once. As chapter N+1 is loaded, chapter N−`queue_size` is evicted. This bounds memory use to roughly `queue_size × pages_per_chapter × ~500 bytes per ImageDetails`.

**HitMaster** holds confirmed duplicate groups and their fingerprints permanently — groups are never evicted. This allows matching against images from chapters that have already left the window.

### Match Logic (per image in the current chapter)

```
1. Already in a group (HitMaster.is_known)?  → skip.
2. Matches any image already in HitMaster?   → join that group (add_to_existing_group).
3. Matches any ungrouped image in the window? → create a new group (add_new_group).
4. No match found                            → not a duplicate; continue.
```

Step 2 runs before the window search. This means a repeating image (e.g. a credit page first seen in chapter 0001) is still recognised and joined to its existing group when it reappears in chapter 0200, even though chapter 0001 has long since been evicted from the window.

### Example

Given chapters `[0001 … 0020]` with `queue_size=6` and a credit page recurring in 0001, 0005, 0010, 0015, 0020:

```
Process 0001: window empty. No match. Add to window.
Process 0005: window=[0001..0004]. Match found in window → new group {0001/credit, 0005/credit}.
Process 0010: HitMaster checked first. 0001/credit is known → join group → {…, 0010/credit}.
Process 0015: Same → {…, 0015/credit}.
Process 0020: 0001 evicted from window long ago, but HitMaster still has it → join group → {…, 0020/credit}.
```

Result: **one group** with five members, not five groups of two.

---

## Output Format

`scan_for_duplicate_chapters()` returns a `DuplicateScanReport`. The `POST /scan/duplicates` route reshapes it into:

```json
{
  "data": {
    "groups": [
      {
        "items": [
          { "chapter": "0001", "filename": "credit.webp" },
          { "chapter": "0005", "filename": "credit.webp" },
          { "chapter": "0010", "filename": "credit.webp" }
        ]
      }
    ],
    "total_groups": 1,
    "chapters_scanned": 20
  }
}
```

Each group is one distinct duplicate identity. The client can select which items to delete using the existing `POST /remove/image` endpoint.

---

## Tuning

### Similarity threshold

Edit `PHASH_DUPLICATE_THRESHOLD` in `image_hashing.py`:

| Value | Effect |
|-------|--------|
| `0` | Exact perceptual match only |
| `5` | Strict — tolerates minor compression differences |
| `10` | Default — tolerates resizing, re-encoding, minor brightness changes |
| `15+` | Loose — may produce false positives on visually distinct images |

### Window size

Pass `queue_size` to `scan_for_duplicate_chapters()`. The default of `6` is conservative for Raspberry Pi.

The window only matters for *discovering* new groups. Once a match is registered in HitMaster, later chapters find it via HitMaster regardless of window size. Increase the window if you have many chapters with no repeating content and want to catch first-time pairs that are far apart.

---

## Processing Pipeline (current)

```
Chapter folder
      |
      v
get_folder_image_details()
      |
      v
Per image: SHA-256 + pHash + dHash + aHash
      |
      v
_compare_chapter_to_window()
      |
      +--> HitMaster check (cross-window)
      |
      +--> Sliding window check (new pairs)
      |
      v
DuplicateScanReport
      |
      v
POST /scan/duplicates → JSON groups
      |
      v
Client review UI → POST /remove/image
```

---

## Database Design (Future)

The current implementation is file-system-only and does not persist fingerprints between scans. A database layer would allow:

- Avoiding re-hashing unchanged files on subsequent scans.
- Global duplicate detection across books (not just within one book).
- A blacklist system to permanently reject known unwanted images on import.

### Proposed Tables

#### MediaImage

| Column | Type | Description |
|--------|------|-------------|
| `id` | integer PK | Row ID |
| `media_id` | foreign key | Book/chapter reference |
| `page_number` | integer | Page number |
| `original_filename` | text | Original file name |
| `webp_path` | text | Path to converted WEBP |
| `width` | integer | Width in pixels |
| `height` | integer | Height in pixels |
| `file_size` | integer | File size in bytes |
| `sha256` | text | Exact hash |
| `phash` | text | Perceptual hash |
| `dhash` | text | Difference hash |
| `ahash` | text | Average hash |
| `created_date` | datetime | Creation timestamp |
| `status` | enum | ACTIVE, BLACKLISTED, DUPLICATE, QUARANTINE |

#### DuplicateGroup / DuplicateMember

Tracks confirmed duplicate sets across the library.

#### ImageBlacklist

Permanently rejects known unwanted images on import.

| Column | Type | Description |
|--------|------|-------------|
| `phash` | text | Perceptual hash of blacklisted image |
| `scope` | text | GLOBAL, MEDIA, CHAPTER |
| `reason` | text | Explanation |

---

## Efficient Search (Future)

For libraries exceeding ~100k images, a linear scan over all stored hashes is too slow. Recommended approach for SQLite on Raspberry Pi:

```sql
-- Step 1: SHA256 exact match
SELECT * FROM MediaImage WHERE sha256 = ?

-- Step 2: Candidate lookup via hash prefix bucket
SELECT * FROM ImageFingerprint WHERE hash_value_bucket = ?

-- Step 3: Calculate Hamming distance on candidates only
```

For larger libraries: SQLite + sqlite-vss or FAISS for nearest-neighbour vector search.

---

## Future Enhancements

- Persist fingerprints to SQLite to avoid re-hashing on repeated scans
- Global duplicate detection across books
- Blacklist system — reject known unwanted images on import
- Chapter-level duplicate detection (80%+ page hash sequence overlap)
- CLIP embeddings for semantic matching
- Browser UI for reviewing matches with inline delete
- Auto-clean rules
- "Find all books containing this page" cross-library search
