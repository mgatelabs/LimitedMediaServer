import argparse
import json

from flask_sqlalchemy.session import Session
from sqlalchemy import Date, cast as sa_cast, desc as sql_desc, func

from auth_utils import get_uid
import datetime

from db import Book, Chapter, VolumeProgress
from feature_flags import MANAGE_VOLUME
from plugin_methods import plugin_select_arg, plugin_select_values
from plugin_system import ActionBookGeneralPlugin
from thread_utils import TaskWrapper
from volume_queries import list_books_for_rating
from volume_utils import get_volume_max_rating


class UpdateAllTagsTask(ActionBookGeneralPlugin):
    """
    This is used to get information about each book and log it.
    """
    AI_QUICK_DESCRIPTION = ('Read-only book reports logged as task output: full book list as JSON, '
                            'top 50 stale active books, or the user\'s continue-reading list.')
    AI_LONG_DESCRIPTION = (
        'Generates a read-only report about the book collection and writes it to the task log. '
        'Mode export_to_json logs a JSON array of every book with id, name, active, processor '
        'and last updated date. Mode top_50_stale logs a markdown table of the 50 active books '
        'with the oldest last-updated date. Mode continue_reading_10 logs the calling user\'s '
        'books they most likely want to continue reading, based on reading progress. No books, '
        'chapters or progress records are modified.')

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
        return [
            plugin_select_arg(
                "Mode", "mode", "export_to_json",
                plugin_select_values(
                    "Export to JSON", "export_to_json",
                    "Top 50 Stale", "top_50_stale",
                    "Continue Reading", "continue_reading_10",
                ),
                "Which mode to use",
                "bkinfo",
            ),
        ]

    def process_action_args(self, args):
        if args.get("mode") not in {"export_to_json", "top_50_stale", "continue_reading_10", None}:
            return ["mode must be one of: export_to_json, top_50_stale, continue_reading_10"]
        return None

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def create_task(self, db_session: Session, args):
        return BookDetails("BookDetails", 'All', args.get('mode', 'export_to_json'))


class BookDetails(TaskWrapper):
    def __init__(self, name, description, mode='export_to_json'):
        super().__init__(name, description)
        self.mode = mode

    def run(self, db_session):
        if self.mode == 'export_to_json':
            books = list_books_for_rating(get_uid(self.user), get_volume_max_rating(self.user), None, sort_field=Book.name,
                                          sort_descending=False, query_offset=0, query_limit=0, db_session=db_session)

            book_list = []
            for book, progress in books:
                book_list.append({
                    'id': book.id,
                    'name': book.name,
                    'active': book.active,
                    'proc': book.processor,
                    'updated': book.last_date.isoformat()
                })

            self.info(json.dumps(book_list), _json=True)
        elif self.mode == 'top_50_stale':
            stale_books = db_session.query(Book).filter(
                Book.active == True,
                Book.last_date != None
            ).order_by(Book.last_date.asc()).limit(50).all()

            md_lines = [
                "| Rank | ID | Name | Last Updated |",
                "|---|---|---|---|",
            ]
            for idx, book in enumerate(stale_books, 1):
                updated = book.last_date.strftime('%Y-%m-%d') if book.last_date else 'N/A'
                md_lines.append(f"| {idx} | {book.id} | {book.name} | {updated} |")

            self.info("\n".join(md_lines), _markdown=True)
        elif self.mode == 'continue_reading_10':
            now = datetime.datetime.now()
            current_date = now.date()

            # Get latest progress timestamp per book for this user (keep as raw datetime)
            latest_per_book = db_session.query(
                VolumeProgress.book_id,
                func.max(VolumeProgress.timestamp).label('last_read')
            ).filter(
                VolumeProgress.user_id == get_uid(self.user)
            ).group_by(VolumeProgress.book_id).subquery()

            # Get unread chapter counts per book — count chapters whose date is after the user's last session
            books_with_unread = db_session.query(
                Book.id,
                Book.name,
                latest_per_book.c.last_read.label('last_read'),
                func.count(Chapter.chapter_id).label('unread_count')
            ).join(latest_per_book, Book.id == latest_per_book.c.book_id).outerjoin(
                Chapter,
                (Chapter.book_id == Book.id) &
                (Chapter.date > sa_cast(latest_per_book.c.last_read, Date))
            ).filter(Book.active == True).group_by(
                Book.id,
                latest_per_book.c.last_read
            ).order_by(latest_per_book.c.last_read.asc()).all()

            md_lines = [
                "| Rank | ID | Name | Days Since Last Read | Unread Chapters |",
                "|---|---|---|---|---|",
            ]
            processed = []
            for row in books_with_unread:
                book_id, book_name = row[0], row[1]
                last_read_raw, unread_count = row[2], int(row[3]) if row[3] is not None else 0
                days_ago = "Unknown"

                if last_read_raw is not None:
                    try:
                        rdate = last_read_raw.date() if isinstance(last_read_raw, datetime.datetime) else datetime.fromisoformat(str(last_read_raw)[:10]).date()
                        days_ago = (current_date - rdate).days
                    except Exception:
                        pass  # leave as "Unknown"

                processed.append((book_id, book_name, days_ago, unread_count))

            # Sort by priority: most overdue books first (unreads * years since last read)
            processed.sort(key=lambda x: ((x[2] if isinstance(x[2], int) else 0) * x[3]) or -99999, reverse=True)
            
            for idx, (book_id, book_name, days_ago, unread_count) in enumerate(processed[:10], 1):
                md_lines.append(f"| {idx} | {book_id} | {book_name} | {days_ago} | {unread_count} |")

            self.info("\n".join(md_lines), _markdown=True)