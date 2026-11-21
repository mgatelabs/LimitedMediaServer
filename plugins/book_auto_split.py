import argparse
import os
import shutil

from flask_sqlalchemy.session import Session
from PIL import Image

from feature_flags import MANAGE_VOLUME
from file_utils import temporary_folder
from plugin_methods import plugin_string_arg
from plugin_system import ActionBookSpecificPlugin
from plugins.book_update_stats import UpdateSingleBookStats
from text_utils import is_blank, clean_string
from thread_utils import TaskWrapper
from number_utils import is_integer
from volume_queries import find_book_by_id


class AutoSplitPlugin(ActionBookSpecificPlugin):
    """
    Split excessively tall WEBP images in a scroll-style book into uniform
    vertical slices (max_height px each), then renumber every image in each
    chapter sequentially starting at 0001.webp.
    """
    AI_QUICK_DESCRIPTION = ('Destructive: splits tall images in a scroll-style book into uniform '
                            'vertical slices and renumbers all chapter images from 0001.webp.')
    AI_LONG_DESCRIPTION = (
        'For a scroll-style (S) book, every image taller than max_height is cut into uniform '
        'vertical slices and rewritten; all other images are kept as-is. After splitting, every '
        'image in every chapter is renamed sequentially starting at 0001.webp, so existing '
        'filenames change. Book ID is required and the book must be scroll-style. '
        'Max Slice Height is the pixel height of the output slices; leave blank for the '
        'default 2000, minimum 100. This action cannot be undone.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'bkautospl'

    def is_book(self):
        return True

    def get_category(self):
        return 'book'

    def get_sort(self):
        return {'id': 'book_workers', 'sequence': 12}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Auto Split'

    def get_action_id(self):
        return 'action.book.auto.split'

    def get_action_icon(self):
        return 'call_split'

    def get_action_args(self):
        result = super().get_action_args()
        result.append(plugin_string_arg(
            'Max Slice Height', 'max_height',
            'Pixel height of each output slice (leave blank for 2000, must be >= 100)',
            'bkautospl',
        ))
        return result

    def process_action_args(self, args):
        errors = []
        h = clean_string(args.get('max_height', ''))

        if is_blank(h):
            args['max_height'] = 2000
        else:
            if not is_integer(h) or int(h) < 100:
                errors.append('Max Slice Height must be an integer \u2265 100')
            else:
                args['max_height'] = int(h)

        book_id = clean_string(args.get('book_id', ''))
        if is_blank(book_id):
            errors.append('Book ID is required')
        else:
            book = find_book_by_id(book_id)
            if book is None:
                errors.append(f'Book not found: {book_id}')
            elif book.style != 'S':
                errors.append('Book is not a scroll-style book')

        return errors if errors else None

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def create_task(self, db_session: Session, args):
        book_id = clean_string(args.get('book_id', ''))

        book = find_book_by_id(book_id, db_session)
        if book is None or book.style != 'S':
            return None

        max_height = args.get('max_height')

        return AutoSplitTask(
            'Auto Split',
            f'Splitting tall images in {book.name}',
            book_id,
            max_height if isinstance(max_height, int) else 2000,
            self.book_storage_folder,
        )


class AutoSplitTask(TaskWrapper):

    def __init__(self, name, description, book_id: str, max_height: int, book_folder: str):
        super().__init__(name, description)
        self.book_id = book_id
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

        if book.style != 'S':
            self.critical(f'Book {self.book_id} is not a scroll-style book')
            self.set_failure()
            return

        chapters = book.chapters
        total = len(chapters)
        images_split = 0
        slices_out = 0

        for idx, chapter in enumerate(chapters, 1):
            self.update_progress((idx / total) * 100.0)

            chapter_path = os.path.join(self.book_folder, self.book_id, chapter.chapter_id)
            if not os.path.isdir(chapter_path):
                continue

            webp_files = sorted(
                f for f in os.listdir(chapter_path)
                if f.lower().endswith('.webp') and os.path.isfile(os.path.join(chapter_path, f))
            )
            if not webp_files:
                continue

            cancelled = False
            failed = False
            staged = []
            split_here = 0
            slices_here = 0

            with temporary_folder(self.book_folder, self) as temp_folder:
                for filename in webp_files:
                    if self.is_cancelled:
                        self.set_warning()
                        self.info('Ending early')
                        cancelled = True
                        break

                    path = os.path.join(chapter_path, filename)
                    try:
                        with Image.open(path) as img:
                            img.load()
                            w, h = img.size

                            base_idx = len(staged) + 1
                            if h <= self.max_height:
                                temp_name = f'__orig_{base_idx}.webp'
                                shutil.copy2(path, os.path.join(temp_folder, temp_name))
                                staged.append(temp_name)
                            else:
                                count = (h + self.max_height - 1) // self.max_height
                                for i in range(count):
                                    y0 = i * self.max_height
                                    y1 = min(y0 + self.max_height, h)
                                    temp_name = f'__split_{base_idx}_{i + 1}.webp'
                                    box = img.crop((0, y0, w, y1))
                                    box.save(os.path.join(temp_folder, temp_name),
                                             format='WEBP', lossless=True)
                                    del box
                                    staged.append(temp_name)
                                split_here += 1
                                slices_here += count
                                self.set_worked()
                                if self.can_debug():
                                    self.debug(f'Split {chapter.chapter_id}/{filename}: {w}x{h} into {count} slices')

                    except Exception as e:
                        self.warn(f'Could not process {chapter.chapter_id}/{filename}: {e}')
                        failed = True
                        break

                if staged and not cancelled and not failed:
                    self._commit(chapter_path, temp_folder, staged)

            if cancelled or failed:
                break

            self.info(f'Split {split_here} images into {slices_here} slices in {chapter.chapter_id}')
            images_split += split_here
            slices_out += slices_here

        self.info(f'Split {images_split} images into {slices_out} slices across {total} chapters')
        self.run_after(UpdateSingleBookStats(
            'Update Cache',
            f'Update {self.book_id} after split',
            self.book_id,
            False,
            self.book_folder,
        ))

    @staticmethod
    def _commit(chapter_path: str, temp_folder: str, staged: list[str]) -> None:
        total = len(staged)
        pad = max(4, len(str(total)))
        final_names = set()

        for i, temp_name in enumerate(staged, 1):
            final_name = f'{str(i).zfill(pad)}.webp'
            final_path = os.path.join(chapter_path, final_name)
            if os.path.exists(final_path):
                os.remove(final_path)
            shutil.move(os.path.join(temp_folder, temp_name), final_path)
            final_names.add(final_name)

        for entry in os.listdir(chapter_path):
            if entry.lower().endswith('.webp') and entry not in final_names:
                try:
                    os.remove(os.path.join(chapter_path, entry))
                except OSError:
                    pass
