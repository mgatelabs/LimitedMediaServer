import io
import logging
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

from PIL import Image
from flask import Blueprint, send_from_directory, current_app, request, make_response, send_file, \
    after_this_request
from sqlalchemy import func
from werkzeug.utils import secure_filename

from auth_utils import shall_authenticate_user, feature_required, feature_required_with_cookie, get_uid
from common_utils import generate_success_response, generate_failure_response
from constants import PROPERTY_SERVER_VOLUME_FOLDER, PROPERTY_SERVER_VOLUME_READY, APP_KEY_PROCESSORS, \
    BOOK_KEY_PURPOSE_ALT_VALUE
from date_utils import convert_date_to_yyyymmdd, convert_datetime_to_yyyymmdd
from db import db, Book, Chapter
from feature_flags import BOOKMARKS, VIEW_BOOKS, MANAGE_VOLUME
from filename_utils import decompress_filenames, compress_filenames
from image_hashing import scan_for_duplicate_chapters
from image_utils import split_and_save_image, merge_two_images, resize_image, split_image_into_pieces
from messages import msg_action_cancelled_wrong, msg_missing_parameter, msg_invalid_parameter, \
    msg_access_denied_content_rating, msg_operation_complete, msg_action_failed, msg_server_error, msg_book_added, \
    msg_book_removed
from number_utils import is_integer, parse_boolean, is_boolean
from text_utils import is_blank, clean_string, is_valid_book_id, is_not_blank
from volume_queries import list_books_for_rating, find_chapters_by_book, find_book_by_id, find_chapter_by_id, \
    find_chapter_by_sequence, upsert_book, upsert_recent, \
    find_bookmarks, add_volume_bookmark, remove_volume_bookmark, \
    count_books_for_rating, find_recent_entries, manage_remove_book, find_tags, search_tags, \
    find_book_key_values, find_book_key_value, add_book_key_value, update_book_key_value, remove_book_key_value
from volume_utils import get_volume_max_rating

volume_blueprint = Blueprint('volume', __name__)


# ==============================================================================
# Book Retrieval: Get books, chapters, tags
# ==============================================================================

@volume_blueprint.route('/list/books', methods=['POST'])
@feature_required(volume_blueprint, VIEW_BOOKS)
def get_books(user_details: dict) -> tuple:
    """
    Retrieve a paginated list of books filtered by rating, text, and tags.

    Args:
        user_details (dict): Authenticated user info (injected).
        form.offset (str, optional): Pagination offset; defaults to 0.
        form.limit (str, optional): Max books per page; defaults to 20.
        form.rating (str, optional): Max content rating to include; defaults to 0.
        form.sort (str, optional): Sort order — 'AZ', 'ZA' by name or 'DA', 'DD' by date; defaults to AZ.
        form.filter_text (str, optional): Keyword search in book names.
        form.filter_tags (str, optional): Comma-separated tags to filter by.
        form.filter_processor (str, optional): Comma-separated processor IDs to filter by.

    Returns:
        tuple: 200 on success with ``{"books": [...], "paging": {"total": N, "offset": N}}``.
               Fails with a message if volume is not ready or rating exceeds the user's limit.
    """

    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400, messages=[msg_server_error()])

    offset = clean_string(request.form.get('offset'))
    limit = clean_string(request.form.get('limit'))
    requested_rating_limit = clean_string(request.form.get('rating'))
    sort = clean_string(request.form.get('sort'))
    filter_text = clean_string(request.form.get('filter_text'))
    filter_tags = clean_string(request.form.get('filter_tags'))
    filter_type = clean_string(request.form.get('filter_type'))
    filter_processor = clean_string(request.form.get('filter_processor'))

    if len(filter_tags) > 0:
        filter_tags = [t.strip().upper() for t in (filter_tags or "").split(",") if t.strip()]
    else:
        filter_tags = []

    if len(filter_processor) > 0:
        filter_processor = [t.strip() for t in (filter_processor or "").split(",") if t.strip()]
    else:
        filter_processor = []

    user_uid = get_uid(user_details)

    if is_not_blank(offset) and is_integer(offset):
        offset = int(offset)
    else:
        offset = 0

    if is_not_blank(limit) and is_integer(limit):
        limit = int(limit)
    else:
        limit = 20

    if is_not_blank(requested_rating_limit) and is_integer(requested_rating_limit):
        requested_rating_limit = int(requested_rating_limit)
    else:
        requested_rating_limit = 0

    book_data = []

    max_rating = get_volume_max_rating(user_details)

    if requested_rating_limit > max_rating:
        return generate_failure_response('Requested rating is greater then user max level',
                                         messages=[msg_access_denied_content_rating()])

    if is_not_blank(sort):
        if sort == 'AZ':
            book_sort = Book.name
            sort_descending = False
        elif sort == 'ZA':
            book_sort = Book.name
            sort_descending = True
        elif sort == 'DA':
            book_sort = Book.last_date
            sort_descending = False
        elif sort == 'DD':
            book_sort = Book.last_date
            sort_descending = True
        else:
            book_sort = Book.name
            sort_descending = False
    else:
        book_sort = Book.name
        sort_descending = False

    total_books = count_books_for_rating(requested_rating_limit, filter_text, filter_tags, filter_type,
                                         filter_processors=filter_processor)

    if offset > total_books:
        offset = 0

    books_with_progress = list_books_for_rating(user_uid, requested_rating_limit, filter_text, filter_tags=filter_tags,
                                                 filter_type=filter_type, filter_processors=filter_processor, sort_field=book_sort,
                                                 sort_descending=sort_descending,
                                                 query_offset=offset, query_limit=limit, db_session=db.session)

    for book, progress in books_with_progress:

        latest = None

        if progress is not None:

            if progress.page_number is not None:
                value = str(progress.page_number)
            else:
                value = f'@{progress.page_percent:.5f}'

            latest = {"chapter": progress.chapter_id, "value": value}

        result = {'id': book.id, 'json': book.id, 'name': book.name, 'rating': book.rating, 'cover': book.cover,
                  'first': book.first_chapter, 'last': book.last_chapter, 'active': book.active,
                  'date': convert_date_to_yyyymmdd(book.last_date),
                  'tags': book.tags.split(',') if book.tags is not None else [],
                  'style': 'page' if book.style == 'P' else 'scroll', "recent": latest}

        book_data.append(result)

    return generate_success_response('', {"books": book_data, "paging": {"total": total_books, "offset": offset}})


@volume_blueprint.route('/list/chapters', methods=['POST'])
@feature_required(volume_blueprint, VIEW_BOOKS)
def get_chapters(user_details: dict) -> tuple:
    """
    Retrieve a list of chapters for a given book with the user's reading progress on each.

    Args:
        user_details (dict): Authenticated user info (injected).
        form.book_id (str): Book whose chapters to list (required).

    Returns:
        tuple: 200 on success with ``{"chapters": [{"name": id, "value": progress}], "name": book_name,
               "style": "page"|"scroll", "info_url": url}``.
               Fails if the book is not found or rating exceeds the user's limit.
    """

    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400, messages=[msg_server_error()])

    user_uid = get_uid(user_details)
    book_id = clean_string(request.form.get('book_id'))

    if is_blank(book_id):
        return generate_failure_response('book_id parameter is required', messages=[msg_missing_parameter('book_id')])

    book = find_book_by_id(book_id)

    if book is None:
        return generate_failure_response(f'Book {book_id} not found', messages=[msg_action_cancelled_wrong()])

    max_rating = get_volume_max_rating(user_details)

    if book.rating > max_rating:
        return generate_failure_response('User is not allowed to view content out of their rating zone',
                                         messages=[msg_access_denied_content_rating()])

    chapters = find_chapters_by_book(book_id, user_uid)

    chapter_results = []

    for chapter, progress in chapters:

        if progress is not None:
            if progress.page_percent is not None:
                value = f'@{progress.page_percent:.5f}'
            else:
                value = str(progress.page_number)
        else:
            value = ''

        entry = {"name": chapter.chapter_id, "value": value}

        chapter_results.append(entry)

    info_url = ''
    if book.info_url is not None:
        info_url = book.info_url

    style = 'scroll' if book.style == 'S' else 'page'

    return generate_success_response('', {'chapters': chapter_results, 'name': book.name, 'style': style,
                                          'info_url': info_url})


@volume_blueprint.route('/list/tags', methods=['POST'])
@feature_required(volume_blueprint, VIEW_BOOKS)
def get_tags(user_details: dict) -> tuple:
    """
    Retrieve the full list of available tags.

    Args:
        user_details (dict): Authenticated user info (injected).

    Returns:
        tuple: 200 on success with ``{"tags": ["tag1", "tag2", ...]}``.
               Fails if volume service is not ready.
    """
    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400, messages=[msg_server_error()])

    tags = []
    for tag in find_tags():
        tags.append(tag.name)

    return generate_success_response('', {'tags': tags})


@volume_blueprint.route('/list/images', methods=['POST'])
@feature_required(volume_blueprint, VIEW_BOOKS)
def get_images(user_details: dict) -> tuple:
    """
    Retrieve a list of image file names for a given chapter, including navigation metadata and optional dimensions.

    Args:
        user_details (dict): Authenticated user info (injected).
        form.book_id (str): Book ID (required).
        form.chapter_id (str): Chapter ID within the book (required).
        query.include_sizes (str, 'true'|'false'): If true, return each file's pixel dimensions in ``"sizes"``.

    Returns:
        tuple: 200 on success with

            ``{"prev": prev_chapter_id, "next": next_chapter_id, "sizes": [{"w": N, "h": M}, ...],
              "files": ["file.png", ...], "style": "page"|"scroll"}``.
            Fails if the book or chapter is not found, or rating exceeds the user's limit.
    """

    include_sizes = request.args.get('include_sizes', default='false').lower() == 'true'

    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400, messages=[msg_server_error()])

    book_id = clean_string(request.form.get('book_id'))
    chapter_id = clean_string(request.form.get('chapter_id'))

    if is_blank(book_id):
        return generate_failure_response('book_id parameter is required', messages=[msg_missing_parameter('book_id')])

    if is_blank(chapter_id):
        return generate_failure_response('chapter_id parameter is required',
                                         messages=[msg_missing_parameter('chapter_id')])

    book = find_book_by_id(book_id)

    if book is None:
        return generate_failure_response('book not found', 404, messages=[msg_action_cancelled_wrong()])

    max_rating = get_volume_max_rating(user_details)

    if book.rating > max_rating:
        return generate_failure_response('User is not allowed to view content out of their rating zone',
                                         messages=[msg_access_denied_content_rating()])

    current_chapter = find_chapter_by_id(book_id, chapter_id)

    if current_chapter is None:
        return generate_failure_response('chapter not found', messages=[msg_action_cancelled_wrong()])

    prev_chapter_record = find_chapter_by_sequence(book_id, current_chapter.sequence - 1)
    next_chapter_record = find_chapter_by_sequence(book_id, current_chapter.sequence + 1)

    files = decompress_filenames(current_chapter.image_names) if current_chapter.image_names else []
    prev_chapter_id = prev_chapter_record.chapter_id if prev_chapter_record else ''
    next_chapter_id = next_chapter_record.chapter_id if next_chapter_record else ''

    sizes = []

    if include_sizes:
        for file_name in files:
            file_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_id, chapter_id, file_name)
            w, h = 0, 0
            if (os.path.exists(file_path)):
                try:
                    with Image.open(file_path) as img:
                        w, h = img.size
                except Exception:
                    w, h = 0, 0

            sizes.append({"w": w, "h": h})

    return generate_success_response('',
                                     {"prev": prev_chapter_id, "next": next_chapter_id, "sizes": sizes, "files": files,
                                      "style": 'page' if book.style == 'P' else 'scroll'})


# ==============================================================================
# Progress Tracking: Manage reading progress
# ==============================================================================

@volume_blueprint.route('/progress', methods=['POST'])
@feature_required(volume_blueprint, VIEW_BOOKS)
def push_progress(user_details):
    """
    Update the user's reading progress for a given book and chapter.

    Args:
        user_details (dict): Authenticated user info (injected).
        form.book_id (str): Book ID (required).
        form.chapter_id (str): Chapter ID within the book (required).
        form.value (str): Current page number or reading progress.

            - For scroll mode ('S'): ``"<number>"`` for absolute page or ``"@<percent>"`` for percentage of chapter read.
            - For page-perfect model (not 'S'): ``"@0"`` always, or an absolute page number.

    Returns:
        tuple: 200 on success with an empty message string. Fails if volume is not ready, book
        or user lacks permission, or any required form param is missing.
    """
    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400, messages=[msg_server_error()])

    book_id = clean_string(request.form.get('book_id'))
    chapter_id = clean_string(request.form.get('chapter_id'))
    value = clean_string(request.form.get('value'))
    user_id = get_uid(user_details)

    if is_blank(book_id):
        return generate_failure_response('book_id parameter is required', messages=[msg_missing_parameter('book_id')])

    if is_blank(chapter_id):
        return generate_failure_response('chapter_id parameter is required',
                                         messages=[msg_missing_parameter('chapter_id')])

    if is_blank(value):
        return generate_failure_response('value parameter is required', messages=[msg_missing_parameter('value')])

    book = find_book_by_id(book_id)

    if book is None:
        return generate_failure_response('book not found', 404, messages=[msg_action_cancelled_wrong()])

    max_rating = get_volume_max_rating(user_details)

    if book.rating > max_rating:
        return generate_failure_response('User is not allowed to view content out of their rating zone',
                                         messages=[msg_access_denied_content_rating()])

    client_page = None
    client_progress = None

    if book.style == 'S':
        if value.startswith('@'):
            client_progress = float(value[1:])  # Extract substring and convert to float
        else:
            client_progress = int(value)  # Convert to integer
    else:
        if value.startswith('@'):
            client_page = 0
        else:
            client_page = int(value)

    upsert_recent(user_id, book_id, chapter_id, client_page, client_progress,
                  datetime.now(timezone.utc), db.session)

    return generate_success_response('')


# ==============================================================================
# Recent History: Retrieve reading history
# ==============================================================================

@volume_blueprint.route('/list/history', methods=['POST'])
@feature_required(volume_blueprint, VIEW_BOOKS)
def list_history(user_details):
    """
    Retrieve the user's recent reading history entries.

    Args:
        user_details (dict): Authenticated user info (injected). No form params are used.

    Returns:
        tuple: 200 on success with ``{"history": [{"name": book_name, "book": book_id, "chapter": chapter_id,
               "mode": "page"|"scroll", "page": value, "timestamp": "yyyymmdd"}]}``.
               Skips any entries that have neither a page number nor a progress percentage.
    """
    user_uid = get_uid(user_details)
    max_rating = get_volume_max_rating(user_details)

    rows = find_recent_entries(user_uid, max_rating)

    results = []

    for row, book_name in rows:

        if row.page_number is not None:
            mode = 'page'
            value = str(row.page_number)
        elif row.page_percent is not None:
            mode = 'scroll'
            value = f'{row.page_percent:.5f}'
        else:
            continue

        the_time = convert_datetime_to_yyyymmdd(row.timestamp)

        results.append(
            {"name": book_name, "book": row.book_id, "chapter": row.chapter_id, "mode": mode, "page": value,
             "timestamp": the_time})

    return generate_success_response('', {"history": results})


# ==============================================================================
# Bookmarks: Manage reading bookmarks
# ==============================================================================

@volume_blueprint.route('/bookmarks/list', methods=['POST'])
@feature_required(volume_blueprint, BOOKMARKS | VIEW_BOOKS)
def get_bookmarks(user_details: dict) -> tuple:
    """
    Retrieve a list of bookmarks for the authenticated user.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the list of bookmarks and HTTP status code.
    """
    uid = user_details['uid']
    book_id = clean_string(request.form.get('book_id'))

    rows = find_bookmarks(uid, book_id)
    items = []

    for row in rows:
        value_page = ''
        value_progress = ''

        if row.page_percent is not None:
            value_progress = f'{row.page_percent:.5f}'
        elif row.page_number is not None:
            value_page = f'{row.page_number}'
        else:
            continue

        items.append({"id": row.id, "book": row.book_id, "chapter": row.chapter_id, "page": value_page,
                      "progress": value_progress})

    return generate_success_response('', {'items': items})


@volume_blueprint.route('/bookmarks/add', methods=['POST'])
@feature_required(volume_blueprint, BOOKMARKS | VIEW_BOOKS)
def add_bookmark(user_details: dict) -> tuple:
    """
    Add a bookmark for the authenticated user.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the status of the operation and HTTP status code.
    """
    uid = user_details['uid']

    book_id = clean_string(request.form.get('book_id'))
    chapter_id = clean_string(request.form.get('chapter_id'))
    page_value = clean_string(request.form.get('page_number'))

    if is_blank(book_id):
        return generate_failure_response('book_id parameter is required', messages=[msg_missing_parameter('book_id')])

    if is_blank(chapter_id):
        return generate_failure_response('chapter_id parameter is required',
                                         messages=[msg_missing_parameter('chapter_id')])

    if is_blank(page_value):
        return generate_failure_response('page_number parameter is required',
                                         messages=[msg_missing_parameter('page_number')])

    if page_value.startswith('@'):
        page_progress = float(page_value[1:])
        page_number = None
    else:
        page_number = int(page_value)
        page_progress = None

    add_volume_bookmark(db.session, uid, book_id, chapter_id, page_number, page_progress)

    return generate_success_response('')


@volume_blueprint.route('/bookmarks/remove', methods=['POST'])
@feature_required(volume_blueprint, BOOKMARKS | VIEW_BOOKS)
def remove_bookmark(user_details: dict) -> tuple:
    """
    Remove a bookmark for the authenticated user.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the status of the operation and HTTP status code.
    """
    uid = user_details['uid']
    row_id = clean_string(request.form.get('row_id'))

    if is_blank(row_id):
        return generate_failure_response('row_id parameter is required', messages=[msg_missing_parameter('row_id')])

    if not is_integer(row_id):
        return generate_failure_response('row_id parameter is invalid', messages=[msg_invalid_parameter('row_id')])

    if remove_volume_bookmark(db.session, uid, int(row_id)):
        return generate_success_response('')
    else:
        return generate_failure_response('bookmark not found')


# ==============================================================================
# Book Details & CRUD: Get, create, update, and delete book metadata
# ==============================================================================

@volume_blueprint.route('/details', methods=['POST'])
@shall_authenticate_user(volume_blueprint)
def get_book_details(user_details: dict) -> tuple:
    """
    Retrieve details of a specific book.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the book details and HTTP status code.
    """
    book_id = clean_string(request.form.get('book_id'))

    if is_blank(book_id):
        return generate_failure_response('book_id parameter is required', messages=[msg_missing_parameter('book_id')])

    book = find_book_by_id(book_id)

    if book is None:
        return generate_failure_response('Book not found', 404, messages=[msg_action_cancelled_wrong()])

    return generate_success_response('', {
        "info": {
            "id": book.id,
            "name": book.name,
            "alt_name": book.alt_name if book.alt_name else "",
            "processor": book.processor,
            "active": book.active,
            "info_url": book.info_url,
            "rss_url": book.rss_url,
            "extra_url": book.extra_url,
            "start_chapter": book.start_chapter,
            "skip": book.skip,
            "rating": book.rating,
            "tags": book.tags.split(',') if book.tags else [],
            "style": 'page' if book.style == 'P' else 'scroll'
        }
    })


BOOK_FIELDS = ['id', 'name', 'alt_name', 'processor', 'active', 'info_url', 'rss_url', 'extra_url', 'start_chapter',
               'skip',
               'rating', 'tags', 'style']
BOOK_REQUIRED_FIELDS = ['id', 'name', 'processor', 'active', 'info_url', 'rating', 'style']
BOOK_DELETE_FIELDS = ['id']


def acquire_book_fields(book_data):
    return {
        'id': clean_string(book_data['id']),
        'name': clean_string(book_data['name']),
        'alt_name': clean_string(book_data['alt_name']),
        'processor': clean_string(book_data['processor']),
        'active': book_data['active'].lower() == 'true',
        'info_url': clean_string(book_data['info_url']),
        'rss_url': clean_string(book_data['rss_url']),
        'extra_url': clean_string(book_data['extra_url']),
        'start_chapter': clean_string(book_data['start_chapter']),
        'skip': book_data['skip'],
        'rating': book_data['rating'],
        'tags': book_data['tags'],
        'style': 'P' if book_data['style'] == 'page' else 'S'
    }


@volume_blueprint.route('/new', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def new_book(user_details: dict) -> tuple:
    """
    Add a new book to the library.

    Returns:
    tuple: JSON response with the status of the operation and HTTP status code.
    """

    book_data = {}
    for field in BOOK_FIELDS:
        book_data[field] = clean_string(request.form.get(field))

    for field in BOOK_REQUIRED_FIELDS:
        if field not in book_data or is_blank(book_data[field]):
            return generate_failure_response(f'{field} parameter is required', messages=[msg_missing_parameter(field)])

    book_id = clean_string(book_data['id']).lower()

    if not is_valid_book_id(book_id):
        return generate_failure_response('Invalid book ID format', messages=[msg_invalid_parameter('book_id')])

    new_book_data = acquire_book_fields(book_data)

    if new_book_data['processor'] == '@AUTO':
        info_url = new_book_data.get('info_url', '')
        if is_not_blank(info_url):
            processors = current_app.config[APP_KEY_PROCESSORS]
            for processor in processors:
                if processor.is_valid_url(info_url):
                    new_book_data['processor'] = processor.processor_id
                    break

    if new_book_data['processor'] == '@AUTO':
        return generate_failure_response('Unknown processor', messages=[msg_action_failed()])

    # Insert the new book into the database
    try:
        upsert_book(new_book_data['id'], new_book_data['name'], new_book_data['alt_name'], new_book_data['processor'],
                    new_book_data['active'], new_book_data['info_url'], new_book_data['rss_url'],
                    new_book_data['extra_url'], new_book_data['start_chapter'], new_book_data['skip'],
                    new_book_data['rating'], new_book_data['tags'], new_book_data['style'], db_session=db.session)

    except Exception as e:
        db.session.rollback()
        return generate_failure_response(f'Error inserting new book: {str(e)}', messages=[msg_action_failed()])

    return generate_success_response('Book added successfully', messages=[msg_book_added()])


@volume_blueprint.route('/update', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def update_book(user_details: dict) -> tuple:
    """
    Update an existing book in the library.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the status of the operation and HTTP status code.
    """
    book_data = {}
    for field in BOOK_FIELDS:
        book_data[field] = clean_string(request.form.get(field))

    for field in BOOK_REQUIRED_FIELDS:
        if field not in book_data or is_blank(book_data[field]):
            return generate_failure_response(f'{field} parameter is required', messages=[msg_missing_parameter(field)])

    book_id = book_data['id']

    existing_book = find_book_by_id(book_id)

    if existing_book is None:
        return generate_failure_response(f'Book with ID {book_id} does not exist', 404,
                                         messages=[msg_action_cancelled_wrong()])

    updated_book = acquire_book_fields(book_data)

    if updated_book['processor'] == '@AUTO':
        info_url = updated_book.get('info_url', '')
        if is_not_blank(info_url):
            processors = current_app.config[APP_KEY_PROCESSORS]
            for processor in processors:
                if processor.is_valid_url(info_url):
                    updated_book['processor'] = processor.processor_id
                    break

    if updated_book['processor'] == '@AUTO':
        return generate_failure_response('Unknown processor', messages=[msg_action_failed()])

    # Update the existing book in the database
    try:
        upsert_book(updated_book['id'], updated_book['name'], updated_book['alt_name'], updated_book['processor'],
                    updated_book['active'],
                    updated_book['info_url'], updated_book['rss_url'], updated_book['extra_url'],
                    updated_book['start_chapter'], updated_book['skip'], updated_book['rating'], updated_book['tags'],
                    updated_book['style'], db_session=db.session)

    except Exception as e:
        db.session.rollback()
        return generate_failure_response(f'Error updating book: {str(e)}', messages=[msg_action_failed()])

    return generate_success_response('Book updated successfully', messages=[msg_operation_complete()])


@volume_blueprint.route('/remove', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def remove_book(user_details: dict) -> tuple:
    """
    Remove a book from the library.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the status of the operation and HTTP status code.
    """
    book_data = {}
    for field in BOOK_FIELDS:
        book_data[field] = clean_string(request.form.get(field))

    for field in BOOK_DELETE_FIELDS:
        if field not in book_data or is_blank(book_data[field]):
            return generate_failure_response(f'{field} parameter is required', messages=[msg_missing_parameter(field)])

    book_id = clean_string(book_data['id'])
    existing_book = find_book_by_id(book_id)

    if existing_book is None:
        return generate_failure_response(f'Book with ID {book_id} does not exist', 404,
                                         messages=[msg_action_cancelled_wrong()])

    if manage_remove_book(existing_book):
        folder_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], existing_book.id)
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path, ignore_errors=True)
    else:
        return generate_failure_response(f'Error removing book: {str(book_id)}', messages=[msg_action_failed()])

    return generate_success_response('Book removed successfully', messages=[msg_book_removed()])


# ==============================================================================
# Book Key Values: Manage per-book key/value rows
# ==============================================================================

def _acquire_book_for_access(user_details: dict, book_id: str) -> tuple:
    """
    Resolve a book by id and verify the user is allowed to view it.

    Args:
    user_details (dict): Details of the authenticated user.
    book_id (str): The book identifier to resolve.

    Returns:
    tuple: (book, None) on success, or (None, failure_response) when the book
    is missing or the user is not permitted to see it.
    """
    max_rating = get_volume_max_rating(user_details)
    book = find_book_by_id(book_id)

    if book is None:
        return None, generate_failure_response('Could not find book', messages=[msg_action_cancelled_wrong()])

    if book.rating > max_rating:
        return None, generate_failure_response('You are not allowed to view this book',
                                               messages=[msg_access_denied_content_rating()])

    return book, None


@volume_blueprint.route('/keys/list', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def list_book_keys(user_details: dict) -> tuple:
    """
    Retrieve all key/value rows stored for a book.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the list of key/value rows and HTTP status code.
    """
    book_id = clean_string(request.form.get('book_id'))

    if is_blank(book_id):
        return generate_failure_response('book_id parameter is required', messages=[msg_missing_parameter('book_id')])

    book, error = _acquire_book_for_access(user_details, book_id)
    if error is not None:
        return error

    items = []
    for row in find_book_key_values(book_id):
        items.append({"id": row.id, "book": row.book_id, "key": row.key,
                      "value": row.value if row.value is not None else "", "purpose": row.purpose})

    return generate_success_response('', {'items': items})


@volume_blueprint.route('/keys/get', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def get_book_key(user_details: dict) -> tuple:
    """
    Retrieve a single key/value row for a book.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the key/value row and HTTP status code.
    """
    book_id = clean_string(request.form.get('book_id'))
    row_id = clean_string(request.form.get('row_id'))

    if is_blank(book_id):
        return generate_failure_response('book_id parameter is required', messages=[msg_missing_parameter('book_id')])

    if is_blank(row_id):
        return generate_failure_response('row_id parameter is required', messages=[msg_missing_parameter('row_id')])

    if not is_integer(row_id):
        return generate_failure_response('row_id parameter is invalid', messages=[msg_invalid_parameter('row_id')])

    book, error = _acquire_book_for_access(user_details, book_id)
    if error is not None:
        return error

    row = find_book_key_value(book_id, int(row_id))

    if row is None:
        return generate_failure_response('Key not found', messages=[msg_action_cancelled_wrong()])

    return generate_success_response('', {'info': {"id": row.id, "book": row.book_id, "key": row.key,
                                                   "value": row.value if row.value is not None else "",
                                                   "purpose": row.purpose}})


@volume_blueprint.route('/keys/insert', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def insert_book_key(user_details: dict) -> tuple:
    """
    Add a key/value row for a book.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the status of the operation and HTTP status code.
    """
    book_id = clean_string(request.form.get('book_id'))
    key = clean_string(request.form.get('key'))
    value = clean_string(request.form.get('value'))
    purpose = clean_string(request.form.get('purpose'))

    if is_blank(book_id):
        return generate_failure_response('book_id parameter is required', messages=[msg_missing_parameter('book_id')])

    if is_blank(key):
        return generate_failure_response('key parameter is required', messages=[msg_missing_parameter('key')])

    if is_not_blank(purpose) and not is_integer(purpose):
        return generate_failure_response('purpose parameter is invalid', messages=[msg_invalid_parameter('purpose')])

    book, error = _acquire_book_for_access(user_details, book_id)
    if error is not None:
        return error

    effective_value = value if is_not_blank(value) else None
    effective_purpose = int(purpose) if is_not_blank(purpose) else BOOK_KEY_PURPOSE_ALT_VALUE

    row = add_book_key_value(db.session, book_id, key, effective_value, effective_purpose)
    if row is None:
        return generate_failure_response('Key already exists or other exception, please see log', 400,
                                         messages=[msg_action_cancelled_wrong()])

    return generate_success_response('Key added successfully', {'id': row.id},
                                     messages=[msg_operation_complete()])


@volume_blueprint.route('/keys/update', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def update_book_key(user_details: dict) -> tuple:
    """
    Update an existing key/value row for a book.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the status of the operation and HTTP status code.
    """
    book_id = clean_string(request.form.get('book_id'))
    row_id = clean_string(request.form.get('row_id'))
    value = clean_string(request.form.get('value'))
    purpose = clean_string(request.form.get('purpose'))

    if is_blank(book_id):
        return generate_failure_response('book_id parameter is required', messages=[msg_missing_parameter('book_id')])

    if is_blank(row_id):
        return generate_failure_response('row_id parameter is required', messages=[msg_missing_parameter('row_id')])

    if not is_integer(row_id):
        return generate_failure_response('row_id parameter is invalid', messages=[msg_invalid_parameter('row_id')])

    if is_not_blank(purpose) and not is_integer(purpose):
        return generate_failure_response('purpose parameter is invalid', messages=[msg_invalid_parameter('purpose')])

    book, error = _acquire_book_for_access(user_details, book_id)
    if error is not None:
        return error

    effective_value = value if is_not_blank(value) else None
    effective_purpose = int(purpose) if is_not_blank(purpose) else None

    if update_book_key_value(db.session, book_id, int(row_id), effective_value, effective_purpose) is None:
        return generate_failure_response('Key not found', messages=[msg_action_cancelled_wrong()])

    return generate_success_response('Key updated successfully', messages=[msg_operation_complete()])


@volume_blueprint.route('/keys/delete', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def delete_book_key(user_details: dict) -> tuple:
    """
    Remove a key/value row for a book.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the status of the operation and HTTP status code.
    """
    book_id = clean_string(request.form.get('book_id'))
    row_id = clean_string(request.form.get('row_id'))

    if is_blank(book_id):
        return generate_failure_response('book_id parameter is required', messages=[msg_missing_parameter('book_id')])

    if is_blank(row_id):
        return generate_failure_response('row_id parameter is required', messages=[msg_missing_parameter('row_id')])

    if not is_integer(row_id):
        return generate_failure_response('row_id parameter is invalid', messages=[msg_invalid_parameter('row_id')])

    book, error = _acquire_book_for_access(user_details, book_id)
    if error is not None:
        return error

    if remove_book_key_value(db.session, book_id, int(row_id)):
        return generate_success_response('Key removed successfully', messages=[msg_operation_complete()])
    else:
        return generate_failure_response('Key not found', messages=[msg_action_cancelled_wrong()])


@volume_blueprint.route('/keys/gen', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def gen_book_keys(user_details: dict) -> tuple:
    """
    Generate the web scraper key rows required by a book's processor.

    Looks up the book's processor, asks it which keys its remote scraper
    needs, and inserts any missing rows with a blank value.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the list of created keys and HTTP status code.
    """
    book_id = clean_string(request.form.get('book_id'))

    if is_blank(book_id):
        return generate_failure_response('book_id parameter is required', messages=[msg_missing_parameter('book_id')])

    book, error = _acquire_book_for_access(user_details, book_id)
    if error is not None:
        return error

    processor = None
    for p in current_app.config[APP_KEY_PROCESSORS]:
        if p.processor_id == book.processor:
            processor = p
            break

    if processor is None:
        return generate_failure_response(f'Unknown processor: {book.processor}', messages=[msg_action_failed()])

    key_names = list(processor.get_remote_scrape_key_names())

    # last_only is an always-available key for every remote plugin, so it is
    # always offered alongside the processor-specific keys.
    if processor.is_remote_process() and 'last_only' not in key_names:
        key_names.append('last_only')

    if not key_names:
        return generate_failure_response('Processor does not require any web scraper keys',
                                         messages=[msg_action_failed()])

    existing_keys = {row.key for row in find_book_key_values(book_id)
                     if row.purpose == BOOK_KEY_PURPOSE_ALT_VALUE}

    created = []
    for key_name in key_names:
        if key_name in existing_keys:
            continue

        row = add_book_key_value(db.session, book_id, key_name, None, BOOK_KEY_PURPOSE_ALT_VALUE)
        if row is not None:
            created.append(row.key)

    return generate_success_response('Web scraper keys generated', {'created': created},
                                     messages=[msg_operation_complete()])


# ==============================================================================
# Image Editing: Split, merge, remove files within chapters
# ==============================================================================

@volume_blueprint.route('/remove/image', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def remove_image(user_details):
    max_rating = get_volume_max_rating(user_details)
    book_id = clean_string(request.form.get('book_id'))
    chapter_id = clean_string(request.form.get('chapter_id'))
    file_name = clean_string(request.form.get('file_name'))

    book_row = find_book_by_id(book_id)

    if book_row is None:
        return generate_failure_response('Could not find book', messages=[msg_action_cancelled_wrong()])

    if book_row.rating > max_rating:
        return generate_failure_response('You are not allowed to view this book',
                                         messages=[msg_access_denied_content_rating()])

    chapter_row = find_chapter_by_id(book_id, chapter_id)

    if chapter_row is None:
        return generate_failure_response('Could not find chapter', messages=[msg_action_cancelled_wrong()])

    current_images = decompress_filenames(chapter_row.image_names) if chapter_row.image_names else []
    was_first = len(current_images) > 0 and current_images[0] == file_name

    if chapter_row.remove_image(file_name):
        file_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_id, chapter_id, file_name)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.unlink(file_path)
            if not os.path.exists(file_path):
                db.session.commit()

                if was_first:
                    updated_images = decompress_filenames(chapter_row.image_names) if chapter_row.image_names else []
                    if updated_images:
                        new_first_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_id,
                                                      chapter_id, updated_images[0])
                        preview_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_id,
                                                    '.previews', chapter_id + '.webp')
                        if os.path.exists(new_first_path):
                            try:
                                resize_image(new_first_path, preview_path, 200, 'WEBP')
                            except Exception as e:
                                logging.error(f'Could not regenerate chapter thumbnail: {e}')

                return generate_success_response('Image removed', messages=[msg_operation_complete()])
            else:
                db.session.rollback()
                return generate_failure_response('Could not erase image', messages=[msg_action_failed()])
        else:
            db.session.commit()
            return generate_success_response('Image already missing', messages=[msg_action_failed()])
    else:
        return generate_failure_response('Image not found in chapter', messages=[msg_action_failed()])


@volume_blueprint.route('/merge/image', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def merge_image(user_details):
    max_rating = get_volume_max_rating(user_details)
    book_id = clean_string(request.form.get('book_id'))
    chapter_id = clean_string(request.form.get('chapter_id'))
    file_name = clean_string(request.form.get('file_name'))
    alt_file_name = clean_string(request.form.get('alt_file_name'))
    is_horizontal = request.form.get('is_horizontal') == 'true'

    book_row = find_book_by_id(book_id)

    if book_row is None:
        return generate_failure_response('Could not find book', messages=[msg_action_cancelled_wrong()])

    if book_row.rating > max_rating:
        return generate_failure_response('You are not allowed to view this book',
                                         messages=[msg_access_denied_content_rating()])

    chapter_row = find_chapter_by_id(book_id, chapter_id)

    if chapter_row is None:
        return generate_failure_response('Could not find chapter', messages=[msg_action_cancelled_wrong()])

    file_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_id, chapter_id, file_name)
    alt_file_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_id, chapter_id, alt_file_name)

    if os.path.exists(file_path) and os.path.isfile(file_path) and os.path.exists(alt_file_path) and os.path.isfile(
            alt_file_path):
        try:
            if merge_two_images(file_path, alt_file_path, is_horizontal):
                if chapter_row.remove_image(alt_file_name):
                    db.session.commit()
                    return generate_success_response('Image Merged', messages=[msg_operation_complete()])
                else:
                    return generate_failure_response('Image remove, but reference was not erased.',
                                                     messages=[msg_action_failed()])
            else:
                return generate_failure_response('Unable to merge images', messages=[msg_action_failed()])
        except ValueError as ve:
            return generate_failure_response(str(ve))
    else:
        return generate_failure_response('Image not found in chapter', messages=[msg_action_failed()])


@volume_blueprint.route('/split/image', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def split_image(user_details):
    max_rating = get_volume_max_rating(user_details)
    book_id = clean_string(request.form.get('book_id'))
    chapter_id = clean_string(request.form.get('chapter_id'))
    file_name = clean_string(request.form.get('file_name'))

    position = clean_string(request.form.get('position'))
    is_horizontal = clean_string(request.form.get('is_horizontal'))
    keep_first = clean_string(request.form.get('keep_first'))

    if is_blank(position):
        return generate_failure_response('position parameter is required', messages=[msg_missing_parameter('position')])
    elif not is_integer(position):
        return generate_failure_response('position parameter is not an integer',
                                         messages=[msg_invalid_parameter('position')])
    else:
        position = int(position)

    if is_blank(is_horizontal):
        return generate_failure_response('is_horizontal parameter is required',
                                         messages=[msg_missing_parameter('is_horizontal')])
    elif not is_boolean(is_horizontal):
        return generate_failure_response('is_horizontal parameter is not an boolean',
                                         messages=[msg_invalid_parameter('is_horizontal')])
    else:
        is_horizontal = parse_boolean(is_horizontal)

    if is_blank(keep_first):
        return generate_failure_response('keep_first parameter is required',
                                         messages=[msg_missing_parameter('position')])
    elif not is_boolean(keep_first):
        return generate_failure_response('keep_first parameter is not an boolean',
                                         messages=[msg_invalid_parameter('position')])
    else:
        keep_first = parse_boolean(keep_first)

    book_row = find_book_by_id(book_id)

    if book_row is None:
        return generate_failure_response('Could not find book', messages=[msg_action_cancelled_wrong()])

    if book_row.rating > max_rating:
        return generate_failure_response('You are not allowed to view this book',
                                         messages=[msg_access_denied_content_rating()])

    chapter_row = find_chapter_by_id(book_id, chapter_id)

    if chapter_row is None:
        return generate_failure_response('Could not find chapter', messages=[msg_action_cancelled_wrong()])

    file_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_id, chapter_id, file_name)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        try:
            split_and_save_image(file_path, position, is_horizontal, keep_first)
            return generate_success_response('Image adjusted', messages=[msg_operation_complete()])
        except ValueError as ve:
            return generate_failure_response(str(ve))
    else:
        return generate_failure_response('Image not found', messages=[msg_action_failed()])


@volume_blueprint.route('/remove/chapter', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def remove_chapter(user_details):
    max_rating = get_volume_max_rating(user_details)
    book_id = clean_string(request.form.get('book_id'))
    chapter_id = clean_string(request.form.get('chapter_id'))
    exclude_chapter = clean_string(request.form.get('exclude_chapter'))

    book_row = find_book_by_id(book_id)

    if book_row is None:
        return generate_failure_response('Could not find book', messages=[msg_action_cancelled_wrong()])

    if book_row.rating > max_rating:
        return generate_failure_response('You are not allowed to view this book',
                                         messages=[msg_access_denied_content_rating()])

    chapter_row = find_chapter_by_id(book_id, chapter_id)

    if chapter_row is None:
        return generate_failure_response('Could not find chapter', messages=[msg_action_cancelled_wrong()])

    folder_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_id, chapter_id)

    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)

    preview_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_id, '.previews',
                                chapter_id + '.webp')

    if os.path.exists(preview_path):
        os.unlink(preview_path)

    db.session.delete(chapter_row)

    if exclude_chapter == '1':
        existing_book_value = book_row.skip

        if existing_book_value is None or len(existing_book_value) == 0:
            book_row.skip = chapter_id
        else:
            book_row.skip = book_row.skip + "," + chapter_id

    db.session.commit()

    return generate_success_response('chapter removed', messages=[msg_operation_complete()])


# ==============================================================================
# Image Serving: Deliver images and previews to the client
# ==============================================================================

def _error_image_response(reason: str, status: int = 404):
    """Return a small grey placeholder PNG with an X-Image-Error header."""
    img = Image.new('RGB', (64, 64), color=(80, 80, 80))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    response = make_response(send_file(buf, mimetype='image/png'), status)
    response.headers['X-Image-Error'] = reason
    response.headers['Cache-Control'] = 'no-store'
    return response


@volume_blueprint.route('/serve_image/<book_folder>/<chapter_name>/<image_name>', methods=['GET'])
@feature_required_with_cookie(volume_blueprint, VIEW_BOOKS)
def serve_image(user_details, book_folder: str, chapter_name: str, image_name: str) -> 'Response':
    """
    Serve an image file from the server.
    """
    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400)

    book_folder = secure_filename(book_folder)
    chapter_name = secure_filename(chapter_name)
    image_name = secure_filename(image_name)

    book_record = find_book_by_id(book_folder)
    if not book_record:
        return generate_failure_response('Volume not found', 404)

    # Check user rating access
    max_rating = get_volume_max_rating(user_details)
    if book_record.rating > max_rating:
        return generate_failure_response('User is not allowed to view content out of their rating zone')

    file_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_folder, chapter_name, image_name)

    if not (os.path.exists(file_path) and os.path.isfile(file_path)):
        logging.warning('File not found: ' + file_path)
        return _error_image_response('file-not-found')

    # Check for quick mode
    quick = request.args.get('quick', 'false').lower() == 'true'

    if quick:
        try:
            # Open, flatten to RGB (discard alpha) and shrink the image
            with Image.open(file_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                width, height = img.size
                if width > 256:
                    new_height = int((256 / width) * height)
                    img = img.resize((256, new_height), Image.LANCZOS)

                # Save to in-memory bytes
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='WEBP')
                img_bytes.seek(0)

            # Build the Flask response
            response = make_response(send_file(img_bytes, mimetype='image/webp'))
            expires_at = datetime.now() + timedelta(minutes=1)
            response.headers['Cache-Control'] = 'public, max-age=60'
            response.headers['Expires'] = expires_at.strftime('%a, %d %b %Y %H:%M:%S GMT')
            return response

        except Exception as e:
            logging.exception(f'Error generating quick image for {file_path}: {e}')
            return _error_image_response(f'quick-resize-failed: {e}', 500)

    # Default: full-size image, 5-hour cache
    response = make_response(send_from_directory(os.path.dirname(file_path), os.path.basename(file_path)))
    expires_at = datetime.now() + timedelta(hours=5)
    response.headers['Cache-Control'] = 'public, max-age=18000'  # 5 hours
    response.headers['Expires'] = expires_at.strftime('%a, %d %b %Y %H:%M:%S GMT')
    return response


@volume_blueprint.route('/serve_preview/<book_folder>/<chapter_name>', methods=['GET'])
@feature_required_with_cookie(volume_blueprint, VIEW_BOOKS)
def serve_preview_image(user_details, book_folder: str, chapter_name: str) -> 'Response':
    """
    Serve a preview image file from the server.

    Args:
    book_folder (str): The folder containing the book.
    chapter_name (str): The name of the chapter.

    Returns:
    Response: The preview image file or a 404 error if not found.
    """
    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400)

    book_folder = secure_filename(book_folder)
    chapter_name = secure_filename(chapter_name)

    file_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_folder, '.previews',
                             chapter_name + '.webp')

    if os.path.exists(file_path) and os.path.isfile(file_path):
        response = make_response(send_from_directory(os.path.dirname(file_path), os.path.basename(file_path)))
        expires_at = datetime.now() + timedelta(hours=5)
        response.headers['Cache-Control'] = 'public, max-age=18000'  # 5 hours cache
        response.headers['Expires'] = expires_at.strftime('%a, %d %b %Y %H:%M:%S GMT')
        return response
    else:
        logging.warning('File not found: ' + file_path)
        return _error_image_response('preview-not-found')


@volume_blueprint.route('/download/chapter/<book_folder>/<chapter_name>', methods=['GET'])
@feature_required_with_cookie(volume_blueprint, VIEW_BOOKS)
def download_chapter(user_details, book_folder: str, chapter_name: str) -> 'Response':
    """
    Download a zip archive (stored, no compression) containing all images of a chapter.

    Image names inside the archive are renumbered from 0001 sequentially,
    keeping each file's original extension (e.g. 0001.webp, 0002.png, 0003.jpg).

    The zip is built on disk in the temp folder and streamed to the client,
    so memory usage stays flat regardless of chapter size. The temp file is
    removed once the response is sent.

    Args:
        book_folder (str): The book id whose chapter to download.
        chapter_name (str): The chapter id to download.

    Returns:
        Response: A zip file attachment named ``<book_id>_<chapter_id>.zip``.
    """
    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400)

    book_folder = secure_filename(book_folder)
    chapter_name = secure_filename(chapter_name)

    book_record = find_book_by_id(book_folder)
    if not book_record:
        return generate_failure_response('Volume not found', 404)

    max_rating = get_volume_max_rating(user_details)
    if book_record.rating > max_rating:
        return generate_failure_response('User is not allowed to view content out of their rating zone')

    chapter_record = find_chapter_by_id(book_folder, chapter_name)
    if chapter_record is None:
        return generate_failure_response('Chapter not found', 404)

    files = decompress_filenames(chapter_record.image_names) if chapter_record.image_names else []

    if not files:
        return generate_failure_response('Chapter has no images')

    chapter_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_folder, chapter_name)

    source_files = []

    for file_name in files:
        file_path = os.path.join(chapter_path, file_name)
        if os.path.isfile(file_path):
            source_files.append((file_path, os.path.splitext(file_name)[1]))
        else:
            logging.warning(f'Skipping missing chapter image while zipping: {file_path}')

    if not source_files:
        return generate_failure_response('No chapter images found on disk', 404)

    temp_dir = tempfile.gettempdir()
    zip_path = os.path.join(temp_dir, f'{uuid.uuid4()}.zip')

    try:
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_STORED) as archive:
            for index, (file_path, ext) in enumerate(source_files, start=1):
                archive.write(file_path, arcname=f'{index:04d}{ext}')
    except Exception:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        raise

    @after_this_request
    def remove_file(response):
        try:
            os.remove(zip_path)
        except Exception:
            current_app.logger.exception('Failed to remove temporary zip file')
        return response

    return send_file(
        zip_path,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'{book_folder}_{chapter_name}.zip'
    )


@volume_blueprint.route('/upload/chapter', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def upload_chapter(user_details):
    """
    Upload a chapter from a zip archive of images.

    This is the inverse of ``download_chapter``. The archive contains images named
    ``0001.<ext>``, ``0002.<ext>``, ... (or ``N.<ext>``) where ``<ext>`` may be
    ``.png``, ``.webp``, ``.jpg`` or ``.jpeg``. All images are renumbered from 1
    in archive order, a single page is extracted at a time (so memory stays flat
    even for hundreds of megabyte zips) and stored in the chapter folder.

    Once the archive is validated, any existing chapter with the same id is
    erased (files, preview and database row) and replaced by the uploaded pages.
    No image processing is done here; a chapter scan/repair task can be run
    afterwards to generate previews and refresh book metadata.

    Args:
        user_details (dict): Authenticated user info (injected). Form params:
            ``book_id`` (str) and ``chapter_id`` (str). The zip is sent as file
            ``file`` (multipart ``application/zip``).

    Returns:
        tuple: 200 on success with the page count, or 400 if any parameter is
            missing/invalid or the zip contains no usable images.
    """
    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400)

    book_id = clean_string(request.form.get('book_id'))
    chapter_id = clean_string(request.form.get('chapter_id'))
    uploaded_file = request.files['file'] if 'file' in request.files else None

    if is_blank(book_id):
        return generate_failure_response('book_id is required', messages=[msg_missing_parameter('book_id')])

    if not is_valid_book_id(book_id):
        return generate_failure_response('book_id is invalid', messages=[msg_invalid_parameter('book_id')])

    if is_blank(chapter_id):
        return generate_failure_response('chapter_id is required', messages=[msg_missing_parameter('chapter_id')])

    if not re.match(r'^[A-Za-z0-9._-]+$', chapter_id):
        return generate_failure_response('chapter_id is invalid', messages=[msg_invalid_parameter('chapter_id')])

    if uploaded_file is None or uploaded_file.filename == '':
        return generate_failure_response('file is required', messages=[msg_missing_parameter('file')])

    book_row = find_book_by_id(book_id)

    if book_row is None:
        return generate_failure_response('Could not find book', messages=[msg_action_cancelled_wrong()])

    max_rating = get_volume_max_rating(user_details)

    if book_row.rating > max_rating:
        return generate_failure_response('You are not allowed to view this book',
                                         messages=[msg_access_denied_content_rating()])

    volume_folder = current_app.config[PROPERTY_SERVER_VOLUME_FOLDER]
    chapter_folder = os.path.join(volume_folder, book_id, chapter_id)
    preview_path = os.path.join(volume_folder, book_id, '.previews', chapter_id + '.webp')

    order_pattern = re.compile(r'^(\d+)(?:\.(\w+))?$', re.IGNORECASE)
    allowed_extensions = {'.png', '.webp', '.jpg', '.jpeg'}

    temp_dir = None

    try:
        with zipfile.ZipFile(uploaded_file, 'r') as archive:
            ordered_members = []

            for info in archive.infolist():
                if info.is_dir():
                    continue

                base_name = os.path.basename(info.filename)
                match = order_pattern.match(base_name)

                if match is not None:
                    number = int(match.group(1))
                    extension = ('.' + match.group(2)).lower() if match.group(2) else ''
                else:
                    number = 999999999
                    extension = os.path.splitext(base_name)[1].lower()

                ordered_members.append((number, extension, base_name, info))

            if not ordered_members:
                return generate_failure_response('Zip archive contains no files',
                                                 messages=[msg_invalid_parameter('file')])

            if not any(extension in allowed_extensions for _, extension, _, _ in ordered_members):
                return generate_failure_response('Zip archive contains no supported images '
                                                 '(png, webp, jpg, jpeg)',
                                                 messages=[msg_invalid_parameter('file')])

            ordered_members.sort(key=lambda item: item[0])

            # Validation passed: erase any existing chapter so the upload cleanly replaces it
            try:
                if os.path.isdir(chapter_folder):
                    shutil.rmtree(chapter_folder)

                if os.path.isfile(preview_path):
                    os.unlink(preview_path)

                existing_chapter = find_chapter_by_id(book_id, chapter_id)

                if existing_chapter is not None:
                    db.session.delete(existing_chapter)
                    db.session.commit()
            except Exception:
                db.session.rollback()
                logging.exception(f'Failed to erase existing chapter {book_id}/{chapter_id}')
                return generate_failure_response('Failed to erase existing chapter', messages=[msg_server_error()])

            # Extract and renumber images one page at a time so memory stays flat
            temp_dir = tempfile.mkdtemp(prefix=f'chapter_{uuid.uuid4().hex}_')
            os.makedirs(chapter_folder, exist_ok=True)

            new_names = []

            for index, (number, extension, base_name, info) in enumerate(ordered_members, start=1):
                if extension not in allowed_extensions:
                    logging.warning(f'Skipping {base_name} in uploaded chapter: unsupported file type')
                    continue

                try:
                    source_path = archive.extract(info, temp_dir)
                except Exception:
                    logging.warning(f'Skipping {base_name} in uploaded chapter: extraction failed')
                    continue

                if not os.path.isfile(source_path):
                    logging.warning(f'Skipping {base_name} in uploaded chapter: extraction failed')
                    continue

                target_name = f'{index:04d}{extension}'
                target_path = os.path.join(chapter_folder, target_name)

                shutil.move(source_path, target_path)
                new_names.append(target_name)
    except zipfile.BadZipFile:
        logging.exception(f'Invalid zip archive in chapter upload for chapter {book_id}/{chapter_id}')
        return generate_failure_response('Invalid zip archive', messages=[msg_invalid_parameter('file')])
    except Exception:
        logging.exception(f'Chapter upload failed for chapter {book_id}/{chapter_id}')
        return generate_failure_response('Chapter upload failed', messages=[msg_server_error()])
    finally:
        if temp_dir is not None and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

    try:
        page_count = len(new_names)
        max_sequence = db.session.query(func.max(Chapter.sequence)).filter_by(book_id=book_id).scalar()
        sequence = (max_sequence if max_sequence is not None else -1) + 1

        db.session.add(Chapter(
            book_id=book_id,
            chapter_id=chapter_id,
            page_count=page_count,
            image_names=compress_filenames(new_names),
            sequence=sequence,
            date=datetime(2005, 1, 1).date()
        ))

        db.session.commit()
    except Exception:
        db.session.rollback()
        logging.exception(f'Failed to record chapter {book_id}/{chapter_id} in database')
        return generate_failure_response('Failed to record chapter in database', messages=[msg_server_error()])

    return generate_success_response('chapter uploaded', extra_data={
        'book_id': book_id,
        'chapter_id': chapter_id,
        'page_count': page_count
    }, messages=[msg_operation_complete()])


# ==============================================================================
# Utility Routes: Processor list and tag guessing
# ==============================================================================

@volume_blueprint.route('/list/processors', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def get_processors(user_details: dict) -> tuple:
    """
    Retrieve details of all registered processors with their configuration requirements.

    Args:
        user_details (dict): Authenticated user info (injected). No form params are used.

    Returns:
        tuple: 200 on success with ``{"processors": [{"id", "name", "pageDescription", "startId", "startIdDescription",
               "baseUrl", "baseUrlDescription", "rss", "rssDescription"}]}``.
               Each processor object describes its capabilities and which optional fields the client should provide when using it.
    """
    processors = current_app.config[APP_KEY_PROCESSORS]
    modified = []

    for processor in processors:
        modified.append({
            'id': processor.processor_id,
            'name': processor.processor_name,
            'pageDescription': processor.page_description(),
            'startId': processor.requires_starting_page(),
            'startIdDescription': processor.starting_page_description(),
            'baseUrl': processor.requires_base_url(),
            'baseUrlDescription': processor.base_url_description(),
            'rss': processor.requires_rss(),
            'rssDescription': processor.rss_description(),
        })

    return generate_success_response('', {'processors': modified})


@volume_blueprint.route('/guess/tags', methods=['POST'])
@feature_required(volume_blueprint, VIEW_BOOKS)
def guess_tags(user_details: dict) -> tuple:
    """
    Given a space-separated string of words (typically typed by the user), find matching tags from the database.

    The function attempts to extend each word sequence to find an exact tag match (up to 6 words).
    Words that don't match any existing tag become new tags themselves (in uppercase).
    Matched multi-word tags consume all their component words; unmatched single words are added as-is.

    Args:
        user_details (dict): Authenticated user info (injected). No form params are used.
        form.values (str): Space-separated string of words to match against existing tags (required).

    Returns:
        tuple: 200 on success with ``{"tags": ["matched_tag_1", "matched_or_new_tag_2", ...]}``.
               Words that didn't match an exact tag are returned in uppercase as new tag suggestions.
               Returns failure if volume is not ready or values param is missing/blank.
    """
    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400, messages=[msg_server_error()])

    values = clean_string(request.form.get('values'))
    if is_blank(values):
        return generate_failure_response('values parameter is required', messages=[msg_missing_parameter('values')])

    words = [w.upper() for w in values.split() if w.strip()]
    matched_tags = []

    i = 0
    while i < len(words):
        best_match = None

        # Try extending the sequence of words to find an exact tag match
        for j in range(i, min(i + 6, len(words))):
            candidate = ' '.join(words[i:j + 1])
            matching_tags = search_tags(candidate)

            # Check for exact equality among matches
            for tag in matching_tags:
                if tag.name == candidate:
                    best_match = candidate
                    break

            if best_match:
                break

        if best_match:
            # Consume all words that were part of the matched tag
            word_count = len(best_match.split())
            matched_tags.append(best_match)
            i += word_count
        else:
            # No match found - this word is a new tag (unmatched)
            matched_tags.append(words[i])
            i += 1

    return generate_success_response('', {'tags': matched_tags})


@volume_blueprint.route('/scan/duplicates', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def scan_duplicate_images(user_details: dict) -> tuple:
    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400, messages=[msg_server_error()])

    book_id = clean_string(request.form.get('book_id'))

    if is_blank(book_id):
        return generate_failure_response('book_id parameter is required', messages=[msg_missing_parameter('book_id')])

    book = find_book_by_id(book_id)

    if book is None:
        return generate_failure_response(f'Book {book_id} not found', messages=[msg_action_cancelled_wrong()])

    book_folder = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_id)

    chapter_filter_raw = clean_string(request.form.get('chapter_filter'))
    chapter_filter = None
    if is_not_blank(chapter_filter_raw):
        chapter_filter = {c.strip() for c in chapter_filter_raw.split(',') if c.strip()}

    report = scan_for_duplicate_chapters(book_folder, chapter_filter=chapter_filter)

    groups = []
    for hit in report.hits:
        items = [{'chapter': hit.source_chapter, 'filename': hit.source_filename}]
        for match in hit.matches:
            items.append({'chapter': match.chapter, 'filename': match.filename})
        groups.append({'items': items})

    return generate_success_response('', {
        'groups': groups,
        'total_groups': len(groups),
        'chapters_scanned': report.chapters_scanned,
    })


@volume_blueprint.route('/split/image/multi', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_VOLUME)
def split_image_multi(user_details: dict) -> tuple:
    max_rating = get_volume_max_rating(user_details)
    book_id = clean_string(request.form.get('book_id'))
    chapter_id = clean_string(request.form.get('chapter_id'))
    file_name = clean_string(request.form.get('file_name'))
    positions_raw = clean_string(request.form.get('positions'))
    is_horizontal_raw = clean_string(request.form.get('is_horizontal'))

    if is_blank(book_id):
        return generate_failure_response('book_id parameter is required', messages=[msg_missing_parameter('book_id')])
    if is_blank(chapter_id):
        return generate_failure_response('chapter_id parameter is required',
                                         messages=[msg_missing_parameter('chapter_id')])
    if is_blank(file_name):
        return generate_failure_response('file_name parameter is required',
                                         messages=[msg_missing_parameter('file_name')])
    if is_blank(positions_raw):
        return generate_failure_response('positions parameter is required',
                                         messages=[msg_missing_parameter('positions')])
    if is_blank(is_horizontal_raw) or not is_boolean(is_horizontal_raw):
        return generate_failure_response('is_horizontal parameter is required and must be a boolean',
                                         messages=[msg_missing_parameter('is_horizontal')])

    # Parse positions
    try:
        positions = [int(p.strip()) for p in positions_raw.split(',') if p.strip()]
    except ValueError:
        return generate_failure_response('positions must be a comma-separated list of integers',
                                         messages=[msg_invalid_parameter('positions')])

    if not positions:
        return generate_failure_response('positions must contain at least one value',
                                         messages=[msg_invalid_parameter('positions')])

    is_horizontal = parse_boolean(is_horizontal_raw)

    book_row = find_book_by_id(book_id)
    if book_row is None:
        return generate_failure_response('Could not find book', messages=[msg_action_cancelled_wrong()])
    if book_row.rating > max_rating:
        return generate_failure_response('You are not allowed to view this book',
                                         messages=[msg_access_denied_content_rating()])

    chapter_row = find_chapter_by_id(book_id, chapter_id)
    if chapter_row is None:
        return generate_failure_response('Could not find chapter', messages=[msg_action_cancelled_wrong()])

    current_images = decompress_filenames(chapter_row.image_names) if chapter_row.image_names else []
    if file_name not in current_images:
        return generate_failure_response('Image not found in chapter', messages=[msg_action_failed()])

    chapter_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_id, chapter_id)
    source_path = os.path.join(chapter_path, file_name)

    if not os.path.isfile(source_path):
        return generate_failure_response('Image file not found on disk', messages=[msg_action_failed()])

    # Crop pieces to temp files — validates positions inside
    try:
        tmp_paths = split_image_into_pieces(source_path, positions, is_horizontal, chapter_path)
    except ValueError as ve:
        return generate_failure_response(str(ve), messages=[msg_invalid_parameter('positions')])

    piece_count = len(tmp_paths)  # = len(positions) + 1
    extra = piece_count - 1  # slots we need to open up (replace 1 file with N)

    target_index = current_images.index(file_name)
    was_first = target_index == 0

    # Determine zero-padding width from the existing filenames
    _num_match = re.match(r'^(\d+)\.', file_name)
    pad_width = len(_num_match.group(1)) if _num_match else 4

    # Determine the numeric value of file_name so we can compute shifted names
    target_num = int(_num_match.group(1)) if _num_match else (target_index + 1)

    # Shift files that come after the target upward by `extra` slots (two-phase rename)
    files_after = current_images[target_index + 1:]

    if files_after and extra > 0:
        # Phase 1: rename to temp names (reverse order to avoid overwrites)
        temp_map = []
        for fname in reversed(files_after):
            tmp_name = f"__mv_tmp_{fname}"
            os.rename(os.path.join(chapter_path, fname), os.path.join(chapter_path, tmp_name))
            temp_map.append((tmp_name, fname))

        # Phase 2: rename temps to final shifted names
        for tmp_name, original_fname in temp_map:
            m = re.match(r'^(\d+)\.(.+)$', original_fname)
            if m:
                new_num = int(m.group(1)) + extra
                new_name = f"{new_num:0{len(m.group(1))}d}.{m.group(2)}"
            else:
                new_name = original_fname
            os.rename(os.path.join(chapter_path, tmp_name), os.path.join(chapter_path, new_name))

    # Delete original source file
    os.unlink(source_path)

    # Move temp pieces into the now-vacant slots
    new_piece_names = []
    for i, tmp_path in enumerate(tmp_paths):
        piece_num = target_num + i
        piece_name = f"{piece_num:0{pad_width}d}.webp"
        os.rename(tmp_path, os.path.join(chapter_path, piece_name))
        new_piece_names.append(piece_name)

    # Rebuild chapter image list
    before = current_images[:target_index]
    after_shifted = []
    for fname in files_after:
        m = re.match(r'^(\d+)\.(.+)$', fname)
        if m:
            new_num = int(m.group(1)) + extra
            after_shifted.append(f"{new_num:0{len(m.group(1))}d}.{m.group(2)}")
        else:
            after_shifted.append(fname)

    new_image_list = before + new_piece_names + after_shifted
    chapter_row.image_names = compress_filenames(new_image_list)
    chapter_row.page_count = len(new_image_list)
    db.session.commit()

    # Regenerate chapter preview if the split target was the first image
    if was_first and new_piece_names:
        first_path = os.path.join(chapter_path, new_piece_names[0])
        preview_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_id,
                                    '.previews', chapter_id + '.webp')
        if os.path.exists(first_path):
            try:
                resize_image(first_path, preview_path, 200, 'WEBP')
            except Exception as e:
                logging.error(f'Could not regenerate chapter thumbnail: {e}')

    return generate_success_response('Image split successfully', {'files': new_piece_names})
