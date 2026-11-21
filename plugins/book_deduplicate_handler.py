import argparse
import json
import os

from flask_sqlalchemy.session import Session

from constants import PROPERTY_SERVER_VOLUME_FOLDER
from feature_flags import MANAGE_VOLUME
from image_hashing import scan_for_duplicate_chapters
from plugin_system import ActionBookSpecificPlugin
from thread_utils import TaskWrapper


class BookDeduplicatePlugin(ActionBookSpecificPlugin):
    AI_QUICK_DESCRIPTION = ('Read-only scan of one book: detects duplicate pages across its chapters '
                            'and logs a JSON report; nothing is deleted or modified.')
    AI_LONG_DESCRIPTION = (
        'Runs a perceptual-hash scan over the chapters of a single book looking for duplicate '
        'images (pages repeated within or across chapters). A JSON report is written to the '
        'task log listing the flagged chapter images. Nothing is deleted, moved or modified. '
        'Book ID is required and the book folder must exist on disk.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'bkdedup'
        self.available_to_menu = False

    def get_sort(self):
        return {'id': 'book_workers', 'sequence': 20}

    def get_category(self):
        return 'book'

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Scan Duplicate Images'

    def get_action_id(self):
        return 'action.book.deduplicate'

    def get_action_icon(self):
        return 'find_replace'

    def get_action_args(self):
        return super().get_action_args()

    def process_action_args(self, args):
        return None

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def absorb_config(self, config):
        super().absorb_config(config)
        self.book_storage_folder = config[PROPERTY_SERVER_VOLUME_FOLDER]

    def create_task(self, db_session: Session, args):
        book_id = args['book_id']
        return BookDeduplicateTask(
            'BookDeduplicate', f'Scan duplicates: {book_id}',
            book_id, self.book_storage_folder,
        )


class BookDeduplicateTask(TaskWrapper):

    def __init__(self, name: str, description: str, book_id: str, book_storage_folder: str):
        super().__init__(name, description)
        self.book_id = book_id
        self.book_storage_folder = book_storage_folder
        self.ref_book_id = book_id
        # This is not a simple request, it should run ASAP
        self.priority = 0

    def run(self, db_session: Session):
        book_folder = os.path.join(self.book_storage_folder, self.book_id)

        if not os.path.isdir(book_folder):
            self.error(f'Book folder not found: {book_folder}')
            self.set_failure()
            return

        report = scan_for_duplicate_chapters(
            book_folder,
            queue_size=20,
            task_wrapper=self,
        )

        self.info(json.dumps(report.to_dict()), _json=True)

        if report.has_duplicates:
            self.set_worked()
