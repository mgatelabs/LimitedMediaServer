import argparse
import platform
import random
from itertools import cycle
import re

from flask_sqlalchemy.session import Session

from db import Book
from feature_flags import MANAGE_VOLUME
from html_utils import has_valid_headers
from plugin_methods import plugin_long_string_arg, plugin_select_arg, plugin_select_values, plugin_url_arg
from plugin_system import ActionBookSpecificPlugin, ActionBookGeneralPlugin
from plugins.book_update_headers import UpdateVolumeHeader
from plugins.book_volume_processing import VolumeProcessor
from text_utils import is_not_blank, is_blank
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


class UpdateAllBooksPlugin(ActionBookGeneralPlugin):
    """
    This is used to download new book content from the Internet (All Books).
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'bkucall'

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

        result = super().get_action_args()

        result.append(
            plugin_select_arg('Filter', 'filter', '*', values, "When not *, only Processors that match will execute.",
                              'book'))

        result.append(plugin_select_arg('Cleaning', 'cleaning', 'n',
                                        plugin_select_values('New Chapters', 'n', 'All Chapters', 'a'),
                                        "Determines when content will be cleaned.  Normally only 'New Chapters' will be cleaned, but choose 'All Chapters' will cause it to purge new and existing chapters.  All files < 10kb or invalid will be removed.",
                                        'com'))

        result.append(plugin_long_string_arg('Headers', 'headers',
                                             'Open Chrome and access any site that is protected by a service you want to get around.  Open chrome dev tools (F12).  Refresh the page.  In the Developer tools network tab, click the page, the 1st item, right click, copy, Copy as cURL (Bash).  Paste that here.',
                                             'com'))

        result.append(plugin_select_arg('Cleaning', 'cleaning', 'n',
                                        plugin_select_values('New Chapters', 'n', 'All Chapters', 'a'),
                                        "Determines when content will be cleaned.  Normally only 'New Chapters' will be cleaned, but choose 'All Chapters' will cause it to purge new and existing chapters.  All files < 10kb or invalid will be removed.",
                                        'com'))

        return result

    def process_action_args(self, args: dict[str, any]):
        results = []

        if 'filter' not in args or args['filter'] is None or is_blank(args['filter']) == '':
            results.append('filter is required')

        if 'cleaning' not in args or args['cleaning'] is None or args['cleaning'] == '':
            results.append('cleaning is required')

        if 'headers' not in args or is_blank(args['headers']):
            args['headers'] = None
            if not has_valid_headers():
                results.append('headers are required to continue')
        elif not args['headers'].startswith('curl'):
            results.append('headers must be a curl bash command')
        else:
            header_dict = parse_curl_headers(args['headers'])
            args['headers'] = header_dict

        if len(results) > 0:
            return results

        return None

    def is_ready(self):
        return super().is_ready() and platform.system() == 'Linux'

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
                    DownloadBookJob("GetBook", f'Updating: {book.name} ({book.processor})', book.id, self.processors,
                                    self.book_storage_folder, self.book_storage_format,
                                    cleaning))

        return results


class UpdateSingleBookPlugin(ActionBookSpecificPlugin):
    """
    This is used to download new book content from the Internet (Single Book).
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'bkuc'

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

        result.append(plugin_select_arg('Cleaning', 'cleaning', 'n',
                                        plugin_select_values('New Chapters', 'n', 'All Chapters', 'a'),
                                        "Determines when content will be cleaned.  Normally only 'New Chapters' will be cleaned, but choose 'All Chapters' will cause it to purge new and existing chapters.  All files < 10kb or invalid will be removed.",
                                        'com'))

        result.append(plugin_long_string_arg('Headers', 'headers',
                                             'Open Chrome and access any site that is protected by a service you want to get around.  Open chrome dev tools (F12).  Refresh the page.  In the Developer tools network tab, click the page, the 1st item, right click, copy, Copy as cURL (Bash).  Paste that here.',
                                             'com'))

        return result

    def process_action_args(self, args):
        results = []

        if 'cleaning' not in args or args['cleaning'] is None or args['cleaning'] == '':
            results.append('cleaning is required')

        if 'headers' not in args or is_blank(args['headers']):
            args['headers'] = None
            if not has_valid_headers():
                results.append('headers are required to continue')
        elif not args['headers'].startswith('curl'):
            results.append('headers must be a curl bash command')
        else:
            header_dict = parse_curl_headers(args['headers'])
            args['headers'] = header_dict

        if len(results) > 0:
            return results

        return None

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def is_ready(self):
        return platform.system() == 'Linux'

    def create_task(self, db_session: Session, args):

        book_id = args['book_id']
        cleaning = (args['cleaning'] == 'a')
        results = []

        if args['headers'] is not None:
            results.append(UpdateVolumeHeader(args['headers']))

        if is_not_blank(book_id):
            book = find_book_by_id(book_id, db_session)
            if book is not None:
                the_book = DownloadBookJob("GetBook", f'Updating: {book.name}', book.id, self.processors,
                                           self.book_storage_folder, self.book_storage_format, cleaning == 'a')
                if len(results) == 0:
                    return the_book
                else:
                    results.append(the_book)

        return results

def is_valid_format(s):
    pattern = r'^\d{4}(\.\d+)?$|^chapter-\d+(\.\d+)?$'
    return bool(re.match(pattern, s))

class UpdateSingleBookChapterPlugin(ActionBookSpecificPlugin):
    """
    This is used to download new book content from the Internet (Single Book).
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'bkucc'

    def is_book(self):
        return True

    def get_category(self):
        return "book"

    def get_sort(self):
        return {'id': 'book_workers', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Download (Chapter)'

    def get_action_id(self):
        return 'action.book.download.chapter'

    def get_action_icon(self):
        return 'download'

    def get_action_args(self):

        result = super().get_action_args()

        result.append(plugin_url_arg("Chapter URL", 'chapter_url', 'The URL to download'))
        result.append(plugin_long_string_arg("Chapter Name", 'chapter_name', 'Name of the chapter, like Chapter-1, 0001, or 0001.5'))

        result.append(plugin_select_arg('Cleaning', 'cleaning', 'n',
                                        plugin_select_values('New Chapters', 'n', 'All Chapters', 'a'),
                                        "Determines when content will be cleaned.  Normally only 'New Chapters' will be cleaned, but choose 'All Chapters' will cause it to purge new and existing chapters.  All files < 10kb or invalid will be removed.",
                                        'com'))

        result.append(plugin_long_string_arg('Headers', 'headers',
                                             'Open Chrome and access any site that is protected by a service you want to get around.  Open chrome dev tools (F12).  Refresh the page.  In the Developer tools network tab, click the page, the 1st item, right click, copy, Copy as cURL (Bash).  Paste that here.',
                                             'com'))

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

        if 'chapter_url' not in args or args['chapter_url'] is None or args['chapter_url'] == '':
            results.append('chapter_url is required')

        if 'chapter_name' not in args or args['chapter_name'] is None or args['chapter_name'] == '':
            results.append('chapter_name is required')

        if not is_valid_format(args['chapter_name']):
            results.append('Invalid chapter_name format')

        if len(results) > 0:
            return results

        return None

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def is_ready(self):
        return platform.system() == 'Linux'

    def create_task(self, db_session: Session, args):

        book_id = args['book_id']
        cleaning = (args['cleaning'] == 'a')
        results = []
        chapter_url = args['chapter_url']
        chapter_name = args['chapter_name']

        if args['headers'] is not None:
            results.append(UpdateVolumeHeader(args['headers']))

        if is_not_blank(book_id):
            book = find_book_by_id(book_id, db_session)
            if book is not None:
                the_book = DownloadBookChapterJob("GetBookChap", f'Updating: {book.name} {chapter_name}', chapter_url, chapter_name, book.id, self.processors,
                                                  self.book_storage_folder, self.book_storage_format, cleaning == 'a')
                if len(results) == 0:
                    return the_book
                else:
                    results.append(the_book)

        return results


class DownloadBookJob(TaskWrapper):
    def __init__(self, name, description, book_id, processors, book_folder: str, storage_format: str = 'PNG',
                 clean_all: bool = False):
        super().__init__(name, description)
        self.book_id = book_id
        self.processors = processors
        self.clean_all = clean_all
        self.book_folder = book_folder
        self.storage_format = storage_format
        self.ref_book_id = book_id

    def run(self, db_session: Session):

        if is_blank(self.book_folder):
            self.critical('volume folder is required')
            self.set_failure()
            return

        book = find_book_by_id(self.book_id, db_session)

        if book is not None:
            self.info('Found book definition : ' + self.book_id)
            bd = VolumeProcessor(self.processors, self.book_folder, self.storage_format, self)
            bd.process_book(db_session, book, self.token, self.clean_all)
        else:
            self.critical('Could not find book: ' + self.book_id)


class DownloadBookChapterJob(TaskWrapper):
    def __init__(self, name, description, chapter_url: str, chapter_name: str, book_id, processors, book_folder: str, storage_format: str = 'PNG',
                 clean_all: bool = False):
        super().__init__(name, description)
        self.book_id = book_id
        self.processors = processors
        self.clean_all = clean_all
        self.book_folder = book_folder
        self.storage_format = storage_format
        self.ref_book_id = book_id
        self.chapter_url = chapter_url
        self.chapter_name = chapter_name

    def run(self, db_session: Session):

        if is_blank(self.book_folder):
            self.critical('volume folder is required')
            self.set_failure()
            return

        book = find_book_by_id(self.book_id, db_session)

        if book is not None:
            self.info('Found book definition : ' + self.book_id)
            bd = VolumeProcessor(self.processors, self.book_folder, self.storage_format, self)
            bd.process_book_chapter(db_session, book, self.token, self.chapter_url, self.chapter_name, self.clean_all)
        else:
            self.critical('Could not find book: ' + self.book_id)
