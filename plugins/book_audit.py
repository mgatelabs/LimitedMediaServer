import argparse
import datetime
import os
import statistics
from typing import Dict, List, Optional, Set, Tuple

import imagehash
from flask_sqlalchemy.session import Session

from db import Book, Chapter
from feature_flags import MANAGE_VOLUME
from filename_utils import decompress_filenames
from image_hashing import get_image_details, ImageDetails, PHASH_DUPLICATE_THRESHOLD
from plugin_methods import plugin_select_arg, plugin_select_values
from plugin_system import ActionBookGeneralPlugin
from thread_utils import TaskWrapper


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _count_phash_matches(
        a_list: List[ImageDetails],
        b_list: List[ImageDetails],
        threshold: int = PHASH_DUPLICATE_THRESHOLD,
) -> int:
    """Count how many images in a_list have a match in b_list (pHash distance <= threshold).
    Each b-image is consumed at most once."""
    count = 0
    used_b: Set[int] = set()
    for a in a_list:
        for j, b in enumerate(b_list):
            if j in used_b:
                continue
            dist = imagehash.hex_to_hash(a.phash) - imagehash.hex_to_hash(b.phash)
            if dist <= threshold:
                count += 1
                used_b.add(j)
                break
    return count


def _find_decimal_groups(chapters: List[Chapter]) -> List[Tuple[Chapter, List[Chapter]]]:
    """Return (integer_chapter, [decimal_chapters]) pairs where decimal variants exist."""
    chapter_map: Dict[str, Chapter] = {c.chapter_id: c for c in chapters}
    groups = []
    for chapter_id, chapter in chapter_map.items():
        if '.' in chapter_id:
            continue
        decimal_variants = [
            c for cid, c in chapter_map.items()
            if cid.startswith(chapter_id + '.')
        ]
        if decimal_variants:
            groups.append((chapter, decimal_variants))
    return groups


def _same_width(w1: int, w2: int) -> bool:
    return abs(w1 - w2) / max(w1, w2) <= _SPLIT_WIDTH_TOLERANCE


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------

class BookAuditPlugin(ActionBookGeneralPlugin):
    """Read-only audit plugin that scans books for common problems and logs findings."""
    AI_QUICK_DESCRIPTION = ('Read-only audit of books: finds wrong aspect ratios, split images, '
                            'duplicate books and duplicate chapters; logs findings only.')
    AI_LONG_DESCRIPTION = (
        'Runs a read-only diagnostic over the book collection. The mode argument selects one '
        'audit: aspect (images whose aspect ratio deviates from the book median), '
        'split_images (images that were split into vertical slices), dup_books (books with '
        'nearly identical image content) or dup_chapters (chapters that reuse the same images). '
        'The date_limit argument optionally restricts the audit to books updated within the '
        'given number of days. Nothing is modified; findings are written to the task log.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'bkaudit'

    def get_sort(self):
        return {'id': 'books_audit', 'sequence': 10}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Book Audit'

    def get_action_id(self):
        return 'action.book.audit'

    def get_action_icon(self):
        return 'find_in_page'

    def get_action_args(self):
        return [
            plugin_select_arg(
                "Mode", "mode", "aspect",
                plugin_select_values(
                    "Wrong Aspect Ratio", "aspect",
                    "Split Images", "split_images",
                    "Duplicate Books", "dup_books",
                    "Duplicate Chapters", "dup_chapters",
                ),
                "Which audit to run",
                "bkaudit",
            ),
            plugin_select_arg(
                "Date Limit", "date_limit", "0",
                plugin_select_values(
                    "No Limit", "0",
                    "30 Days",  "30",
                    "20 Days",  "20",
                    "10 Days",  "10",
                    "5 Days",   "5",
                    "3 Days",   "3",
                    "2 Days",   "2",
                    "1 Day",    "1",
                ),
                "Only audit books updated within this many days",
                "bkaudit",
            ),
        ]

    def process_action_args(self, args):
        if args.get("mode") not in {"aspect", "split_images", "dup_books", "dup_chapters"}:
            return ["mode must be one of: aspect, split_images, dup_books, dup_chapters"]
        args['date_limit'] = int(args.get('date_limit', '0'))
        return None

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def absorb_config(self, config):
        super().absorb_config(config)

    def create_task(self, db_session: Session, args):
        mode = args.get("mode", "aspect")
        date_limit = args.get('date_limit', 0)
        cutoff = (datetime.date.today() - datetime.timedelta(days=date_limit)) if date_limit else None
        if mode == "split_images":
            return SplitImagesTask("BookAudit", "Split Images Audit", self.book_storage_folder, cutoff)
        elif mode == "dup_books":
            return DupBooksTask("BookAudit", "Duplicate Books Audit", self.book_storage_folder, cutoff)
        elif mode == "dup_chapters":
            return DupChaptersTask("BookAudit", "Duplicate Chapters Audit", self.book_storage_folder, cutoff)
        else:
            return AspectRatioTask("BookAudit", "Aspect Ratio Audit", self.book_storage_folder, cutoff)


# ---------------------------------------------------------------------------
# Task: Wrong Aspect Ratio
# ---------------------------------------------------------------------------

class AspectRatioTask(TaskWrapper):

    def __init__(self, name: str, description: str, book_storage_folder: str,
                 cutoff: Optional[datetime.date] = None):
        super().__init__(name, description)
        self.book_storage_folder = book_storage_folder
        self.cutoff = cutoff

    def run(self, db_session: Session):
        books = db_session.query(Book).filter(Book.active == True).all()
        total = len(books)
        if total == 0:
            self.info("No active books found.")
            return

        for i, book in enumerate(books):
            if self.is_cancelled:
                break
            self.update_progress((i / total) * 100)

            if book.style == 'S':
                continue
            if self.cutoff and (book.last_date is None or book.last_date < self.cutoff):
                continue

            book_folder = os.path.join(self.book_storage_folder, book.id)
            if not os.path.isdir(book_folder):
                self.debug(f"Book folder missing: {book.id}")
                continue

            chapters_sorted = sorted(book.chapters, key=lambda c: c.sequence)
            if not chapters_sorted:
                continue

            # Collect ratios from middle images.
            # Landscape images (ratio > 1.0) are double-page spreads — excluded from
            # the baseline so they don't skew the portrait median upward.
            all_images: List[Tuple[str, str, float]] = []   # (chapter_id, filename, ratio)
            portrait_ratios: List[float] = []

            for chapter in chapters_sorted:
                images = decompress_filenames(chapter.image_names)
                middle_images = images[3:-3] if len(images) > 6 else []
                if not middle_images:
                    continue
                chapter_folder = os.path.join(book_folder, chapter.chapter_id)
                for filename in middle_images:
                    path = os.path.join(chapter_folder, filename)
                    try:
                        details = get_image_details(path)
                        if details.height > 0:
                            ratio = details.width / details.height
                            all_images.append((chapter.chapter_id, filename, ratio))
                            if ratio <= 1.0:
                                portrait_ratios.append(ratio)
                    except (FileNotFoundError, ValueError) as e:
                        self.debug(f"Cannot read {book.id}/{chapter.chapter_id}/{filename}: {e}")

            if not portrait_ratios:
                continue

            normal_ratio = statistics.median(portrait_ratios)

            # Skip books where the portrait baseline is itself very tall — those are
            # naturally scrolling-style content despite being marked page-style.
            if normal_ratio < 0.4:
                self.debug(f"Skipping tall-image book {book.id} (median ratio={normal_ratio:.3f})")
                continue

            # An image is "stacked" if it is more than 3× taller than the normal page.
            # Landscape images are never stacked — skip them.
            threshold = normal_ratio / 3
            bad: Dict[str, List[str]] = {}
            for chapter_id, filename, ratio in all_images:
                if ratio > 1.0:
                    continue
                if ratio < threshold:
                    bad.setdefault(chapter_id, []).append(filename)

            for chapter_id, filenames in bad.items():
                self.warn(
                    f"ASPECT book={book.id} chapter={chapter_id} "
                    f"images=[{', '.join(filenames)}] "
                    f"threshold={threshold:.4f} (normal={normal_ratio:.4f})"
                )

        self.update_progress(100)


# ---------------------------------------------------------------------------
# Task: Split Images (tall+short alternating pairs with matching width)
# ---------------------------------------------------------------------------

# Minimum consecutive alternating pairs required to flag a chapter.
_SPLIT_MIN_PAIRS = 3
# Width tolerance: two images are considered "same width" within this fraction.
_SPLIT_WIDTH_TOLERANCE = 0.02


class SplitImagesTask(TaskWrapper):
    """Detect chapters where images were cut in half unequally.

    Pattern: tall image followed immediately by a shorter image of the same width,
    repeating for at least _SPLIT_MIN_PAIRS consecutive pairs.  Only page-style
    books are checked; scrolling books are skipped.
    """

    def __init__(self, name: str, description: str, book_storage_folder: str,
                 cutoff: Optional[datetime.date] = None):
        super().__init__(name, description)
        self.book_storage_folder = book_storage_folder
        self.cutoff = cutoff

    def run(self, db_session: Session):
        books = db_session.query(Book).filter(Book.active == True).all()
        total = len(books)
        if total == 0:
            self.info("No active books found.")
            return

        for i, book in enumerate(books):
            if self.is_cancelled:
                break
            self.update_progress((i / total) * 100)

            if book.style == 'S':
                continue
            if self.cutoff and (book.last_date is None or book.last_date < self.cutoff):
                continue

            book_folder = os.path.join(self.book_storage_folder, book.id)
            if not os.path.isdir(book_folder):
                self.debug(f"Book folder missing: {book.id}")
                continue

            chapters_sorted = sorted(book.chapters, key=lambda c: c.sequence)
            affected_chapters: List[str] = []

            for chapter in chapters_sorted:
                chapter_folder = os.path.join(book_folder, chapter.chapter_id)
                if not os.path.isdir(chapter_folder):
                    continue

                images = decompress_filenames(chapter.image_names)
                if len(images) < _SPLIT_MIN_PAIRS * 2:
                    continue

                dims: List[Tuple[str, int, int]] = []
                for filename in images:
                    path = os.path.join(chapter_folder, filename)
                    try:
                        d = get_image_details(path)
                        if d.width > 0 and d.height > 0:
                            dims.append((filename, d.width, d.height))
                    except (FileNotFoundError, ValueError):
                        pass

                if len(dims) < _SPLIT_MIN_PAIRS * 2:
                    continue

                pair_run = 0
                chapter_flagged = False

                for idx in range(0, len(dims) - 1, 2):
                    fn_a, w_a, h_a = dims[idx]
                    fn_b, w_b, h_b = dims[idx + 1]
                    if _same_width(w_a, w_b) and h_b < h_a * 0.5:
                        pair_run += 1
                        if pair_run >= _SPLIT_MIN_PAIRS and not chapter_flagged:
                            affected_chapters.append(chapter.chapter_id)
                            chapter_flagged = True
                    else:
                        pair_run = 0

            if affected_chapters:
                self.warn(
                    f"SPLIT_IMAGES book={book.id} chapters=[{', '.join(affected_chapters)}]"
                )

        self.update_progress(100)


# ---------------------------------------------------------------------------
# Task: Duplicate Books
# ---------------------------------------------------------------------------

class DupBooksTask(TaskWrapper):

    def __init__(self, name: str, description: str, book_storage_folder: str,
                 cutoff: Optional[datetime.date] = None):
        super().__init__(name, description)
        self.book_storage_folder = book_storage_folder
        self.cutoff = cutoff

    def run(self, db_session: Session):
        books = db_session.query(Book).filter(Book.active == True).all()
        total = len(books)
        if total == 0:
            self.info("No active books found.")
            return

        fingerprints: Dict[str, List[ImageDetails]] = {}

        for i, book in enumerate(books):
            if self.is_cancelled:
                break
            self.update_progress((i / total) * 50)

            if self.cutoff and (book.last_date is None or book.last_date < self.cutoff):
                continue

            chapters_sorted = sorted(book.chapters, key=lambda c: c.sequence)
            if not chapters_sorted:
                continue

            ref_chapter = next(
                (c for c in chapters_sorted if c.chapter_id == '0001'),
                chapters_sorted[0]
            )
            chapter_folder = os.path.join(self.book_storage_folder, book.id, ref_chapter.chapter_id)
            if not os.path.isdir(chapter_folder):
                continue

            images = decompress_filenames(ref_chapter.image_names)
            details_list: List[ImageDetails] = []
            for filename in images[:10]:
                path = os.path.join(chapter_folder, filename)
                try:
                    details_list.append(get_image_details(path))
                except (FileNotFoundError, ValueError):
                    pass

            if details_list:
                fingerprints[book.id] = details_list

        book_ids = list(fingerprints.keys())
        seen_as_source: Set[str] = set()

        for i, book_a_id in enumerate(book_ids):
            if self.is_cancelled:
                break
            self.update_progress(50 + (i / max(len(book_ids), 1)) * 50)

            if book_a_id in seen_as_source:
                continue

            a_details = fingerprints[book_a_id]
            for book_b_id in book_ids[i + 1:]:
                b_details = fingerprints[book_b_id]
                match_count = _count_phash_matches(a_details, b_details)
                if match_count >= 6:
                    self.warn(
                        f"DUP_BOOKS book_a={book_a_id} book_b={book_b_id} "
                        f"matches={match_count}/{min(len(a_details), len(b_details))}"
                    )
                    seen_as_source.add(book_a_id)
                    break

        self.update_progress(100)


# ---------------------------------------------------------------------------
# Task: Duplicate Chapters
# ---------------------------------------------------------------------------

class DupChaptersTask(TaskWrapper):

    def __init__(self, name: str, description: str, book_storage_folder: str,
                 cutoff: Optional[datetime.date] = None):
        super().__init__(name, description)
        self.book_storage_folder = book_storage_folder
        self.cutoff = cutoff

    def run(self, db_session: Session):
        books = db_session.query(Book).filter(Book.active == True).all()
        total = len(books)
        if total == 0:
            self.info("No active books found.")
            return

        for i, book in enumerate(books):
            if self.is_cancelled:
                break
            self.update_progress((i / total) * 100)

            if self.cutoff and (book.last_date is None or book.last_date < self.cutoff):
                continue

            book_folder = os.path.join(self.book_storage_folder, book.id)
            if not os.path.isdir(book_folder):
                continue

            groups = _find_decimal_groups(book.chapters)
            if not groups:
                continue

            for int_chapter, decimal_chapters in groups:
                int_folder = os.path.join(book_folder, int_chapter.chapter_id)
                int_images = decompress_filenames(int_chapter.image_names)
                int_details: List[ImageDetails] = []
                for filename in int_images:
                    path = os.path.join(int_folder, filename)
                    try:
                        int_details.append(get_image_details(path))
                    except (FileNotFoundError, ValueError):
                        pass

                dec_details: List[ImageDetails] = []
                for dec_chapter in decimal_chapters:
                    dec_folder = os.path.join(book_folder, dec_chapter.chapter_id)
                    dec_images = decompress_filenames(dec_chapter.image_names)
                    for filename in dec_images:
                        path = os.path.join(dec_folder, filename)
                        try:
                            dec_details.append(get_image_details(path))
                        except (FileNotFoundError, ValueError):
                            pass

                if not int_details or not dec_details:
                    continue

                dec_matches = _count_phash_matches(dec_details, int_details)
                smaller = min(len(dec_details), len(int_details))
                overlap_pct = dec_matches / smaller

                if overlap_pct >= 0.90:
                    dec_ids = ", ".join(c.chapter_id for c in decimal_chapters)
                    self.warn(
                        f"DUP_CHAPTERS book={book.id} int_chapter={int_chapter.chapter_id} "
                        f"dec_chapters=[{dec_ids}] overlap={overlap_pct * 100:.1f}% "
                        f"({dec_matches}/{smaller} images matched)"
                    )

        self.update_progress(100)
