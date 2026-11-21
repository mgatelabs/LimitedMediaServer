# image_hashing.py - Image Fingerprinting and Duplicate Detection

This module provides image fingerprinting and cross-chapter duplicate detection for the media library. It is designed to run efficiently on Raspberry Pi hardware by using a sliding memory window rather than loading all images at once.

**Dependency:** requires `imagehash~=4.3.1` (added to `requirements.txt`).

---

## Constants

| Name | Value | Description |
|------|-------|-------------|
| `SUPPORTED_EXTENSIONS` | `.jpg .jpeg .png .webp .bmp .tiff` | File types considered for fingerprinting |
| `CHAPTER_FOLDER_RE` | `^\d{4}(\.\d+)?$` | Folder names treated as chapters (e.g. `0001`, `0012`, `0001.5`) |
| `PHASH_DUPLICATE_THRESHOLD` | `10` | Maximum pHash Hamming distance to consider two images visually identical |

---

## Data Classes

### `ImageDetails`

Holds the fingerprint for a single image file.

| Field | Type | Description |
|-------|------|-------------|
| `width` | int | Image width in pixels |
| `height` | int | Image height in pixels |
| `file_size` | int | File size in bytes |
| `sha256` | str | SHA-256 hex digest of the raw file bytes |
| `phash` | str | Perceptual hash (pHash) |
| `dhash` | str | Difference hash (dHash) |
| `ahash` | str | Average hash (aHash) |

**Method:** `to_dict()` — returns all fields as a plain dict.

---

### `DuplicateMatch`

One image that matched a source image during a scan.

| Field | Type | Description |
|-------|------|-------------|
| `chapter` | str | Chapter folder name |
| `filename` | str | Image filename |
| `phash_distance` | int | Hamming distance between the two pHashes (0 = identical) |

**Method:** `to_dict()`

---

### `DuplicateHit`

A source image paired with all its matches found in other chapters.

| Field | Type | Description |
|-------|------|-------------|
| `source_chapter` | str | Chapter of the source image |
| `source_filename` | str | Filename of the source image |
| `matches` | list[DuplicateMatch] | All images that look like the source |

**Methods:** `add_match(chapter, filename, phash_distance)`, `to_dict()`

---

### `HitMaster`

Single source of truth for all known duplicate groups during a scan. Prevents the same image from being assigned to multiple groups or compared twice.

Internally maintains:
- A list of `DuplicateHit` groups
- A `dict` mapping `(chapter, filename)` → group index for O(1) lookup

**Methods:**

| Method | Description |
|--------|-------------|
| `is_known(chapter, filename)` | Returns `True` if the image already belongs to a group |
| `add_new_group(source_chapter, source_filename, match_chapter, match_filename, phash_distance)` | Creates a new group from a freshly discovered pair; registers both images as known |
| `add_to_existing_group(existing_chapter, existing_filename, new_chapter, new_filename, phash_distance)` | Adds an image to the group that `existing_filename` already belongs to |
| `hits` (property) | Returns a copy of the group list |

---

### `DuplicateScanReport`

Returned by `scan_for_duplicate_chapters()`. Contains all duplicate groups found.

| Field | Type | Description |
|-------|------|-------------|
| `root_folder` | str | The root folder that was scanned |
| `chapters_scanned` | int | Total number of chapter folders found |
| `hits` | list[DuplicateHit] | All duplicate groups |
| `has_duplicates` (property) | bool | `True` if any groups were found |

**Method:** `to_dict()` — returns the full report as a serialisable dict.

---

## Public Functions

### `get_image_details(path) -> ImageDetails`

Fingerprint a single image file.

```python
from image_hashing import get_image_details

details = get_image_details("/media/manga/one-piece/0001/page001.webp")
print(details.phash)       # e.g. "8fa221bb92aa3c11"
print(details.file_size)   # bytes
print(details.to_dict())
```

**Raises:**
- `FileNotFoundError` — path does not exist
- `ValueError` — file cannot be opened as an image

---

### `get_folder_image_details(folder) -> dict[str, ImageDetails]`

Fingerprint every supported image in a folder. Returns a `dict` mapping filename → `ImageDetails`. Files that fail to process are silently skipped.

```python
from image_hashing import get_folder_image_details

pages = get_folder_image_details("/media/manga/one-piece/0001")
for filename, details in pages.items():
    print(filename, details.phash)
```

**Raises:** `NotADirectoryError` if `folder` does not exist.

---

### `scan_for_duplicate_chapters(root_folder, queue_size=10) -> DuplicateScanReport`

Scan a book's root folder for cross-chapter duplicate images. Only subfolders matching `####` or `####.#` are treated as chapters.

**Memory model:** A sliding window (`deque`) of `queue_size` chapters is kept in memory at once. As the 11th chapter is loaded, the oldest drops off. Confirmed duplicate groups are held in `HitMaster` and are never evicted.

**Match logic:**

1. For each image in the current chapter, check `HitMaster.is_known()` — skip if already grouped.
2. Search the window. Skip window images that are already grouped.
3. On the first match found, call `HitMaster.add_new_group()` and stop searching for that image.

**Match criteria:** SHA-256 exact match (byte-identical), or pHash Hamming distance ≤ `PHASH_DUPLICATE_THRESHOLD` (10).

```python
from image_hashing import scan_for_duplicate_chapters

report = scan_for_duplicate_chapters("/media/manga/one-piece")

print(f"Scanned {report.chapters_scanned} chapters")
print(f"Found {len(report.hits)} duplicate groups")

for hit in report.hits:
    print(f"\nGroup: {hit.source_chapter}/{hit.source_filename}")
    for match in hit.matches:
        print(f"  also in {match.chapter}/{match.filename} "
              f"(distance={match.phash_distance})")
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `root_folder` | str | — | Path to the book folder containing chapter subfolders |
| `queue_size` | int | 10 | Number of chapters to hold in the sliding window |

**Raises:** `NotADirectoryError` if `root_folder` does not exist.

---

## Scan Algorithm Walkthrough

Given chapters `[0001, 0002, 0003, ..., 0015]` with `queue_size=10`:

```
Process 0001: window empty, no comparisons. Add 0001 to window.
Process 0002: compare against [0001]. Add 0002 to window.
...
Process 0010: compare against [0001..0009]. Add 0010 to window.
Process 0011: compare against [0002..0010]. 0001 is evicted from window.
...
```

When a match is found between `0011/page001.webp` and `0005/page001.webp`:
- Both are registered in `HitMaster`
- When `0012` is later scanned, both images are skipped immediately

---

## Integration with `volume_routes.py`

The scan is exposed via `POST /scan/duplicates`. See `docs/volume_routes.md` for the full API contract. The route reshapes the `DuplicateScanReport` into a flat `groups` list suitable for a client review UI where the user can select which variants to delete using the existing `POST /remove/image` endpoint.

---

## Tuning

### Adjusting the similarity threshold

Edit `PHASH_DUPLICATE_THRESHOLD` in `image_hashing.py`:

| Value | Effect |
|-------|--------|
| `0` | Exact perceptual match only |
| `5` | Strict — tolerates minor compression differences |
| `10` | Default — tolerates resizing, re-encoding, minor brightness changes |
| `15+` | Loose — may produce false positives on visually distinct images |

### Adjusting window size

Pass `queue_size` to `scan_for_duplicate_chapters()`. The default of 10 is conservative for Raspberry Pi. Increase it if chapters are short and duplicates span a wide range:

```python
report = scan_for_duplicate_chapters(book_folder, queue_size=20)
```

Memory cost is roughly: `queue_size × pages_per_chapter × ~500 bytes per ImageDetails`.
