import argparse
import platform
from typing import Optional

from flask_sqlalchemy.session import Session

from db import Book
from feature_flags import MANAGE_VOLUME
from plugin_methods import plugin_select_arg
from plugin_system import ActionBookSpecificPlugin, ActionBookGeneralPlugin
from plugins.book_update_contents import group_books_by_processor, interleave_books
from plugins.book_volume_processing import VolumeProcessor
from text_utils import is_not_blank
from thread_utils import TaskWrapper
from volume_queries import find_book_by_id


def processor_for_id(processors, processor_id: str) -> Optional["CustomDownloadInterface"]:
    for processor in processors:
        if processor.processor_id == processor_id:
            return processor
    return None


class CheckAllStatusTask(ActionBookGeneralPlugin):
    """
    This is used to download new book content from the Internet (All Books).
    """
    AI_QUICK_DESCRIPTION = ('Checks every active book against its source site and deactivates '
                            'books that are no longer being updated (optionally by processor).')
    AI_LONG_DESCRIPTION = (
        'Runs over all active books (or only those of a processor selected via Filter) and asks '
        'each book\'s source site, through its processor, whether the series is still being '
        'updated. A book whose site reports it is finished or offline is marked inactive in the '
        'database. No chapters or images are downloaded or changed. The all-books variant only '
        'runs on a Linux server. Filter is a required select (default All); per-processor book '
        'ids are the values to choose from when not All.')

    def __init__(self):
        super().__init__()
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
        return super().is_ready() and platform.system() == 'Linux'

    def create_task(self, db_session: Session, args):

        results = []

        books = db_session.query(Book).filter(Book.active == True).all()

        processor = args['filter']

        grouped_books = group_books_by_processor(books)
        interleaved_books = interleave_books(grouped_books)

        for book in interleaved_books:
            if processor == '*' or processor == book.processor:
                book_processor = processor_for_id(self.processors, book.processor)

                results.append(
                    CheckBookStatusTask("BookStatus", f'Checking: {book.name}', book.id, book_processor,
                                        self.processors))

        return results


class UpdateSingleStatusTask(ActionBookSpecificPlugin):
    """
    This is used to download new book content from the Internet (Single Book).
    """
    AI_QUICK_DESCRIPTION = ('Checks one book against its source site and deactivates it in the '
                            'database if the series is no longer being updated.')
    AI_LONG_DESCRIPTION = (
        'Runs a single-book liveness check: asks the book\'s processor (source site) whether the '
        'series is still active and, if the site says it is finished or offline, marks the book '
        'inactive in the database. Only runs on books that are currently active; an inactive or '
        'unknown book produces no task. No chapters or images are downloaded or changed. Book ID '
        'is required.')

    def __init__(self):
        super().__init__()
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

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def create_task(self, db_session: Session, args):

        book_id = args['book_id']
        results = []

        if is_not_blank(book_id):
            book = find_book_by_id(book_id, db_session)
            if book is not None and book.active:
                book_processor = processor_for_id(self.processors, book.processor)

                return CheckBookStatusTask("Book Status", f'Checking: {book.name}', book.id, book_processor,
                                           self.processors)

        return results


class CheckBookStatusTask(TaskWrapper):
    def __init__(self, name, description, book_id, processor, processors, clean_all: bool = False):
        super().__init__(name, description)
        self.book_id = book_id
        self.processors = processors
        self.processor = processor
        self.clean_all = clean_all
        self.ref_book_id = book_id
        if self.processor is not None:
            self.set_locking_key(self.processor.get_locking_key())

    def run(self, db_session: Session):

        book = find_book_by_id(self.book_id, db_session)

        if book is not None:
            self.debug('Found book definition : ' + self.book_id)
            bd = VolumeProcessor(self.processors, '', 'WEBP', self)
            status = bd.ia_active(book, self.token)
            if status is not None and not status:
                self.info('Book no longer active')
                self.set_worked()
                db_session.commit()
        else:
            self.critical('Could not find book: ' + self.book_id)
