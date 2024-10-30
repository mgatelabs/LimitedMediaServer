import json
import logging
import os
from datetime import datetime, timedelta, timezone

from flask import Blueprint, send_from_directory, current_app, request, make_response, abort
from werkzeug.utils import secure_filename

from auth_utils import shall_authenticate_user, feature_required, feature_required_with_cookie
from common_utils import generate_success_response, generate_failure_response
from constants import PROPERTY_SERVER_VOLUME_FOLDER, PROPERTY_SERVER_VOLUME_READY
from date_utils import convert_date_to_yyyymmdd
from db import db, Book
from feature_flags import BOOKMARKS, VIEW_BOOKS, MANAGE_BOOK
from number_utils import is_integer
from text_utils import is_blank, clean_string, is_valid_book_id, is_not_blank
from volume_queries import list_books_for_rating, find_chapters_by_book, find_book_by_id, find_chapter_by_id, \
    find_chapter_by_sequence, upsert_book, upsert_recent, \
    find_recent_entry, find_viewed_entries, find_bookmarks, add_volume_bookmark, remove_volume_bookmark, \
    count_books_for_rating
from volume_utils import get_volume_max_rating

volume_blueprint = Blueprint('volume', __name__)


# Book REST Resources

@volume_blueprint.route('/list/books', methods=['POST'])
@feature_required(volume_blueprint, VIEW_BOOKS)
def get_books(user_details: dict) -> tuple:
    """
    Retrieve a list of books based on user details and rating limits.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the list of books and HTTP status code.
    """

    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400)

    offset = clean_string(request.form.get('offset'))
    limit = clean_string(request.form.get('limit'))
    requested_rating_limit = clean_string(request.form.get('rating'))
    sort = clean_string(request.form.get('sort'))
    filter_text = clean_string(request.form.get('filter_text'))

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
        return generate_failure_response('Requested rating is greater then user max level')

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

    total_books = count_books_for_rating(max_rating, filter_text)

    if offset > total_books:
        offset = 0

    books = list_books_for_rating(max_rating, filter_text, book_sort, sort_descending, offset, limit)

    for book in books:
        result = {'id': book.id, 'json': book.id, 'name': book.name, 'rating': book.rating, 'cover': book.cover,
                  'first': book.first_chapter, 'last': book.last_chapter, 'active': book.active,
                  'date': convert_date_to_yyyymmdd(book.last_date),
                  'tags': book.tags.split(',') if book.tags is not None else [],
                  'style': 'page' if book.style == 'P' else 'scroll'}

        book_data.append(result)

    return generate_success_response('', {"books": book_data, "paging": {"total": total_books, "offset": offset}})


@volume_blueprint.route('/list/chapters', methods=['POST'])
@feature_required(volume_blueprint, VIEW_BOOKS)
def get_chapters(user_details: dict) -> tuple:
    """
    Retrieve a list of chapters for a given book.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the list of chapters and HTTP status code.
    """

    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400)

    book_id = clean_string(request.form.get('book_id'))

    if is_blank(book_id):
        return generate_failure_response('book_id parameter is required')

    book = find_book_by_id(book_id)

    if book is None:
        return generate_failure_response(f'Book {book_id} not found')

    max_rating = get_volume_max_rating(user_details)

    if book.rating > max_rating:
        return generate_failure_response('User is not allowed to view content out of their rating zone')

    chapters = find_chapters_by_book(book_id)

    chapter_names = [chapter.chapter_id for chapter in chapters]

    style = 'scroll' if book.style == 'S' else 'page'

    return generate_success_response('', {'chapters': chapter_names, 'style': style})


@volume_blueprint.route('/list/images', methods=['POST'])
@feature_required(volume_blueprint, VIEW_BOOKS)
def get_images(user_details: dict) -> tuple:
    """
    Retrieve a list of images for a given chapter in a book.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the list of images and HTTP status code.
    """

    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400)

    book_id = clean_string(request.form.get('book_id'))
    chapter_id = clean_string(request.form.get('chapter_id'))

    if is_blank(book_id):
        return generate_failure_response('book_id parameter is required')

    if is_blank(chapter_id):
        return generate_failure_response('chapter_id parameter is required')

    book = find_book_by_id(book_id)

    if book is None:
        return generate_failure_response('book not found', 404)

    max_rating = get_volume_max_rating(user_details)

    if book.rating > max_rating:
        return generate_failure_response('User is not allowed to view content out of their rating zone')

    current_chapter = find_chapter_by_id(book_id, chapter_id)

    if current_chapter is None:
        return generate_failure_response('chapter not found')

    prev_chapter_record = find_chapter_by_sequence(book_id, current_chapter.sequence - 1)
    next_chapter_record = find_chapter_by_sequence(book_id, current_chapter.sequence + 1)

    files = current_chapter.image_names.split(',') if current_chapter.image_names else []
    prev_chapter_id = prev_chapter_record.chapter_id if prev_chapter_record else ''
    next_chapter_id = next_chapter_record.chapter_id if next_chapter_record else ''

    return generate_success_response('', {"prev": prev_chapter_id, "next": next_chapter_id, "files": files})


# Image Serving

@volume_blueprint.route('/serve_image/<book_folder>/<chapter_name>/<image_name>', methods=['GET'])
@feature_required_with_cookie(volume_blueprint, VIEW_BOOKS)
def serve_image(user_details, book_folder: str, chapter_name: str, image_name: str) -> 'Response':
    """
    Serve an image file from the server.

    Args:
    book_folder (str): The folder containing the book.
    chapter_name (str): The name of the chapter.
    image_name (str): The name of the image file.

    Returns:
    Response: The image file or a 404 error if not found.
    """
    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400)

    book_folder = secure_filename(book_folder)
    chapter_name = secure_filename(chapter_name)
    image_name = secure_filename(image_name)

    book_record = find_book_by_id(book_folder)
    if not book_record:
        return generate_failure_response('Volume not found', 404)

    # Get the user's max rating
    max_rating = get_volume_max_rating(user_details)

    if book_record.rating > max_rating:
        return generate_failure_response('User is not allowed to view content out of their rating zone')

    file_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_folder, chapter_name, image_name)

    if os.path.exists(file_path) and os.path.isfile(file_path):
        response = make_response(send_from_directory(os.path.dirname(file_path), os.path.basename(file_path)))
        expires_at = datetime.now() + timedelta(hours=5)
        response.headers['Cache-Control'] = 'public, max-age=18000'  # 5 hours cache
        response.headers['Expires'] = expires_at.strftime('%a, %d %b %Y %H:%M:%S GMT')
        return response
    else:
        logging.warning('File not found: ' + file_path)
        abort(404)


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

    file_path = os.path.join(current_app.config[PROPERTY_SERVER_VOLUME_FOLDER], book_folder, '.previews', chapter_name + '.png')

    if os.path.exists(file_path) and os.path.isfile(file_path):
        response = make_response(send_from_directory(os.path.dirname(file_path), os.path.basename(file_path)))
        expires_at = datetime.now() + timedelta(hours=5)
        response.headers['Cache-Control'] = 'public, max-age=18000'  # 5 hours cache
        response.headers['Expires'] = expires_at.strftime('%a, %d %b %Y %H:%M:%S GMT')
        return response
    else:
        logging.warning('File not found: ' + file_path)
        abort(404)


@volume_blueprint.route('/viewed', methods=['POST'])
@feature_required(volume_blueprint, VIEW_BOOKS)
def view_sync(user_details: dict) -> tuple:
    """
    Synchronize the viewed and history data for a user.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the synchronized data and HTTP status code.
    """

    if not current_app.config[PROPERTY_SERVER_VOLUME_READY]:
        return generate_failure_response('Volume service not ready', 400)

    current_user_id = user_details['uid']

    viewed_json_string = request.form.get('viewed')
    history_json_string = request.form.get('history')

    client_viewed_data = None
    client_history_data = None
    if viewed_json_string:
        try:
            client_viewed_data = json.loads(viewed_json_string)
            client_history_data = json.loads(history_json_string)
        except ValueError as e:
            return generate_failure_response('Invalid JSON format')

    in_history = {}

    # History merges
    for client_data in client_history_data:
        book_id = clean_string(client_data['book'])
        client_chapter = clean_string(client_data['chapter'])
        client_value = clean_string(client_data['page'])
        client_timestamp = client_data['timestamp'] / 1000
        client_page = None
        client_progress = None

        if is_blank(client_chapter) or is_blank(book_id):
            continue

        in_history[book_id] = True

        if client_value.startswith('@'):
            client_progress = float(client_value[1:])  # Extract substring and convert to float
        else:
            client_page = int(client_value)  # Convert to integer

        server_timestamp = 0

        recent_entry = find_recent_entry(current_user_id, book_id)
        if recent_entry is not None:
            # Assuming 'row' is the result from your database query
            if recent_entry.timestamp:
                server_timestamp = int(recent_entry.timestamp.timestamp())

        # update it new
        if client_timestamp > server_timestamp:
            upsert_recent(current_user_id, book_id, client_chapter, client_page, client_progress,
                          datetime.fromtimestamp(client_timestamp), db.session)

    # See if something fell through
    for client_key in client_viewed_data:
        if client_key not in in_history:
            in_history[client_key] = True
            value = client_viewed_data[client_key]
            recent_entry = find_recent_entry(current_user_id, client_key)
            if recent_entry is None:
                book = find_book_by_id(client_key, db.session)
                client_page = None
                client_progress = None
                parts = value.split('^')
                if len(parts) < 2:
                    continue
                chapter = parts[0]
                page_progress = parts[1]

                if book.style == 'S':
                    if page_progress.startswith('@'):
                        client_progress = float(page_progress[1:])  # Extract substring and convert to float
                    else:
                        client_progress = int(page_progress)  # Convert to integer
                else:
                    if page_progress.startswith('@'):
                        continue
                    client_page = int(page_progress)

                upsert_recent(current_user_id, book.id, chapter, client_page, client_progress,
                              datetime.now(timezone.utc), db.session)

    recent_rows = find_viewed_entries(current_user_id)

    dest_viewed = {}
    dest_history = []
    count = 0

    if recent_rows:
        for recent in recent_rows:

            if recent.page_percent is not None:
                mode = 'scroll'
                value = f'@{recent.page_percent:.5f}'
            else:
                mode = 'page'
                value = str(recent.page_number)

            if count < 25:
                dest_history.append({"book": recent.book_id, "chapter": recent.chapter_id, "page": value, "mode": mode,
                                     "timestamp": int(recent.timestamp.timestamp()) * 1000})

            count = count + 1

            dest_viewed[recent.book_id] = f'{recent.chapter_id}^{value}'

    return generate_success_response('', {"viewed": dest_viewed, "history": dest_history[:25]})


@volume_blueprint.route('/list/processors', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_BOOK)
def get_processors(user_details: dict) -> tuple:
    """
    Retrieve a list of processors.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the list of processors and HTTP status code.
    """
    processors = current_app.config['PROCESSORS']
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


# Bookmarks

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
        return generate_failure_response('book_id parameter is required')

    if is_blank(chapter_id):
        return generate_failure_response('chapter_id parameter is required')

    if is_blank(page_value):
        return generate_failure_response('page_number parameter is required')

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
        return generate_failure_response('row_id parameter is required')

    if not is_integer(row_id):
        return generate_failure_response('row_id parameter is invalid')

    if remove_volume_bookmark(db.session, uid, int(row_id)):
        return generate_success_response('')
    else:
        return generate_failure_response('bookmark not found')


# Editing

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
        return generate_failure_response('book_id parameter is required')

    book = find_book_by_id(book_id)

    if book is None:
        return generate_failure_response('Book not found', 404)

    return generate_success_response('', {
        "info": {
            "id": book.id,
            "name": book.name,
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


BOOK_FIELDS = ['id', 'name', 'processor', 'active', 'info_url', 'rss_url', 'extra_url', 'start_chapter', 'skip',
               'rating', 'tags', 'style']
BOOK_REQUIRED_FIELDS = ['id', 'name', 'processor', 'active', 'info_url', 'rating', 'style']


def acquire_book_fields(book_data):
    return {
        'id': clean_string(book_data['id']),
        'name': clean_string(book_data['name']),
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


# Modifications

@volume_blueprint.route('/new', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_BOOK)
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
            return generate_failure_response(f'{field} parameter is required')

    book_id = clean_string(book_data['id']).lower()

    if not is_valid_book_id(book_id):
        return generate_failure_response('Invalid book ID format')

    new_book_data = acquire_book_fields(book_data)

    # Insert the new book into the database
    try:
        upsert_book(new_book_data['id'], new_book_data['name'], new_book_data['processor'], new_book_data['active'],
                    new_book_data['info_url'], new_book_data['rss_url'], new_book_data['extra_url'],
                    new_book_data['start_chapter'], new_book_data['skip'], new_book_data['rating'],
                    new_book_data['tags'], new_book_data['style'], db_session=db.session)

    except Exception as e:
        db.session.rollback()
        return generate_failure_response(f'Error inserting new book: {str(e)}')

    return generate_success_response('Book added successfully')


@volume_blueprint.route('/update', methods=['POST'])
@feature_required(volume_blueprint, MANAGE_BOOK)
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
            return generate_failure_response(f'{field} parameter is required')

    book_id = clean_string(book_data['id'])

    existing_book = find_book_by_id(book_id)

    if existing_book is None:
        return generate_failure_response(f'Book with ID {book_id} does not exist', 404)

    updated_book = acquire_book_fields(book_data)

    # Update the existing book in the database
    try:
        upsert_book(updated_book['id'], updated_book['name'], updated_book['processor'], updated_book['active'],
                    updated_book['info_url'], updated_book['start_chapter'], updated_book['rss_url'],
                    updated_book['extra_url'], updated_book['skip'], updated_book['rating'], updated_book['tags'],
                    updated_book['style'], db_session=db.session)

    except Exception as e:
        db.session.rollback()
        return generate_failure_response(f'Error updating book: {str(e)}')

    return generate_success_response('Book updated successfully')
