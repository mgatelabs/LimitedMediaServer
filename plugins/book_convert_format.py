import argparse
import os.path

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_VOLUME
from image_utils import convert_images_to_format
from plugin_system import ActionBookSpecificPlugin
from plugins.book_update_stats import UpdateSingleBookStats
from text_utils import is_not_blank, is_blank
from thread_utils import TaskWrapper
from volume_queries import find_book_by_id


class ConvertFormatPlugin(ActionBookSpecificPlugin):
    """
    Convert the chapters from chapter-X to 000X
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'bkconvfmt'

    def is_book(self):
        return True

    def get_category(self):
        return "book"

    def get_sort(self):
        return {'id': 'book_format_convert', 'sequence': 0}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Convert Format'

    def get_action_id(self):
        return 'action.convert.format'

    def get_action_icon(self):
        return 'style'

    def get_action_args(self):

        result = super().get_action_args()

        return result

    def process_action_args(self, args):
        results = []

        if len(results) > 0:
            return results

        return None

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def create_task(self, db_session: Session, args):

        book_id = args['book_id']
        results = []

        if is_not_blank(book_id):
            book = find_book_by_id(book_id, db_session)
            if book is not None:
                return ConvertFormatTask("Converting Format", f'Converting: {book.name}', book.id,
                                         self.book_storage_folder, self.book_storage_format)

        return results


class ConvertFormatTask(TaskWrapper):
    def __init__(self, name, description, book_id, book_folder, storage_format: str):
        super().__init__(name, description)
        self.book_id = book_id
        self.book_folder = book_folder
        self.storage_format = storage_format

    def run(self, db_session: Session):

        if is_blank(self.book_folder):
            self.critical('volume folder is required')
            self.set_failure()
            return

        book = find_book_by_id(self.book_id, db_session)

        converted = 0

        if book is not None:
            chapters = book.chapters

            total = len(chapters)
            count = 0

            for chapter in chapters:
                count = count + 1
                self.update_progress((count / total) * 100.0)

                identified_folder = os.path.join(self.book_folder, self.book_id, chapter.chapter_id)
                if os.path.exists(identified_folder) and os.path.isdir(identified_folder):
                    if self.can_debug():
                        self.debug(f'Working on {chapter.chapter_id}')
                    if convert_images_to_format(identified_folder, self.storage_format, self):
                        self.set_worked()
                        converted = converted + 1

                if self.is_cancelled:
                    self.set_warning()
                    self.info('Ending Early')
                    break

            self.info(f'Converted {converted} Chapters')

            self.run_after(UpdateSingleBookStats("Update", f'Update {self.book_id} Definition', self.book_id,
                                                 False, self.book_folder))

        else:
            self.critical('Could not find book: ' + self.book_id)
