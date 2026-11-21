import os
import hashlib
import re
from collections import deque
from typing import TYPE_CHECKING

import imagehash
from PIL import Image

if TYPE_CHECKING:
    from thread_utils import TaskWrapper

SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}
CHAPTER_FOLDER_RE = re.compile(r'^\d{4}(\.\d+)?$')

PHASH_DUPLICATE_THRESHOLD = 10


# ---------------------------------------------------------------------------
# Core data classes
# ---------------------------------------------------------------------------

class ImageDetails:
    def __init__(self, width: int, height: int, file_size: int, sha256: str,
                 phash: str, dhash: str, ahash: str):
        self.width = width
        self.height = height
        self.file_size = file_size
        self.sha256 = sha256
        self.phash = phash
        self.dhash = dhash
        self.ahash = ahash

    def to_dict(self) -> dict:
        return {
            'width': self.width,
            'height': self.height,
            'file_size': self.file_size,
            'sha256': self.sha256,
            'phash': self.phash,
            'dhash': self.dhash,
            'ahash': self.ahash,
        }


class DuplicateMatch:
    """One image that matches the source image."""
    def __init__(self, chapter: str, filename: str, phash_distance: int):
        self.chapter = chapter
        self.filename = filename
        self.phash_distance = phash_distance

    def to_dict(self) -> dict:
        return {
            'chapter': self.chapter,
            'filename': self.filename,
            'phash_distance': self.phash_distance,
        }


class DuplicateHit:
    """
    A source image with one or more matching images found in other chapters.
    The matches list contains every image that looks like the source.
    """
    def __init__(self, source_chapter: str, source_filename: str):
        self.source_chapter = source_chapter
        self.source_filename = source_filename
        self.matches: list[DuplicateMatch] = []

    def add_match(self, chapter: str, filename: str, phash_distance: int):
        self.matches.append(DuplicateMatch(chapter, filename, phash_distance))

    def to_dict(self) -> dict:
        return {
            'source_chapter': self.source_chapter,
            'source_filename': self.source_filename,
            'matches': [m.to_dict() for m in self.matches],
        }


class HitMaster:
    """
    Single source of truth for all known duplicate groups.

    Tracks every (chapter, filename) pair that has already been assigned to a
    group so that the same image is never processed twice. Stores ImageDetails
    for every known image so that later chapters can match against already-evicted
    window entries directly, without relying on the sliding window.
    """

    def __init__(self):
        self._hits: list[DuplicateHit] = []
        # Maps (chapter, filename) -> index in _hits for O(1) lookup
        self._known: dict[tuple[str, str], int] = {}
        # Maps (chapter, filename) -> ImageDetails for cross-window matching
        self._details: dict[tuple[str, str], ImageDetails] = {}

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def is_known(self, chapter: str, filename: str) -> bool:
        """Return True if this image already belongs to a group."""
        return (chapter, filename) in self._known

    def find_match(self, details: ImageDetails) -> tuple[str, str] | None:
        """
        Search all known images for a duplicate of details.
        Returns (chapter, filename) of the first match found, or None.
        """
        for key, known_details in self._details.items():
            if _is_duplicate(details, known_details):
                return key
        return None

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_new_group(self, source_chapter: str, source_filename: str,
                      source_details: ImageDetails,
                      match_chapter: str, match_filename: str,
                      match_details: ImageDetails,
                      phash_distance: int) -> None:
        """Create a new duplicate group from a freshly discovered pair."""
        hit = DuplicateHit(source_chapter, source_filename)
        hit.add_match(match_chapter, match_filename, phash_distance)
        idx = len(self._hits)
        self._hits.append(hit)
        self._known[(source_chapter, source_filename)] = idx
        self._known[(match_chapter, match_filename)] = idx
        self._details[(source_chapter, source_filename)] = source_details
        self._details[(match_chapter, match_filename)] = match_details

    def add_to_existing_group(self, existing_chapter: str, existing_filename: str,
                               new_chapter: str, new_filename: str,
                               new_details: ImageDetails,
                               phash_distance: int) -> None:
        """Add new_filename to the group that existing_filename already belongs to."""
        idx = self._known[(existing_chapter, existing_filename)]
        self._hits[idx].add_match(new_chapter, new_filename, phash_distance)
        self._known[(new_chapter, new_filename)] = idx
        self._details[(new_chapter, new_filename)] = new_details

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @property
    def hits(self) -> list[DuplicateHit]:
        return list(self._hits)


class DuplicateScanReport:
    """
    Returned by scan_for_duplicate_chapters(). Contains all duplicate hits
    found across the scanned chapter folders. Use to_dict() for serialisation
    or iterate hits directly.
    """
    def __init__(self, root_folder: str, chapters_scanned: int):
        self.root_folder = root_folder
        self.chapters_scanned = chapters_scanned
        self.hits: list[DuplicateHit] = []

    def add_hit(self, hit: DuplicateHit):
        self.hits.append(hit)

    @property
    def has_duplicates(self) -> bool:
        return len(self.hits) > 0

    def to_dict(self) -> dict:
        return {
            'root_folder': self.root_folder,
            'chapters_scanned': self.chapters_scanned,
            'duplicate_count': len(self.hits),
            'hits': [h.to_dict() for h in self.hits],
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_for_duplicate_chapters(root_folder: str,
                                 queue_size: int = 6,
                                 chapter_filter: set[str] | None = None,
                                 task_wrapper: 'TaskWrapper | None' = None) -> DuplicateScanReport:
    """
    Walk root_folder looking for chapter subfolders (#### or ####.# naming).
    Fingerprint each chapter's images with a sliding window of queue_size
    chapters kept in memory at once. Compare every new chapter against:
      1. All images already registered in HitMaster (survives window eviction).
      2. Ungrouped images in the sliding window.

    This ensures a recurring image (e.g. a credit page) that first appears in
    chapter 0001 is still recognised and joined to its existing group when it
    reappears in chapter 0020, even if chapter 0001 has long since left the window.

    chapter_filter: optional set of chapter folder names to scan. When provided,
    only folders whose names are in the set are processed; all others are skipped.

    task_wrapper: optional TaskWrapper (or NoOpTaskWrapper) for progress reporting
    and cancellation. When provided, update_progress() tracks overall chapter
    progress, update_percent() tracks per-chapter image fingerprinting, and
    is_cancelled is checked before each chapter.

    Returns a DuplicateScanReport listing every cross-chapter duplicate found.
    """
    from thread_utils import NoOpTaskWrapper
    tw = task_wrapper if task_wrapper is not None else NoOpTaskWrapper()

    if not os.path.isdir(root_folder):
        raise NotADirectoryError(f"Not a directory: {root_folder}")

    chapter_folders = sorted(
        name for name in os.listdir(root_folder)
        if os.path.isdir(os.path.join(root_folder, name))
        and CHAPTER_FOLDER_RE.match(name)
    )

    if chapter_filter:
        chapter_folders = [name for name in chapter_folders if name in chapter_filter]

    total = len(chapter_folders)
    master = HitMaster()

    # Sliding window: deque of (chapter_name, {filename: ImageDetails})
    window: deque[tuple[str, dict[str, ImageDetails]]] = deque(maxlen=queue_size)

    for idx, chapter_name in enumerate(chapter_folders):
        if tw.is_cancelled:
            break

        tw.update_progress((idx / total) * 100.0 if total else 0.0)
        tw.update_percent(0.0)

        chapter_path = os.path.join(root_folder, chapter_name)
        current_pages = get_folder_image_details(chapter_path)
        tw.update_percent(100.0)

        _compare_chapter_to_window(chapter_name, current_pages, window, master)

        window.append((chapter_name, current_pages))

    tw.update_progress(100.0)
    tw.update_percent(100.0)

    report = DuplicateScanReport(root_folder, len(chapter_folders))
    for hit in master.hits:
        report.add_hit(hit)
    return report


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compare_chapter_to_window(
        current_chapter: str,
        current_pages: dict[str, ImageDetails],
        window: deque,
        master: HitMaster,
) -> None:
    """
    For each image in current_chapter:
      1. Skip if already grouped (is_known).
      2. Search HitMaster's known images first — catches matches whose original
         chapter has already scrolled out of the window.
      3. If no HitMaster match, search the window for an ungrouped duplicate.
         On a match, create a new group.
    """
    for current_filename, current_details in current_pages.items():

        if master.is_known(current_chapter, current_filename):
            continue

        # --- Priority 1: check against all already-known (possibly evicted) images ---
        match_key = master.find_match(current_details)
        if match_key is not None:
            match_chapter, match_filename = match_key
            distance = _phash_distance(
                current_details, master._details[match_key])
            master.add_to_existing_group(
                match_chapter, match_filename,
                current_chapter, current_filename,
                current_details,
                distance,
            )
            continue

        # --- Priority 2: search the window for a new, ungrouped duplicate ---
        for window_chapter, window_pages in window:
            found = False
            for window_filename, window_details in window_pages.items():
                if master.is_known(window_chapter, window_filename):
                    continue
                if not _is_duplicate(current_details, window_details):
                    continue

                distance = _phash_distance(current_details, window_details)
                master.add_new_group(
                    window_chapter, window_filename, window_details,
                    current_chapter, current_filename, current_details,
                    distance,
                )
                found = True
                break

            if found:
                break


def _is_duplicate(a: ImageDetails, b: ImageDetails) -> bool:
    if a.sha256 == b.sha256:
        return True
    return _phash_distance(a, b) <= PHASH_DUPLICATE_THRESHOLD


def _phash_distance(a: ImageDetails, b: ImageDetails) -> int:
    return imagehash.hex_to_hash(a.phash) - imagehash.hex_to_hash(b.phash)


# ---------------------------------------------------------------------------
# File-level functions
# ---------------------------------------------------------------------------

def get_folder_image_details(folder: str) -> dict[str, ImageDetails]:
    """
    Return a dict mapping filename -> ImageDetails for every supported image in folder.
    Files that cannot be processed are silently skipped.
    """
    if not os.path.isdir(folder):
        raise NotADirectoryError(f"Not a directory: {folder}")

    result = {}
    for filename in os.listdir(folder):
        if os.path.splitext(filename)[1].lower() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            result[filename] = get_image_details(os.path.join(folder, filename))
        except (FileNotFoundError, ValueError):
            pass
    return result


def get_image_details(path: str) -> ImageDetails:
    """
    Return fingerprint details for an image file.

    Raises FileNotFoundError if the path does not exist.
    Raises ValueError if the file cannot be opened as an image.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")

    file_size = os.path.getsize(path)

    with open(path, 'rb') as f:
        sha256 = hashlib.sha256(f.read()).hexdigest()

    try:
        with Image.open(path) as img:
            img.load()
            width, height = img.size
            ph = str(imagehash.phash(img))
            dh = str(imagehash.dhash(img))
            ah = str(imagehash.average_hash(img))
    except Exception as e:
        raise ValueError(f"Could not process image '{path}': {e}")

    return ImageDetails(
        width=width,
        height=height,
        file_size=file_size,
        sha256=sha256,
        phash=ph,
        dhash=dh,
        ahash=ah,
    )
