import argparse
import random
from itertools import cycle

from flask_sqlalchemy.session import Session

from constants import PROPERTY_SERVER_VOLUME_FOLDER, APP_KEY_PROCESSORS
from db import Book
from feature_flags import MANAGE_VOLUME
from plugin_system import ActionPlugin, ActionBookPlugin, plugin_long_string_arg
from plugins.book_update_headers import UpdateVolumeHeader
from plugins.book_volume_processing import VolumeProcessor
from text_utils import is_not_blank, is_blank, clean_string
from thread_utils import TaskWrapper
from volume_queries import find_book_by_id
from volume_utils import parse_curl_headers


# Example function to group books by processor
def group_books_by_processor(books):
    # Group books by processor value
    grouped_books = {}
    for book in books:
        if book.processor not in grouped_books:
            grouped_books[book.processor] = []
        grouped_books[book.processor].append(book)

    return grouped_books


# Function to interleave grouped books in desired order
def interleave_books(grouped_books):
    # Create a list of unique processors
    processors = list(grouped_books.keys())
    # Cycle through processors
    processor_cycle = cycle(processors)

    # Interleave books
    result = []
    while any(grouped_books.values()):  # Continue while there are books left in any group
        for processor in processor_cycle:
            if grouped_books[processor]:  # If there are still books in this group
                # Choose a random book from the group and add it to the result list
                book = random.choice(grouped_books[processor])
                result.append(book)
                # Remove the chosen book from the group to avoid repeats
                grouped_books[processor].remove(book)

            # If all books have been used, stop cycling
            if not any(grouped_books.values()):
                break

    return result


class UpdateAllBooksTask(ActionPlugin):
    """
    This is used to download new book content from the Internet (All Books).
    """

    def __init__(self):
        super().__init__()
        self.processors = []
        self.book_folder = ''

    def get_sort(self):
        return {'id': 'books_workers', 'sequence': 0}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_category(self):
        return 'book'

    def get_action_name(self):
        return 'Download All Books'

    def get_action_id(self):
        return 'action.books.download'

    def get_action_icon(self):
        return 'download'

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def get_action_args(self):

        values = [{"id": "*", "name": "All"}]

        for processor in self.processors:
            values.append({"id": processor.processor_id, "name": processor.processor_name})

        result = [{
            "name": "FILTER",
            "id": "filter",
            "type": "select",
            "default": "*",
            "description": "When not *, only Processors that match will execute.",
            "values": values
        }, {
            "name": "Cleaning",
            "id": "cleaning",
            "type": "select",
            "default": "n",
            "description": "Determines when content will be cleaned.  Normally only 'New Chapters' will be cleaned, but choose 'All Chapters' will cause it to purge new and existing chapters.  All files < 10kb or invalid will be removed.",
            "values": [{"id": 'n', "name": 'New Chapters'}, {"id": 'a', "name": 'All Chapters'}]
        }, plugin_long_string_arg('Headers', 'headers',
                                  'Open Chrome and access any site that is protected by a service you want to get around.  Open chrome dev tools (F12).  Refresh the page.  In the Developer tools network tab, click the page, the 1st item, right click, copy, Copy as cURL (Bash).  Paste that here.')]

        return result

    def process_action_args(self, args: dict[str, any]):
        results = []

        if 'filter' not in args or args['filter'] is None or is_blank(args['filter']) == '':
            results.append('filter is required')

        if 'cleaning' not in args or args['cleaning'] is None or args['cleaning'] == '':
            results.append('cleaning is required')

        if 'headers' not in args or is_blank(args['headers']):
            args['headers'] = None
        elif not args['headers'].startswith('curl'):
            results.append('headers must be a curl bash command')
        else:
            header_dict = parse_curl_headers(args['headers'])
            args['headers'] = header_dict

        if len(results) > 0:
            return results

        return None

    def absorb_config(self, config):
        self.processors = config[APP_KEY_PROCESSORS]
        self.book_folder = config[PROPERTY_SERVER_VOLUME_FOLDER]

    def create_task(self, db_session: Session, args):

        results = []

        if args['headers'] is not None:
            results.append(UpdateVolumeHeader(args['headers']))

        cleaning = (args['cleaning'] == 'a')

        books = db_session.query(Book).filter(Book.active == True).all()

        grouped_books = group_books_by_processor(books)
        interleaved_books = interleave_books(grouped_books)

        processor_filter = args['filter']

        for book in interleaved_books:
            if processor_filter == '*' or processor_filter == book.processor:
                results.append(
                    DownloadBookTask("GetBook", f'Updating: {book.name}', book.id, self.processors, self.book_folder,
                                     cleaning))

        return results


class UpdateSingleBookTask(ActionBookPlugin):
    """
    This is used to download new book content from the Internet (Single Book).
    """

    def __init__(self):
        super().__init__()
        self.processors = []
        self.book_folder = ''

    def is_book(self):
        return True

    def get_category(self):
        return "book"

    def get_sort(self):
        return {'id': 'book_workers', 'sequence': 0}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Download Book'

    def get_action_id(self):
        return 'action.book.download'

    def get_action_icon(self):
        return 'download'

    def get_action_args(self):

        result = super().get_action_args()

        result.append({
            "name": "Cleaning",
            "id": "cleaning",
            "type": "select",
            "default": "n",
            "description": "Determines when content will be cleaned.  Normally only 'New Chapters' will be cleaned, but choose 'All Chapters' will cause it to purge new and existing chapters.  All files < 10kb or invalid will be removed.",
            "values": [{"id": 'n', "name": 'New Chapters'}, {"id": 'a', "name": 'All Chapters'}]
        })
        result.append(plugin_long_string_arg('Headers', 'headers',
                                  'Open Chrome and access any site that is protected by a service you want to get around.  Open chrome dev tools (F12).  Refresh the page.  In the Developer tools network tab, click the page, the 1st item, right click, copy, Copy as cURL (Bash).  Paste that here.'))

        return result

    def process_action_args(self, args):
        results = []

        if 'cleaning' not in args or args['cleaning'] is None or args['cleaning'] == '':
            results.append('cleaning is required')

        if 'headers' not in args or is_blank(args['headers']):
            args['headers'] = None
        elif not args['headers'].startswith('curl'):
            results.append('headers must be a curl bash command')
        else:
            header_dict = parse_curl_headers(args['headers'])
            args['headers'] = header_dict

        if len(results) > 0:
            return results

        return None

    def absorb_config(self, config):
        self.processors = config[APP_KEY_PROCESSORS]
        self.book_folder = config[PROPERTY_SERVER_VOLUME_FOLDER]

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def create_task(self, db_session: Session, args):

        book_id = args['series_id']
        cleaning = (args['cleaning'] == 'a')
        results = []

        if args['headers'] is not None:
            results.append(UpdateVolumeHeader(args['headers']))

        if is_not_blank(book_id):
            book = find_book_by_id(book_id, db_session)
            if book is not None:
                the_book = DownloadBookTask("GetBook", f'Updating: {book.name}', book.id, self.processors,
                                            self.book_folder, cleaning == 'a')
                if len(results) == 0:
                    return the_book
                else:
                    results.append(the_book)

        return results


class DownloadBookTask(TaskWrapper):
    def __init__(self, name, description, book_id, processors, book_folder: str, clean_all: bool = False):
        super().__init__(name, description)
        self.book_id = book_id
        self.processors = processors
        self.clean_all = clean_all
        self.book_folder = book_folder

    def run(self, db_session: Session):

        if is_blank(self.book_folder):
            self.critical('volume folder is required')
            self.set_failure()
            return

        book = find_book_by_id(self.book_id, db_session)

        if book is not None:
            self.info('Found book definition : ' + self.book_id)
            bd = VolumeProcessor(self.processors, self.book_folder, self)
            bd.process_book(db_session, book, self.token, self.clean_all)
        else:
            self.critical('Could not find book: ' + self.book_id)
