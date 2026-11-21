import argparse
import os

from flask_sqlalchemy.session import Session
from PIL import Image

from feature_flags import MANAGE_VOLUME
from plugin_methods import plugin_string_arg
from plugin_system import ActionBookSpecificPlugin
from plugins.book_update_stats import UpdateSingleBookStats
from text_utils import is_blank, is_not_blank, clean_string
from thread_utils import TaskWrapper
from number_utils import is_integer
from volume_queries import find_book_by_id


class MaxSizePlugin(ActionBookSpecificPlugin):
    """
    Scan every chapter of a book and resize any WEBP image whose width or
    height exceeds the given limits. Aspect ratio is always preserved.
    At least one of Max Width / Max Height must be provided.
    """
    AI_QUICK_DESCRIPTION = ('Resizes oversized images in one book down to the given max width and/or '
                            'height (aspect ratio preserved); images that already fit are untouched.')
    AI_LONG_DESCRIPTION = (
        'Scans every chapter of a single book and re-encodes any image whose width or height '
        'exceeds the Max Width / Max Height limits, preserving aspect ratio. Images that already '
        'fit are left untouched, and only the oversized files on disk are rewritten. Book ID is '
        'required. Max Width and Max Height are pixel limits; each may be left blank (unbounded) '
        'but at least one must be a positive integer. Book stats are refreshed afterwards.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'bkmaxsz'

    def is_book(self):
        return True

    def get_category(self):
        return 'book'

    def get_sort(self):
        return {'id': 'book_workers', 'sequence': 11}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Max Size'

    def get_action_id(self):
        return 'action.book.max.size'

    def get_action_icon(self):
        return 'photo_size_select_large'

    def get_action_args(self):
        result = super().get_action_args()
        result.append(plugin_string_arg(
            'Max Width', 'max_width',
            'Maximum image width in pixels (leave blank for unbounded)',
            'bkmaxsz',
        ))
        result.append(plugin_string_arg(
            'Max Height', 'max_height',
            'Maximum image height in pixels (leave blank for unbounded)',
            'bkmaxsz',
        ))
        return result

    def process_action_args(self, args):
        errors = []
        w = clean_string(args.get('max_width', ''))
        h = clean_string(args.get('max_height', ''))

        if is_blank(w) and is_blank(h):
            errors.append('At least one of Max Width or Max Height is required')

        if is_not_blank(w):
            if not is_integer(w) or int(w) <= 0:
                errors.append('Max Width must be a positive integer')
            else:
                args['max_width'] = int(w)

        if is_not_blank(h):
            if not is_integer(h) or int(h) <= 0:
                errors.append('Max Height must be a positive integer')
            else:
                args['max_height'] = int(h)

        return errors if errors else None

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def create_task(self, db_session: Session, args):
        book_id = clean_string(args.get('book_id', ''))

        book = find_book_by_id(book_id, db_session)
        if book is None:
            return [f'Book not found: {book_id}']

        max_width = args.get('max_width')   # int or absent
        max_height = args.get('max_height') # int or absent

        return MaxSizeTask(
            'Max Size',
            f'Resizing {book.name}',
            book_id,
            max_width if isinstance(max_width, int) else None,
            max_height if isinstance(max_height, int) else None,
            self.book_storage_folder,
        )


class MaxSizeTask(TaskWrapper):

    def __init__(self, name, description, book_id: str,
                 max_width: int | None, max_height: int | None,
                 book_folder: str):
        super().__init__(name, description)
        self.book_id = book_id
        self.max_width = max_width
        self.max_height = max_height
        self.book_folder = book_folder
        self.ref_book_id = book_id

    def run(self, db_session: Session):
        if is_blank(self.book_folder):
            self.critical('Volume folder is not configured')
            self.set_failure()
            return

        book = find_book_by_id(self.book_id, db_session)
        if book is None:
            self.critical(f'Book not found: {self.book_id}')
            self.set_failure()
            return

        chapters = book.chapters
        total = len(chapters)
        resized_count = 0

        for idx, chapter in enumerate(chapters, 1):
            self.update_progress((idx / total) * 100.0)

            chapter_path = os.path.join(self.book_folder, self.book_id, chapter.chapter_id)
            if not os.path.isdir(chapter_path):
                continue

            for filename in os.listdir(chapter_path):
                if not filename.lower().endswith('.webp'):
                    continue

                path = os.path.join(chapter_path, filename)
                try:
                    with Image.open(path) as img:
                        img.load()
                        w, h = img.size
                        needs_resize = (
                            (self.max_width and w > self.max_width) or
                            (self.max_height and h > self.max_height)
                        )
                        if not needs_resize:
                            continue

                        box = (
                            self.max_width if self.max_width else w,
                            self.max_height if self.max_height else h,
                        )
                        img.thumbnail(box, Image.LANCZOS)
                        img.save(path, format='WEBP', lossless=True)
                        resized_count += 1
                        self.set_worked()
                        if self.can_debug():
                            self.debug(f'Resized {chapter.chapter_id}/{filename}: {w}x{h} → {img.size[0]}x{img.size[1]}')

                except Exception as e:
                    self.warn(f'Could not process {chapter.chapter_id}/{filename}: {e}')

            if self.is_cancelled:
                self.set_warning()
                self.info('Ending early')
                break

        self.info(f'Resized {resized_count} images across {total} chapters')
        self.run_after(UpdateSingleBookStats(
            'Update Cache',
            f'Update {self.book_id} after resize',
            self.book_id,
            False,
            self.book_folder,
        ))
