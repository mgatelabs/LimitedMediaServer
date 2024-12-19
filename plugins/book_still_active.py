import argparse
import platform

from flask_sqlalchemy.session import Session

from constants import PROPERTY_SERVER_VOLUME_FOLDER, APP_KEY_PROCESSORS
from db import Book
from feature_flags import MANAGE_VOLUME
from plugin_methods import plugin_select_arg
from plugin_system import ActionPlugin, ActionBookPlugin
from plugins.book_update_contents import group_books_by_processor, interleave_books
from plugins.book_volume_processing import VolumeProcessor
from text_utils import is_not_blank, is_blank
from thread_utils import TaskWrapper
from volume_queries import find_book_by_id

class CheckAllStatusTask(ActionPlugin):
    """
    This is used to download new book content from the Internet (All Books).
    """

    def __init__(self):
        super().__init__()
        self.processors = []
        self.prefix_lang_id = 'bkact'

    def get_sort(self):
        return {'id': 'books_still_active', 'sequence': 0}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_category(self):
        return 'book'

    def get_action_name(self):
        return 'Check Book Status'

    def get_action_id(self):
        return 'action.books.status'

    def get_action_icon(self):
        return 'toggle_on'

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def get_action_args(self):

        values = [{"id": "*", "name": "All"}]

        for processor in self.processors:
            values.append({"id": processor.processor_id, "name": processor.processor_name})

        result = []

        result.append(
            plugin_select_arg('Filter', 'filter', '*', values, "When not *, only Processors that match will execute.",
                              'book'))

        return result

    def process_action_args(self, args):
        results = []

        if 'filter' not in args or args['filter'] is None or args['filter'] == '':
            results.append('filter is required')

        if len(results) > 0:
            return results

        return None

    def is_ready(self):
        return platform.system() == 'Linux'

    def absorb_config(self, config):
        self.processors = config[APP_KEY_PROCESSORS]

    def create_task(self, db_session: Session, args):

        results = []

        books = db_session.query(Book).filter(Book.active == True).all()

        processor = args['filter']

        grouped_books = group_books_by_processor(books)
        interleaved_books = interleave_books(grouped_books)

        for book in interleaved_books:
            if processor == '*' or processor == book.processor:
                results.append(
                   CheckBookStatusTask("BookStatus", f'Checking: {book.name}', book.id, self.processors, '*'))

        return results


class UpdateSingleStatusTask(ActionBookPlugin):
    """
    This is used to download new book content from the Internet (Single Book).
    """

    def __init__(self):
        super().__init__()
        self.processors = []
        self.prefix_lang_id = 'bkact'

    def is_book(self):
        return True

    def get_category(self):
        return "book"

    def get_sort(self):
        return {'id': 'book_status', 'sequence': 0}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Check Book Status'

    def get_action_id(self):
        return 'action.book.status'

    def get_action_icon(self):
        return 'toggle_on'

    def get_action_args(self):

        result = super().get_action_args()

        return result

    def process_action_args(self, args):
        results = []

        if len(results) > 0:
            return results

        return None

    def absorb_config(self, config):
        self.processors = config[APP_KEY_PROCESSORS]

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def create_task(self, db_session: Session, args):

        book_id = args['book_id']
        results = []

        if is_not_blank(book_id):
            book = find_book_by_id(book_id, db_session)
            if book is not None and book.active:
                return CheckBookStatusTask("Book Status", f'Checking: {book.name}', book.id, self.processors, '*')

        return results


class CheckBookStatusTask(TaskWrapper):
    def __init__(self, name, description, book_id, processors, processor_filter: str = "*",
                 clean_all: bool = False):
        super().__init__(name, description)
        self.book_id = book_id
        self.processors = processors
        self.processor_filter = processor_filter
        self.clean_all = clean_all

    def run(self, db_session: Session):

        book = find_book_by_id(self.book_id, db_session)

        if book is not None:
            self.debug('Found book definition : ' + self.book_id)
            bd = VolumeProcessor(self.processors, '', self)
            status = bd.ia_active(book, self.token)
            if status is not None and not status:
                self.info('Book no longer active')
                self.set_worked()
                db_session.commit()
        else:
            self.critical('Could not find book: ' + self.book_id)
