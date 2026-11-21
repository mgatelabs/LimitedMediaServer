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
from volume_queries import find_book_by_id, sync_book_tags


class CheckAllTagsTask(ActionBookGeneralPlugin):
    """
    This is used to download new book content from the Internet (All Books).
    """
    AI_QUICK_DESCRIPTION = ('Fetches genre tags for all active books that have no tags yet from '
                            'their source sites and stores them on the books.')
    AI_LONG_DESCRIPTION = (
        'Runs over all active books and, for any book whose tag field is still blank, asks the '
        'book\'s processor (source site) for its genre tags, then stores the returned tags on '
        'the book record and syncs the tag tables. Books that already have tags are skipped. '
        'Filter is a required select (default All) limiting the run to one processor when not '
        'All. No chapters or images are downloaded or changed. This action only runs on a Linux '
        'server.')

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
    AI_QUICK_DESCRIPTION = ('Fetches the genre tags for one active book from its source site and '
                            'stores them on the book record.')
    AI_LONG_DESCRIPTION = (
        'Runs a single-book tag fetch: asks the book\'s processor (source site) for its genre '
        'tags and, when the site returns a result, stores the tags on the book record and syncs '
        'the tag tables. Only runs on books that are currently active; an inactive or unknown '
        'book produces no task. Unlike the all-books variant, a book that already has tags is '
        'still re-checked. No chapters or images are downloaded or changed. Book ID is required. '
        'This action only runs on a Linux server.')

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
            bd = VolumeProcessor(self.processors, '', 'WEBP', self)
            status = bd.get_tags(book, self.token)
            if status is not None and status:
                self.info('Book tags updates')
                self.set_worked()
                tag_list = [t.strip().upper() for t in (book.tags or "").split(",") if t.strip()]
                sync_book_tags(book, tag_list, db_session, False)
                db_session.commit()
        else:
            self.critical('Could not find book: ' + self.book_id)
