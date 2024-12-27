from datetime import date, datetime
from typing import Optional, List, Tuple
import logging

from flask_sqlalchemy.session import Session
from sqlalchemy import desc, func, or_
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import aliased

from date_utils import convert_yyyymmdd_to_date
from db import Book, Chapter, VolumeProgress, VolumeBookmark, db
from text_utils import is_not_blank
from thread_utils import TaskWrapper


# Function to find a book by its ID
def find_book_by_id(book_id: str, db_session: Session = None) -> Optional[Book]:
    """
    Quickly look up a book by ID
    :param book_id:
    :param db_session:
    :return:
    """
    if db_session is not None:
        return db_session.query(Book).filter_by(id=book_id).first()
    else:
        return Book.query.filter_by(id=book_id).first()


# Recent / Viewed

def find_recent_entries(user_id: int, max_rating: int) -> Optional[List[Tuple[VolumeProgress, str]]]:
    """
    Find the user's recent activities, grouped by book_id with the latest timestamp,
    and filtered by the book's rating.
    :param user_id: The user's ID.
    :param max_rating: The maximum rating allowed for the books.
    :return: List of recent VolumeProgress entries.
    """
    # Subquery to get the latest timestamp per book_id
    latest_entries_subquery = (
        db.session.query(
            VolumeProgress.book_id,
            func.max(VolumeProgress.timestamp).label("latest_timestamp")
        )
        .filter(VolumeProgress.user_id == user_id)
        .group_by(VolumeProgress.book_id)
        .subquery()
    )

    # Alias for the book model to apply rating filter
    BookAlias = aliased(Book)

    # Main query: Join with the subquery and filter by max_rating
    return (
        db.session.query(VolumeProgress, BookAlias.name)
        .join(latest_entries_subquery,
              (VolumeProgress.book_id == latest_entries_subquery.c.book_id) &
              (VolumeProgress.timestamp == latest_entries_subquery.c.latest_timestamp))
        .join(BookAlias, VolumeProgress.book_id == BookAlias.id)
        .filter(BookAlias.rating <= max_rating)
        .order_by(desc(VolumeProgress.timestamp))
        .limit(35)
        .all()
    )


# Bookmarks

def find_bookmarks(user_id: int, book_id: str = '') -> Optional[List[VolumeBookmark]]:
    """
    Find bookmarks for a series or everywhere for a User
    :param user_id:
    :param book_id:
    :return:
    """
    if is_not_blank(book_id):
        return VolumeBookmark.query.filter_by(user_id=user_id, book_id=book_id).order_by(
            VolumeBookmark.chapter_id).all()
    else:
        return VolumeBookmark.query.filter_by(user_id=user_id).order_by(VolumeBookmark.book_id,
                                                                        VolumeBookmark.chapter_id).all()


def add_volume_bookmark(session: Session, user_id: int, book_id: str, chapter_id: str, page_number: int | None,
                        page_progress: float | None):
    """
    Add a bookmark for a user
    :param session:
    :param user_id:
    :param book_id:
    :param chapter_id:
    :param page_number:
    :param page_progress:
    :return:
    """
    # If no book is found, create a new record
    new_book = VolumeBookmark(
        user_id=user_id,
        book_id=book_id,
        chapter_id=chapter_id,
        page_number=page_number,
        page_percent=page_progress
    )

    # Add and commit the new book
    session.add(new_book)
    session.commit()


def remove_volume_bookmark(session: Session, user_id: int, row_id: int) -> bool:
    """
    Remove a bookmark for a user
    :param session:
    :param user_id:
    :param row_id:
    :return:
    """
    row = VolumeBookmark.query.filter_by(id=row_id, user_id=user_id).first()
    if row is not None:
        session.delete(row)
        session.commit()
        return True
    return False


def find_chapters_by_book(book_id: str, uid: int) -> Optional[List[tuple[Chapter, VolumeProgress]]]:
    """
    Function to find all chapters of a book by the book's ID
    :param book_id: Book ID
    :param uid: User ID
    :return:
    """

    return (
        db.session.query(
            Chapter,
            VolumeProgress
        )
        .filter(Chapter.book_id == book_id)
        .outerjoin(
            VolumeProgress,
            (VolumeProgress.book_id == Chapter.book_id) &
            (VolumeProgress.chapter_id == Chapter.chapter_id) &
            (VolumeProgress.user_id == uid)
        )
        .order_by(Chapter.sequence)
        .all()
    )
    #
    # return Chapter.query.filter_by(book_id=book_id).order_by(Chapter.sequence).all()


def find_chapter_by_id(book_id: str, chapter_id: str) -> Optional[Chapter]:
    """
    Function to find a specific chapter by book ID and chapter ID
    :param book_id:
    :param chapter_id:
    :return:
    """
    return Chapter.query.filter_by(book_id=book_id, chapter_id=chapter_id).first()


# Function to find a chapter by book ID and sequence number
def find_chapter_by_sequence(book_id: str, sequence: int) -> Optional[Chapter]:
    """
    Find a book chapter by sequence number
    :param book_id:
    :param sequence:
    :return:
    """
    return Chapter.query.filter_by(book_id=book_id, sequence=sequence).first()


def _build_books_query(max_rating: int = 0, filter_text: str = None, user_id: Optional[int] = None,
                       db_session: Session = db.session):
    """
    Used to share book search functionality
    :param max_rating:
    :param filter_text:
    :return:
    """

    if user_id is not None:

        # Aliased subquery to get the latest VolumeProgress entry for each book for a given user
        latest_volume_progress = (
            db.session.query(
                VolumeProgress.book_id,
                func.max(VolumeProgress.timestamp).label("latest_timestamp")
            )
            .filter(VolumeProgress.user_id == user_id)
            .group_by(VolumeProgress.book_id)
            .subquery()
        )

        # Aliased for easy reference in join condition
        vp_alias = aliased(VolumeProgress)

        query = db.session.query(Book, vp_alias)
    else:
        query = db.session.query(Book)

    if max_rating < 200:
        query = query.filter(Book.rating <= max_rating)

    if is_not_blank(filter_text):
        query = query.filter(
            or_(
                Book.name.like(f'%{filter_text}%'),
                Book.id.like(f'%{filter_text}%'),
                Book.tags.like(f'%{filter_text}%')
            )
        )

    return query


def _build_books_with_progress_query(user_id: int, max_rating: int = 0, filter_text: str = None,
                                     db_session: Session = db.session):
    """
    Used to share book search functionality
    :param max_rating:
    :param filter_text:
    :return:
    """

    # Aliased subquery to get the latest VolumeProgress entry for each book for a given user
    latest_volume_progress = (
        db.session.query(
            VolumeProgress.book_id,
            func.max(VolumeProgress.timestamp).label("latest_timestamp")
        )
        .filter(VolumeProgress.user_id == user_id)
        .group_by(VolumeProgress.book_id)
        .subquery()
    )

    # Aliased for easy reference in join condition
    vp_alias = aliased(VolumeProgress)

    query = db.session.query(Book, vp_alias)

    query = query.outerjoin(
        latest_volume_progress,
        Book.id == latest_volume_progress.c.book_id
    ).outerjoin(
        vp_alias,
        (vp_alias.book_id == Book.id) &
        (vp_alias.timestamp == latest_volume_progress.c.latest_timestamp)
    )

    if max_rating < 200:
        query = query.filter(Book.rating <= max_rating)

    if is_not_blank(filter_text):
        query = query.filter(
            or_(
                Book.name.like(f'%{filter_text}%'),
                Book.id.like(f'%{filter_text}%'),
                Book.tags.like(f'%{filter_text}%')
            )
        )

    return query


# Function to list books with a rating less than or equal to max_rating
def list_books_for_rating(user_id: int, max_rating: int, filter_text: str = None, sort_field=None,
                          sort_descending: bool = False,
                          query_offset: int = 0, query_limit: int = 0,
                          db_session: Session = db.session) -> List[tuple[Book, VolumeProgress]]:
    """
    List the books that a user has access to based upon their criteria and the search window
    :param max_rating:
    :param filter_text: If not blank, the book title must have this text
    :param sort_field: The field to sort against
    :param sort_descending: Is this descending sort?
    :param query_offset: The offset to query from
    :param query_limit: How many items should we return?
    :param user_id:
    :param db_session:
    :return:
    """
    query = _build_books_with_progress_query(user_id, max_rating, filter_text, db_session)

    if sort_descending:
        query = query.order_by(sort_field.desc(), Book.id.desc())
    else:
        query = query.order_by(sort_field.asc(), Book.id.asc())

    if query_offset > 0:
        query = query.offset(query_offset)

    if query_limit > 0:
        query = query.limit(query_limit)

    return query.all()


# Function to count the books with a rating less than or equal to max_rating
def count_books_for_rating(max_rating: int, filter_text: str = None) -> int:
    """
    This is the result count for list_books_for_rating
    :param max_rating:
    :param filter_text:
    :return:
    """
    return _build_books_query(max_rating, filter_text).count()


# Function to insert or update a book record
def upsert_book(book_id: str, name: str, processor: str, active: bool, info_url: str, rss_url: str = None,
                extra_url: str = None, start_chapter_id: str = None, skip: str = None, rating: int = 200,
                tags: str = None, style: str = 'P', logger: TaskWrapper = None, db_session: Session = db.session):
    """
    Update/Insert a book
    :param db_session:
    :param book_id:
    :param name:
    :param processor:
    :param active:
    :param info_url:
    :param start_chapter_id:
    :param rss_url:
    :param extra_url:
    :param skip:
    :param rating:
    :param tags:
    :param style:
    :param logger:
    :return:
    """
    try:
        # Try to get the book with the specified ID
        book = db_session.query(Book).filter_by(id=book_id).one()

        updated = False

        # Inspect the values and update if necessary
        if book.name != name:
            book.name = name
            updated = True
        if book.processor != processor:
            book.processor = processor
            updated = True
        if book.active != active:
            book.active = active
            updated = True
        if book.info_url != info_url:
            book.info_url = info_url
            updated = True
        if book.extra_url != extra_url:
            book.extra_url = extra_url
            updated = True
        if book.rss_url != rss_url:
            book.rss_url = rss_url
            updated = True
        if book.skip != skip:
            book.skip = skip
            updated = True
        if book.rating != rating:
            book.rating = rating
            updated = True
        if book.tags != tags:
            book.tags = tags
            updated = True
        if book.style != style:
            book.style = style
            updated = True
        if book.start_chapter != start_chapter_id:
            book.start_chapter = start_chapter_id
            updated = True
        if updated:
            # Commit the updates
            db_session.commit()
            if logger is not None:
                logger.info(f"Updated book with ID {book_id}")
        else:
            # Nothing to change
            db_session.rollback()

    except NoResultFound:
        # If no book is found, create a new record
        new_book = Book(
            id=book_id,
            name=name,
            processor=processor,
            active=active,
            info_url=info_url,
            extra_url=extra_url,
            rss_url=rss_url,
            skip=skip,
            rating=rating,
            tags=tags,
            style=style,
            start_chapter=start_chapter_id
        )

        # Add and commit the new book
        db_session.add(new_book)
        db_session.commit()
        if logger is not None:
            logger.info(f"Created new book with ID {book_id}")


# Function to update live book details
def update_book_live(book_id: str, last_date: date, last_chapter: str, cover: str, first_chapter: str,
                     logger: TaskWrapper = None, db_session: Session = db.session):
    """
    This is explicitly an update request for a book
    :param book_id:
    :param last_date:
    :param last_chapter:
    :param cover:
    :param first_chapter:
    :param logger:
    :param db_session:
    :return:
    """
    try:
        # Try to get the book with the specified ID
        book = db_session.query(Book).filter_by(id=book_id).one()

        updated = False

        # Inspect the values and update if necessary
        if book.last_date != last_date:
            book.last_date = last_date
            updated = True

        if book.last_chapter != last_chapter:
            book.last_chapter = last_chapter
            updated = True

        if book.cover != cover:
            book.cover = cover
            updated = True

        if book.first_chapter != first_chapter:
            book.first_chapter = first_chapter
            updated = True

        if updated:
            # Commit the updates
            db_session.commit()
            if logger is not None:
                logger.info(f"Updated book with ID {book_id}")
        else:
            # Nothing to change
            db_session.rollback()

    except NoResultFound:
        if logger is not None:
            logger.error(f"Could not find book for {book_id}")


# Function to insert or update a book record
def upsert_recent(user_id: int, book_id: str, chapter_id: str, page_number: int | None, page_percent: float | None,
                  timestamp: datetime, db_session: Session = db.session):
    """
    This will add/update a recent entry, so we can track how far a user has progressed
    :param user_id:
    :param book_id:
    :param chapter_id:
    :param page_number:
    :param page_percent:
    :param timestamp:
    :param db_session:
    :return:
    """
    try:
        # Try to get the book with the specified ID
        existing_progress = db_session.query(VolumeProgress).filter(VolumeProgress.user_id == user_id,
                                                                    VolumeProgress.book_id == book_id,
                                                                    VolumeProgress.chapter_id == chapter_id).one()

        existing_progress.chapter_id = chapter_id
        existing_progress.page_number = page_number
        existing_progress.page_percent = page_percent
        existing_progress.timestamp = timestamp

        # Commit the updates
        db_session.commit()

    except NoResultFound:
        # If no book is found, create a new record
        new_progress = VolumeProgress(
            user_id=user_id,
            book_id=book_id,
            chapter_id=chapter_id,
            page_number=page_number,
            page_percent=page_percent,
            timestamp=timestamp
        )

        # Add and commit the new book
        db_session.add(new_progress)
        db_session.commit()


# Function to manage book chapters
def manage_book_chapters(book_id: str, chapters, logger: TaskWrapper = None, db_session: Session = db.session):
    # Retrieve existing chapters for the book
    exiting_chapters = db_session.query(Chapter).filter_by(book_id=book_id).order_by(Chapter.sequence).all()
    existing_lookup = {}

    for exiting_chapter in exiting_chapters:
        existing_lookup[exiting_chapter.chapter_id] = exiting_chapter

    sequence_number = 0

    for chapter in chapters:
        chapter_name = chapter['name']
        page_count = len(chapter['files'])
        pages = ','.join(chapter['files'])
        chapter_date = convert_yyyymmdd_to_date(chapter['date'])

        if logger is not None and logger.can_trace():
            logger.trace(f"Finding {chapter_name}")

        if chapter_name in existing_lookup:
            exiting_chapter = existing_lookup[chapter_name]
            del existing_lookup[chapter_name]

            if exiting_chapter.sequence != sequence_number or exiting_chapter.page_count != page_count or exiting_chapter.image_names != pages or exiting_chapter.date != chapter_date:
                exiting_chapter.sequence = sequence_number
                exiting_chapter.page_count = page_count
                exiting_chapter.image_names = pages
                db_session.commit()

                if logger is not None and logger.can_debug():
                    logger.debug(f"Updated Chapter {book_id} {chapter_name}")
            else:
                if logger is not None and logger.can_trace():
                    logger.trace(f"Chapter {book_id} {chapter_name} in Sync")

        else:
            new_chapter = Chapter(
                book_id=book_id,
                chapter_id=chapter_name,
                page_count=page_count,
                image_names=pages,
                sequence=sequence_number,
                date=chapter_date
            )

            # Add and commit the new chapter
            db_session.add(new_chapter)
            db_session.commit()

            if logger is not None and logger.can_debug():
                logger.debug(f"New Chapter {book_id} {chapter_name}")

        sequence_number = sequence_number + 1

    try:
        for exiting_chapter in existing_lookup.values():
            if logger is not None and logger.can_trace():
                logger.trace(f"Erasing Chapter {exiting_chapter.chapter_id}")
            db_session.delete(exiting_chapter)
            db_session.commit()
    except Exception as ex:
        logging.exception(ex)
        logger.info(existing_lookup)
