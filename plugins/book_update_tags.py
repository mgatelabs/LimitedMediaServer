import argparse
import platform

from flask_sqlalchemy.session import Session

from db import Book
from feature_flags import MANAGE_VOLUME
from plugin_methods import plugin_select_arg
from plugin_system import ActionBookSpecificPlugin, ActionBookGeneralPlugin
from plugins.book_update_contents import group_books_by_processor, interleave_books
from plugins.book_volume_processing import VolumeProcessor
from text_utils import is_not_blank, is_blank
from thread_utils import TaskWrapper
from volume_queries import find_book_by_id


class CheckAllTagsTask(ActionBookGeneralPlugin):
    """
    This is used to download new book content from the Internet (All Books).
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id ='bktagall'

    def get_sort(self):
        return {'id': 'books_tags', 'sequence': 0}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_category(self):
        return 'book'

    def get_action_name(self):
        return 'Update Tags'

    def get_action_id(self):
        return 'action.books.tags'

    def get_action_icon(self):
        return 'style'

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def get_action_args(self):

        values = [{"id": "*", "name": "All"}]

        for processor in self.processors:
            values.append({"id": processor.processor_id, "name": processor.processor_name})

        result = super().get_action_args()

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

    def create_task(self, db_session: Session, args):

        results = []

        books = db_session.query(Book).filter(Book.active == True).all()

        processor = args['filter']

        grouped_books = group_books_by_processor(books)
        interleaved_books = interleave_books(grouped_books)

        for book in interleaved_books:
            if processor == '*' or processor == book.processor:
                if is_blank(book.tags):
                    results.append(
                        CheckBookTagsTask("Book Tags", f'Checking: {book.name}', book.id, self.processors, '*'))

        return results


class UpdateSingleTagsTask(ActionBookSpecificPlugin):
    """
    This is used to download new book content from the Internet (Single Book).
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'bktagall'

    def is_book(self):
        return True

    def get_category(self):
        return "book"

    def get_sort(self):
        return {'id': 'book_tags', 'sequence': 0}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Update Tags'

    def get_action_id(self):
        return 'action.book.tags'

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

    def is_ready(self):
        return super().is_ready() and platform.system() == 'Linux'

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def create_task(self, db_session: Session, args):

        book_id = args['book_id']
        results = []

        if is_not_blank(book_id):
            book = find_book_by_id(book_id, db_session)
            if book is not None and book.active:
                return CheckBookTagsTask("Book Tags", f'Checking: {book.name}', book.id, self.processors, '*')

        return results


class CheckBookTagsTask(TaskWrapper):
    def __init__(self, name, description, book_id, processors, processor_filter: str = "*",
                 clean_all: bool = False):
        super().__init__(name, description)
        self.book_id = book_id
        self.processors = processors
        self.processor_filter = processor_filter
        self.clean_all = clean_all
        self.ref_book_id = book_id

    def run(self, db_session: Session):

        book = find_book_by_id(self.book_id, db_session)

        if book is not None:
            bd = VolumeProcessor(self.processors, '', 'PNG', self)
            status = bd.get_tags(book, self.token)
            if status is not None and status:
                self.info('Book tags updates')
                self.set_worked()
                db_session.commit()
        else:
            self.critical('Could not find book: ' + self.book_id)
