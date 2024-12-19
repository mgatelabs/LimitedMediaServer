import argparse

from flask_sqlalchemy.session import Session

from auth_utils import get_uid
from db import Book
from feature_flags import MANAGE_VOLUME
from plugin_system import ActionPlugin
from thread_utils import TaskWrapper
from volume_queries import list_books_for_rating
from volume_utils import get_volume_max_rating


class UpdateAllTagsTask(ActionPlugin):
    """
    This is used to get information about each book and log it.
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'bkinfo'

    def get_sort(self):
        return {'id': 'books_info', 'sequence': 2}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Book Info'

    def get_action_id(self):
        return 'action.book.info'

    def get_action_icon(self):
        return 'bookmarks'

    def get_action_args(self):
        return []

    def process_action_args(self, args):
        return None

    def absorb_config(self, config):
        pass

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def get_category(self):
        return 'book'

    def create_task(self, db_session: Session, args):
        return BookDetails("BookDetails", 'All')


class BookDetails(TaskWrapper):
    def __init__(self, name, description):
        super().__init__(name, description)

    def run(self, db_session):

        books = list_books_for_rating(get_uid(self.user), get_volume_max_rating(self.user), None, Book.name, False, 0, 0, db_session)

        for book, progress in books:
            self.always('Book: ' + book.name + ' (' + book.id + ')')

            self.info(f'Active: {book.active}')
            self.info(f'Processor: {book.processor}')

            if book.info_url:
                self.info(f'Info URL: {book.info_url}')
            if book.rss_url:
                self.info(f'RSS URL: {book.rss_url}')
            if book.extra_url:
                self.info(f'Extra URL: {book.extra_url}')

            if book.tags:
                self.info(f'Tags: {book.tags}')
            else:
                self.warn('Missing tags')