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
from volume_queries import find_book_by_id, find_chapter_by_id

SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}


class RefreshChapterPlugin(ActionBookSpecificPlugin):
    """
    Open and re-save every image in a chapter to fix corrupted or
    improperly-encoded files without changing content or filenames.
    """
    AI_QUICK_DESCRIPTION = ('Re-saves every image in one chapter (lossless re-encode) to repair '
                            'corrupted or bad files; pixels and filenames are unchanged.')
    AI_LONG_DESCRIPTION = (
        'Opens each image of a single chapter and re-saves it losslessly in place, which '
        'repairs files that are corrupted or were improperly encoded without changing the '
        'visible content or the filenames. Supported extensions are jpg, jpeg, png, webp, bmp '
        'and tiff; webp files stay webp while the others are rewritten as lossless PNG data '
        'under their original filename. Unreadable files are skipped with a warning and do not '
        'abort the task. Book ID, Chapter ID and the chapter folder on disk must all exist. '
        'The book stats cache is refreshed when the chapter is done.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'bkrefchp'

    def is_book(self):
        return True

    def get_category(self):
        return 'book'

    def get_sort(self):
        return {'id': 'book_workers', 'sequence': 10}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Refresh Chapter'

    def get_action_id(self):
        return 'action.book.refresh.chapter'

    def get_action_icon(self):
        return 'refresh'

    def get_action_args(self):
        result = super().get_action_args()
        result.append(plugin_string_arg(
            'Chapter', 'chapter_id',
            'Chapter to refresh, e.g. 0001 or 0012.5',
            'bkrefchp',
        ))
        return result

    def process_action_args(self, args):
        errors = []
        if is_blank(args.get('book_id', '')):
            errors.append('Book ID is required')
        if is_blank(clean_string(args.get('chapter_id', ''))):
            errors.append('Chapter is required')
        return errors if errors else None

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def create_task(self, db_session: Session, args):
        book_id = clean_string(args.get('book_id', ''))
        chapter_id = clean_string(args.get('chapter_id', ''))

        book = find_book_by_id(book_id, db_session)
        if book is None:
            return [f'Book not found: {book_id}']

        chapter = find_chapter_by_id(book_id, chapter_id)
        if chapter is None:
            return [f'Chapter not found: {chapter_id}']

        chapter_path = os.path.join(self.book_storage_folder, book_id, chapter_id)
        if not os.path.isdir(chapter_path):
            return [f'Chapter folder does not exist: {chapter_path}']

        return RefreshChapterTask(
            'Refresh Chapter',
            f'Refreshing {book.name} / {chapter_id}',
            book_id,
            chapter_id,
            self.book_storage_folder,
        )


class RefreshChapterTask(TaskWrapper):

    def __init__(self, name, description, book_id: str, chapter_id: str, book_folder: str):
        super().__init__(name, description)
        self.book_id = book_id
        self.chapter_id = chapter_id
        self.book_folder = book_folder
        self.ref_book_id = book_id

    def run(self, db_session: Session):
        if is_blank(self.book_folder):
            self.critical('Volume folder is not configured')
            self.set_failure()
            return

        chapter_path = os.path.join(self.book_folder, self.book_id, self.chapter_id)
        if not os.path.isdir(chapter_path):
            self.critical(f'Chapter folder not found: {chapter_path}')
            self.set_failure()
            return

        files = sorted(f for f in os.listdir(chapter_path)
                       if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS)
        total = len(files)

        for idx, filename in enumerate(files, 1):
            self.update_percent((idx / total) * 100.0)
            path = os.path.join(chapter_path, filename)
            ext = os.path.splitext(filename)[1].lower()
            fmt = 'WEBP' if ext == '.webp' else 'PNG'
            try:
                with Image.open(path) as img:
                    img.load()
                    img.save(path, format=fmt, lossless=True)
                self.set_worked()
                if self.can_debug():
                    self.debug(f'Refreshed {filename}')
            except Exception as e:
                self.warn(f'Could not refresh {filename}: {e}')

        self.info(f'Refreshed {total} images in {self.chapter_id}')
        self.run_after(UpdateSingleBookStats(
            'Update Cache',
            f'Update {self.book_id} after refresh',
            self.book_id,
            False,
            self.book_folder,
        ))
