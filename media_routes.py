import logging
import mimetypes
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image
from flask import Blueprint, request, current_app, make_response, send_from_directory, Response, send_file, \
    stream_with_context, after_this_request
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from auth_utils import feature_required, feature_required_with_cookie, get_user_features, get_user_group_id, get_uid, \
    feature_required_silent
from common_utils import generate_success_response, generate_failure_response
from constants import PROPERTY_SERVER_MEDIA_READY, COMMON_MEDIA_RATINGS, PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER, \
    PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER, APP_KEY_SLC, MEDIA_FOLDER_KEY_PURPOSE_DEFAULT
from date_utils import convert_date_to_yyyymmdd, convert_datetime_to_yyyymmdd
from db import db, MediaFolder, MediaFile, MediaFolderTag
from feature_flags import VIEW_MEDIA, MANAGE_MEDIA, MEDIA_PLUGINS, MANAGE_APP
from file_utils import is_valid_mime_type
from media_queries import find_folder_by_id, find_root_folders, find_folders_in_folder, find_files_in_folder, \
    insert_folder, update_folder, find_file_by_id, update_file, count_folders_in_folder, count_root_folders, \
    count_files_in_folder, insert_file, upsert_progress, find_progress_entries, get_all_tags, get_tag_row, \
    find_media_folder_key_values, find_media_folder_key_value, add_media_folder_key_value, \
    update_media_folder_key_value, remove_media_folder_key_value
from media_utils import calculate_offset_limit, parse_range_header, get_data_for_mediafile, get_media_max_rating, \
    get_folder_group_checker, get_folder_rating_checker, user_can_see_rating, read_file_chunk
from messages import msg_file_migrated, msg_access_denied_content_rating, msg_action_cancelled_wrong, msg_action_failed, \
    msg_operation_complete, msg_file_moved, msg_file_deleted, msg_file_updated, msg_missing_parameter, \
    msg_folder_created, msg_invalid_parameter, msg_folder_updated, msg_action_cancelled_folder_not_empty, \
    msg_folder_deleted, msg_folder_moved, msg_action_failed_missing
from number_utils import is_integer, is_boolean, parse_boolean
from short_lived_cache import ShortLivedCache
from tag_utils import DCBitScanner128, calculate_tag_number, bits_csv_to_int
from text_utils import clean_string, is_not_blank, is_blank, is_guid, safe_filename
from user_queries import get_all_groups, get_group_by_id

media_blueprint = Blueprint('media', __name__)


# Media REST Resources

@media_blueprint.route('/list', methods=['POST'])
@feature_required(media_blueprint, VIEW_MEDIA)
def list_media(user_details: dict) -> tuple:
    """
    Retrieve a list of folder, files and information from the Media service.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the list of folder, files, info, message and status code.
    """
    if not current_app.config[PROPERTY_SERVER_MEDIA_READY]:
        return generate_failure_response(
            'This feature is not ready.  Please configure the app properties and restart the server.')

    folder_id = clean_string(request.form.get('folder_id'))

    offset = clean_string(request.form.get('offset'))
    limit = clean_string(request.form.get('limit'))
    requested_rating_limit = clean_string(request.form.get('rating'))
    sort = clean_string(request.form.get('sort'))
    filter_text = clean_string(request.form.get('filter_text'))
    filter_required_tags = bits_csv_to_int(clean_string(request.form.get('required_tags')))
    filter_hidden_tags = bits_csv_to_int(clean_string(request.form.get('hidden_tags')))

    folder_group_checker = get_folder_group_checker(user_details)
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

    if is_not_blank(sort):
        if sort == 'AZ':
            folder_sort = MediaFolder.name
            file_sort = MediaFile.filename
            sort_descending = False
        elif sort == 'ZA':
            folder_sort = MediaFolder.name
            file_sort = MediaFile.filename
            sort_descending = True
        elif sort == 'DA':
            folder_sort = MediaFolder.last_date
            file_sort = MediaFile.created
            sort_descending = False
        elif sort == 'DD':
            folder_sort = MediaFolder.last_date
            file_sort = MediaFile.created
            sort_descending = True
        elif sort == 'FA':
            folder_sort = MediaFolder.name
            file_sort = MediaFile.filesize
            sort_descending = False
        elif sort == 'FD':
            folder_sort = MediaFolder.name
            file_sort = MediaFile.filesize
            sort_descending = True
        else:
            folder_sort = MediaFolder.name
            file_sort = MediaFile.filename
            sort_descending = False
    else:
        folder_sort = MediaFolder.name
        file_sort = MediaFile.filename
        sort_descending = False

    current_info = {}
    folder_data = []
    file_data = []
    max_rating = get_media_max_rating(user_details)
    max_rating_checker = get_folder_rating_checker(user_details)

    if requested_rating_limit > max_rating:
        return generate_failure_response('User has requested a rating limit they are not allowed to access!',
                                         messages=[msg_access_denied_content_rating()])

    if is_not_blank(folder_id):
        # Make sure this exists, and you can see it
        current_folder = find_folder_by_id(folder_id)
        if current_folder is None:
            return generate_failure_response('Folder not found', 404, messages=[msg_action_cancelled_wrong()])

        if not max_rating_checker(current_folder):
            return generate_failure_response('User is not allowed to view content out of their rating zone',
                                             messages=[msg_access_denied_content_rating()])

        # App Admins see everything
        if not folder_group_checker(current_folder):
            return generate_failure_response(
                'User is not allowed to see a folder that is owned by another group',
                messages=[msg_access_denied_content_rating()])

        total_folders = count_folders_in_folder(folder_id, filter_text, requested_rating_limit,
                                                required_tags=filter_required_tags, hidden_tags=filter_hidden_tags,
                                                db_session=None)
        total_files = count_files_in_folder(folder_id, filter_text, None)
        total_items = total_folders + total_files

        query_stats = calculate_offset_limit(offset, limit, total_folders, total_files)

        if query_stats['folders_needed']:
            folder_rows = find_folders_in_folder(folder_id, filter_text, requested_rating_limit,
                                                 query_stats['folder_offset'], query_stats['folder_limit'], folder_sort,
                                                 sort_descending, required_tags=filter_required_tags,
                                                 hidden_tags=filter_hidden_tags, db_session=None)
        else:
            folder_rows = []

        if query_stats['files_needed']:
            file_rows = find_files_in_folder(folder_id, filter_text, query_stats['file_offset'],
                                             query_stats['file_limit'], file_sort, sort_descending, None, user_uid)
        else:
            file_rows = []

        # Setup the folder
        current_info['id'] = clean_string(current_folder.id)
        current_info['name'] = clean_string(current_folder.name)
        current_info['info_url'] = clean_string(current_folder.info_url)
        current_info['rating'] = current_folder.rating
        current_info['created'] = convert_date_to_yyyymmdd(current_folder.created)
        current_info['preview'] = current_folder.preview
        current_info['active'] = current_folder.active
        current_info['parent'] = clean_string(current_folder.parent_id)

    else:
        folder_rows = find_root_folders(filter_text, requested_rating_limit, offset, limit, folder_sort,
                                        sort_descending, required_tags=filter_required_tags,
                                        hidden_tags=filter_hidden_tags, db_session=None)
        total_items = count_root_folders(filter_text, requested_rating_limit, required_tags=filter_required_tags,
                                         hidden_tags=filter_hidden_tags, db_session=None)
        file_rows = []
        current_info['id'] = ''
        current_info['name'] = 'ROOT'
        current_info['info_url'] = ''
        current_info['rating'] = 0
        current_info['created'] = '20050101'
        current_info['preview'] = False
        current_info['active'] = False
        current_info['parent'] = ''

    tag_scanner = DCBitScanner128()

    for row in folder_rows:
        # Always ensure they can see everything returned, just in case
        if max_rating_checker(row) and folder_group_checker(row):
            folder_data.append(
                {"id": row.id,
                 "name": row.name,
                 "rating": row.rating,
                 "preview": row.preview,
                 "active": row.active,
                 'info_url': clean_string(row.info_url),
                 "created": convert_datetime_to_yyyymmdd(row.created),
                 "updated": convert_date_to_yyyymmdd(row.last_date),
                 "fast_tags": tag_scanner.positions(int(row.folder_tag_mask) if row.folder_tag_mask else 0)
                 })

    for row in file_rows:
        the_time = convert_datetime_to_yyyymmdd(row.created)

        user_progress = next(
            (progress for progress in row.progress_records if progress.user_id == user_uid),
            None
        )

        if user_progress is None:
            progress = '0'
        else:
            progress = f'{user_progress.progress:.5f}'

        file_data.append(
            {"id": row.id, "name": row.filename, "mime_type": row.mime_type, "preview": row.preview,
             "filesize": row.filesize, "archive": row.archive, "progress": progress,
             "created": the_time, "updated": the_time})

    return generate_success_response('', {"info": current_info, "paging": {"total": total_items, "offset": offset},
                                           "folders": folder_data, "files": file_data})


@media_blueprint.route('/list/by-date', methods=['POST'])
@feature_required(media_blueprint, VIEW_MEDIA)
def list_media_for_date(user_details: dict) -> tuple:
    """
    Retrieve a list of files created within a date range from the Media service.

    Args:
        user_details (dict): Details of the authenticated user.

    Returns:
        tuple: JSON response with the list of files, info, paging, message and status code.
    """
    if not current_app.config[PROPERTY_SERVER_MEDIA_READY]:
        return generate_failure_response(
            'This feature is not ready.  Please configure the app properties and restart the server.')

    start_date_str = clean_string(request.form.get('start_date'))
    end_date_str = clean_string(request.form.get('end_date'))

    offset = clean_string(request.form.get('offset'))
    limit = clean_string(request.form.get('limit'))
    requested_rating_limit = clean_string(request.form.get('rating'))
    sort = clean_string(request.form.get('sort'))

    if is_blank(start_date_str) or is_blank(end_date_str):
        return generate_failure_response('start_date and end_date parameters are required',
                                          messages=[msg_missing_parameter('start_date'), msg_missing_parameter('end_date')])

    if not (len(start_date_str) == 8 and len(end_date_str) == 8):
        return generate_failure_response('Dates must be in YYYYMMDD format',
                                          messages=[msg_invalid_parameter('start_date'), msg_invalid_parameter('end_date')])

    for date_str, param_name in [(start_date_str, 'start_date'), (end_date_str, 'end_date')]:
        try:
            datetime.strptime(date_str, '%Y%m%d')
        except ValueError:
            return generate_failure_response(f'{param_name} is not a valid date',
                                              messages=[msg_invalid_parameter(param_name)])

    start_date = datetime.strptime(start_date_str, '%Y%m%d').date()
    end_date = datetime.strptime(end_date_str, '%Y%m%d').date()

    if start_date > end_date:
        return generate_failure_response('start_date must be before or equal to end_date',
                                          messages=[msg_invalid_parameter('start_date')])

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

    if is_not_blank(sort):
        sort_descending = False
        if sort == 'ZA' or sort == 'DD' or sort == 'FD':
            sort_descending = True

    max_rating_checker = get_folder_rating_checker(user_details)
    folder_group_checker = get_folder_group_checker(user_details)
    user_uid = get_uid(user_details)

    if requested_rating_limit > 200:
        return generate_failure_response('User has requested a rating limit they are not allowed to access!',
                                          messages=[msg_access_denied_content_rating()])

    # Build folder cache: collect all visible folders (root + descendants) via a single query
    from sqlalchemy.orm import joinedload

    all_visible_folders = db.session.query(MediaFolder).all()

    cache = {}
    for f in all_visible_folders:
        if max_rating_checker(f) and folder_group_checker(f):
            cache[f.id] = f

    total_items = 0
    file_data = []
    tag_scanner = DCBitScanner128()

    if cache:
        from datetime import time as dt_time
        query_builder = db.session.query(MediaFile).join(MediaFolder).filter(
            MediaFolder.id.in_(list(cache.keys())),
            MediaFile.created >= datetime.combine(start_date, dt_time.min),
            MediaFile.created < datetime.combine(end_date + timedelta(days=1), dt_time.min)
        ).options(joinedload(MediaFile.progress_records))

        # Use column references for order_by instead of lambdas
        if sort == 'FA':
            query_builder = query_builder.order_by(MediaFile.filesize.asc()) if not sort_descending else query_builder.order_by(MediaFile.filesize.desc())
        elif sort == 'FD':
            query_builder = query_builder.order_by(MediaFile.filesize.desc()) if sort_descending else query_builder.order_by(MediaFile.filesize.asc())
        elif sort in ('DA', 'DD'):
            query_builder = query_builder.order_by(MediaFile.created.asc()) if not sort_descending else query_builder.order_by(MediaFile.created.desc())
        elif sort == 'ZA':
            query_builder = query_builder.order_by(MediaFile.filename.asc()) if not sort_descending else query_builder.order_by(MediaFile.filename.desc())
        elif sort == 'AZ':
            query_builder = query_builder.order_by(MediaFile.filename.asc()) if not sort_descending else query_builder.order_by(MediaFile.filename.desc())
        else:
            query_builder = query_builder.order_by(MediaFile.created.asc())

        all_file_rows = query_builder.all()

        for file_row in all_file_rows:
            parent_folder = cache.get(file_row.folder_id)
            if not parent_folder:
                continue

            if parent_folder.rating > requested_rating_limit:
                continue

            total_items += 1

            user_progress = next(
                (progress for progress in file_row.progress_records if progress.user_id == user_uid),
                None
            )

            if user_progress is None:
                progress = '0'
            else:
                progress = f'{user_progress.progress:.5f}'

            file_data.append(
                {"id": file_row.id, "name": file_row.filename, "mime_type": file_row.mime_type,
                 "preview": file_row.preview, "filesize": file_row.filesize, "archive": file_row.archive,
                 "progress": progress, "created": convert_datetime_to_yyyymmdd(file_row.created),
                 "updated": convert_datetime_to_yyyymmdd(file_row.created),
                 "folder_name": parent_folder.name, "folder_id": parent_folder.id,
                 "fast_tags": tag_scanner.positions(int(parent_folder.folder_tag_mask) if parent_folder.folder_tag_mask else 0),
                 "rating": parent_folder.rating})

    start_idx = offset
    end_idx = min(start_idx + limit, total_items)
    if start_idx >= total_items:
        file_data = []
    else:
        file_data = file_data[start_idx:end_idx]

    return generate_success_response('', {"info": {}, "paging": {"total": total_items, "offset": offset},
                                           "folders": [], "files": file_data})


# Folder Management

@media_blueprint.route('/folder', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def get_media_folder(user_details: dict) -> tuple:
    """
    Get the details of a folder
    :param user_details:
    :return:
    """
    folder_id = clean_string(request.form.get('folder_id'))

    if is_blank(folder_id):
        return generate_failure_response('folder_id parameter is required',
                                         messages=[msg_missing_parameter('folder_id')])

    folder_group_checker = get_folder_group_checker(user_details)
    folder_rating_checker = get_folder_rating_checker(user_details)

    folder_row = find_folder_by_id(folder_id)

    if folder_row is None:
        return generate_failure_response('Could not find requested folder', messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checker(folder_row.rating):
        return generate_failure_response('User is not allowed to see a folder with a higher rating limit',
                                         messages=[msg_access_denied_content_rating()])

    # App Admins see everything
    if not folder_group_checker(folder_row):
        return generate_failure_response('User is not allowed to see a folder that is owned by another group',
                                         messages=[msg_access_denied_content_rating()])

    parent_rating = 0
    parent_group = None

    if folder_row.parent:
        parent = folder_row.parent
        parent_rating = parent.rating
        parent_group = parent.owning_group_id

    tag_scanner = DCBitScanner128()

    return generate_success_response('',
                                     {"info": {"id": folder_row.id, "name": folder_row.name,
                                               "rating": folder_row.rating, "parent_rating": parent_rating,
                                               "parent_group": parent_group,
                                               "preview": folder_row.preview, "active": folder_row.active,
                                               "created": convert_datetime_to_yyyymmdd(folder_row.created),
                                               "updated": convert_datetime_to_yyyymmdd(folder_row.last_date),
                                               "parent_id": clean_string(folder_row.parent_id),
                                               "info_url": clean_string(folder_row.info_url),
                                               "group_id": folder_row.owning_group_id,
                                               "fast_tags": tag_scanner.positions(
                                                   int(folder_row.folder_tag_mask) if folder_row.folder_tag_mask else 0),
                                               "tags": clean_string(folder_row.tags)}})


@media_blueprint.route('/folder/post', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def post_media_folder(user_details: dict) -> tuple:
    """
    Create a media folder
    :param user_details:
    :return:
    """
    parent_id = clean_string(request.form.get('parent_id'))
    name = clean_string(request.form.get('name'))

    if is_blank(name):
        return generate_failure_response('name parameter is required', messages=[msg_missing_parameter('name')])

    rating = clean_string(request.form.get('rating'))

    if not is_integer(rating):
        return generate_failure_response('rating parameter is not an integer',
                                         messages=[msg_missing_parameter('rating')])

    fast_tags = clean_string(request.form.get('fast_tags'))
    tag_number = calculate_tag_number(fast_tags)

    rating = int(rating)

    if rating not in COMMON_MEDIA_RATINGS:
        return generate_failure_response('rating parameter is not valid', messages=[msg_action_cancelled_wrong()])

    folder_rating_checker = get_folder_rating_checker(user_details)
    folder_group_checker = get_folder_group_checker(user_details)

    if not user_can_see_rating(user_details, rating):
        return generate_failure_response('User is not allowed to define a folder that has a higher rating limit',
                                         messages=[msg_access_denied_content_rating()])

    info_url = clean_string(request.form.get('info_url'))

    active = clean_string(request.form.get('active'))

    if not is_boolean(active):
        return generate_failure_response('active parameter is invalid', messages=[msg_action_cancelled_wrong()])
    active = parse_boolean(active)

    group_id = clean_string(request.form.get('group_id'))

    if is_not_blank(group_id) and is_integer(group_id):
        group_id = int(group_id)
        group = get_group_by_id(group_id)
        if group is None:
            return generate_failure_response('Unknown group', 400, messages=[msg_action_cancelled_wrong()])
    else:
        group_id = None

    tags = clean_string(request.form.get('tags'))

    if is_not_blank(parent_id):
        # Make sure the parent exists
        parent_row = find_folder_by_id(parent_id)
        if parent_row is None:
            return generate_failure_response('Could not find parent folder', messages=[msg_action_cancelled_wrong()])

        # Do you even haver access to see the lower folder
        if not folder_rating_checker(parent_row):
            return generate_failure_response('User does not have access to parent folder',
                                             messages=[msg_access_denied_content_rating()])

        if rating < parent_row.rating:
            return generate_failure_response('Sub-folders must have a rating >= to their parent folder',
                                             messages=[msg_access_denied_content_rating()])

        if not folder_group_checker(parent_row):
            return generate_failure_response('User does not have access to parent folder via parent group',
                                             messages=[msg_access_denied_content_rating()])

        if parent_row.owning_group_id is not None and (parent_row.owning_group_id != group_id or group_id is None):
            return generate_failure_response('Sub-folders must have the same group security as a parent with security',
                                             messages=[msg_access_denied_content_rating()])

    new_folder = insert_folder(parent_id, name, rating, info_url, tag_number, tags, active, group_id, db.session)

    return generate_success_response('Folder inserted', {"folder_id": new_folder.id}, messages=[msg_folder_created()])


@media_blueprint.route('/folder/put', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def put_media_folder(user_details: dict) -> tuple:
    """
    Update a media folder
    :param user_details:
    :return:
    """
    max_rating = get_media_max_rating(user_details)

    folder_id = clean_string(request.form.get('folder_id'))
    name = clean_string(request.form.get('name'))
    folder_rating_checker = get_folder_rating_checker(user_details)
    folder_group_checker = get_folder_group_checker(user_details)

    # Name checks
    if is_blank(name):
        return generate_failure_response('name parameter is required', messages=[msg_missing_parameter('name')])

    # Rating checks
    rating = clean_string(request.form.get('rating'))
    if not is_integer(rating):
        return generate_failure_response('rating parameter is not an integer',
                                         messages=[msg_invalid_parameter('rating')])
    rating = int(rating)
    if rating not in COMMON_MEDIA_RATINGS:
        return generate_failure_response('rating parameter is not valid', messages=[msg_invalid_parameter('rating')])
    if rating > max_rating:
        return generate_failure_response('User is not allowed to define a folder that has a higher rating limit',
                                         messages=[msg_access_denied_content_rating()])

    fast_tags = clean_string(request.form.get('fast_tags'))
    tag_number = calculate_tag_number(fast_tags)

    info_url = clean_string(request.form.get('info_url'))

    active = clean_string(request.form.get('active'))
    if not is_boolean(active):
        return generate_failure_response('active parameter is invalid', messages=[msg_invalid_parameter('active')])
    active = parse_boolean(active)

    group_id = clean_string(request.form.get('group_id'))

    if is_not_blank(group_id) and is_integer(group_id):
        group_id = int(group_id)
        group = get_group_by_id(group_id)
        if group is None:
            return generate_failure_response('Unknown group', 400, messages=[msg_invalid_parameter('group_id')])
    else:
        group_id = None

    tags = clean_string(request.form.get('tags'))

    # Make sure the folder exists
    existing_row = find_folder_by_id(folder_id)
    if existing_row is None:
        return generate_failure_response('Could not find existing folder to edit',
                                         messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checker(existing_row):
        return generate_failure_response(
            'You are not allowed to edit this folder, since its rating is above your limit',
            messages=[msg_access_denied_content_rating()])

    if not folder_group_checker(existing_row):
        return generate_failure_response(
            'You are not allowed to edit this folder, since you do not have access via group security',
            messages=[msg_access_denied_content_rating()])

    parent_row = existing_row.parent

    if parent_row is not None:
        # Do you even haver access to see the lower folder
        if not folder_rating_checker(parent_row):
            return generate_failure_response('User does not have access to parent folder',
                                             messages=[msg_access_denied_content_rating()])

        if rating < parent_row.rating:
            return generate_failure_response(
                'Sub-folders must have a rating >= to their parent folder',
                messages=[msg_access_denied_content_rating()])

        if not folder_group_checker(parent_row):
            return generate_failure_response(
                'Parent does not have access to parent folder via group security',
                messages=[msg_access_denied_content_rating()])

        if parent_row.owning_group_id is not None and (parent_row.owning_group_id != group_id or group_id is None):
            return generate_failure_response('Sub-folders must have the same group security as a parent with security',
                                             messages=[msg_access_denied_content_rating()])

    if update_folder(folder_id, name, rating, info_url, tags, tag_number, active, group_id, db.session):
        return generate_success_response('Folder update', messages=[msg_folder_updated()])
    else:
        return generate_failure_response('Failed to update folder', messages=[msg_action_failed()])


@media_blueprint.route('/folder/delete', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def delete_media_folder(user_details: dict) -> tuple:
    """
    Delete a media folder
    :param user_details:
    :return:
    """
    folder_id = clean_string(request.form.get('folder_id'))
    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    # Name checks
    if is_blank(folder_id):
        return generate_failure_response('folder_id parameter is required',
                                         messages=[msg_missing_parameter('folder_id')])

    # Make sure the folder exists
    existing_row = find_folder_by_id(folder_id)
    if existing_row is None:
        return generate_failure_response('Could not find existing folder', messages=[msg_action_cancelled_wrong()])

    # Make sure you have access to even do this
    if not folder_rating_checks(existing_row) or not folder_group_checks(existing_row):
        return generate_failure_response('User should not have access to this folder',
                                         messages=[msg_access_denied_content_rating()])

    if len(find_files_in_folder(folder_id)) > 0:
        return generate_failure_response('Child files still exist', messages=[msg_action_cancelled_folder_not_empty()])

    if len(find_folders_in_folder(folder_id)) > 0:
        return generate_failure_response('Child folders still exist',
                                         messages=[msg_action_cancelled_folder_not_empty()])

    if existing_row.preview:
        primary_folder = current_app.config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER]
        target_file = os.path.join(primary_folder, existing_row.id + '_prev.webp')
        if os.path.exists(target_file) and os.path.isfile(target_file):
            os.unlink(target_file)

    try:
        db.session.delete(existing_row)
        db.session.commit()
        return generate_success_response('Folder deleted', messages=[msg_folder_deleted()])
    except Exception as e:
        logging.exception(e)
        return generate_failure_response('Failed to delete folder', messages=[msg_action_failed()])


@media_blueprint.route('/folder/move', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def move_media_folder(user_details: dict) -> tuple:
    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    source_folder_id = clean_string(request.form.get('source_id'))
    dest_folder_id = clean_string(request.form.get('folder_id'))

    source_row = find_folder_by_id(source_folder_id)

    if source_row is None:
        return generate_failure_response('Could not find requested folder', messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checks(source_row):
        return generate_failure_response('User is not allowed to move a folder in a folder with a higher rating limit',
                                         messages=[msg_access_denied_content_rating()])

    if not folder_group_checks(source_row):
        return generate_failure_response(
            'User is not allowed to move a folder in a folder with a different security group',
            messages=[msg_access_denied_content_rating()])

    if is_not_blank(dest_folder_id):
        # Destination Folder Check

        target_folder_row = find_folder_by_id(dest_folder_id)

        if target_folder_row is None:
            return generate_failure_response('Destination folder does not exist',
                                             messages=[msg_action_cancelled_wrong()])

        if not folder_rating_checks(target_folder_row):
            return generate_failure_response(
                'User is not allowed to move a file into a folder with a higher rating limit',
                messages=[msg_access_denied_content_rating()])

        if not folder_group_checks(target_folder_row):
            return generate_failure_response(
                'User is not allowed to move a file into a folder with a different security group',
                messages=[msg_access_denied_content_rating()])

        # Make sure it's not the same folder

        if target_folder_row.id == source_row.id:
            return generate_failure_response(
                'Source folder should not equal dest folder', messages=[msg_action_cancelled_wrong()])

        if target_folder_row.id == source_row.parent_id:
            return generate_failure_response(
                'Source folder should not equal dest folder', messages=[msg_action_cancelled_wrong()])

        # Check the limit

        if target_folder_row.rating > source_row.rating:
            return generate_failure_response(
                'Target folder has a higher rating over the source', messages=[msg_access_denied_content_rating()])

        target_folder_value = target_folder_row.id
    else:
        # Drop a folder to root
        target_folder_value = None

    # Update the pointer
    source_row.parent_id = target_folder_value

    db.session.commit()

    return generate_success_response('Folder Moved', messages=[msg_folder_moved()])


@media_blueprint.route('/folder/activate', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def activate_folder(user_details: dict) -> tuple:
    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    source_folder_id = clean_string(request.form.get('folder_id'))
    source_row = find_folder_by_id(source_folder_id)

    if source_row is None:
        return generate_failure_response('Could not find requested folder', messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checks(source_row):
        return generate_failure_response(
            'User is not allowed to activate a folder in a folder with a higher rating limit',
            messages=[msg_access_denied_content_rating()])

    if not folder_group_checks(source_row):
        return generate_failure_response(
            'User is not allowed to activate a folder in a folder with a different security group',
            messages=[msg_access_denied_content_rating()])

    source_row.active = True

    db.session.commit()

    return generate_success_response('Folder Activated', messages=[msg_folder_updated()])


@media_blueprint.route('/folder/inactivate', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def inactivate_folder(user_details: dict) -> tuple:
    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    source_folder_id = clean_string(request.form.get('folder_id'))
    source_row = find_folder_by_id(source_folder_id)

    if source_row is None:
        return generate_failure_response('Could not find requested folder', messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checks(source_row):
        return generate_failure_response(
            'User is not allowed to inactivate a folder in a folder with a higher rating limit',
            messages=[msg_access_denied_content_rating()])

    if not folder_group_checks(source_row):
        return generate_failure_response(
            'User is not allowed to inactivate a folder in a folder with a different security group',
            messages=[msg_access_denied_content_rating()])

    source_row.active = False

    db.session.commit()

    return generate_success_response('Folder Inactivated', messages=[msg_folder_updated()])


# File Management

@media_blueprint.route('/file', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def get_media_file(user_details: dict) -> tuple:
    file_id = clean_string(request.form.get('file_id'))

    if is_blank(file_id):
        return generate_failure_response('file_id parameter is required', messages=[msg_missing_parameter('file_id')])

    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    file_row = find_file_by_id(file_id)

    if file_row is None:
        return generate_failure_response('Could not find requested file', messages=[msg_action_cancelled_wrong()])

    folder_row = file_row.mediafolder

    if folder_row is None:
        return generate_failure_response('File need to be placed inside a non-root folder',
                                         messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checks(folder_row) or not folder_group_checks(folder_row):
        return generate_failure_response('User is not allowed to see containing folder',
                                         messages=[msg_access_denied_content_rating()])

    return generate_success_response('',
                                     {"file": {"id": file_row.id, "filename": file_row.filename,
                                               "mime_type": file_row.mime_type,
                                               "archive": file_row.archive, "preview": file_row.preview,
                                               "filesize": file_row.filesize, "active": folder_row.active,
                                               "created": convert_datetime_to_yyyymmdd(file_row.created)}})


@media_blueprint.route('/file/put', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def put_media_file(user_details: dict) -> tuple:
    file_id = clean_string(request.form.get('file_id'))
    filename = clean_string(request.form.get('filename'))
    mime_type = clean_string(request.form.get('mime_type'))

    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    # Name checks
    if is_blank(filename):
        return generate_failure_response('filename parameter is required', messages=[msg_missing_parameter('filename')])

    # Name checks
    if is_blank(mime_type):
        return generate_failure_response('mime_type parameter is required',
                                         messages=[msg_missing_parameter('mime_type')])

    # Make sure it's a known file type
    if not is_valid_mime_type(mime_type):
        return generate_failure_response('invalid mime_type value', messages=[msg_invalid_parameter('mime_type')])

    # Find the row
    file_row = find_file_by_id(file_id)

    if file_row is None:
        return generate_failure_response('Could not find file to update', messages=[msg_action_cancelled_wrong()])

    # Find the folder
    folder_row = file_row.mediafolder

    if folder_row is None:
        return generate_failure_response('File does not have a parent', messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checks(folder_row) or not folder_group_checks(folder_row):
        return generate_failure_response('User does not have access to containing folder',
                                         messages=[msg_access_denied_content_rating()])

    if update_file(file_id, filename, mime_type, db.session):
        return generate_success_response('File update', messages=[msg_file_updated()])
    else:
        return generate_failure_response('Failed to update file', messages=[msg_action_failed()])


@media_blueprint.route('/file/progress', methods=['POST'])
@feature_required(media_blueprint, VIEW_MEDIA)
def put_media_progress(user_details: dict) -> tuple:
    file_id = clean_string(request.form.get('file_id'))
    progress = clean_string(request.form.get('progress'))

    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    # Name checks
    if is_blank(progress):
        return generate_failure_response('progress parameter is required', messages=[msg_missing_parameter('progress')])

    # Find the row
    file_row = find_file_by_id(file_id)

    if file_row is None:
        return generate_failure_response('Could not find file to update', messages=[msg_action_cancelled_wrong()])

    # Find the folder
    folder_row = file_row.mediafolder

    if folder_row is None:
        return generate_failure_response('File does not have a parent', messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checks(folder_row) or not folder_group_checks(folder_row):
        return generate_failure_response('User does not have access to containing folder',
                                         messages=[msg_access_denied_content_rating()])

    try:
        progress = float(progress)
    except Exception as e:
        logging.exception(e)
        return generate_failure_response('Failed to parse progress value', messages=[msg_action_failed()])

    upsert_progress(get_uid(user_details), file_id, progress, datetime.now(timezone.utc))

    return generate_success_response('')


@media_blueprint.route('/file/migrate', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def migrate_media_file(user_details: dict) -> tuple:
    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    file_id = clean_string(request.form.get('file_id'))
    force_archive = clean_string(request.form.get('force_archive'))

    if is_blank(force_archive):
        force_archive = False
    elif is_boolean(force_archive):
        force_archive = parse_boolean(force_archive)
    else:
        force_archive = False

    file_row = find_file_by_id(file_id)

    if file_row is None:
        return generate_failure_response('Could not find requested file', messages=[msg_action_cancelled_wrong()])

    if force_archive and file_row.archive:
        return generate_failure_response('File is already archived', messages=[msg_action_cancelled_wrong()])

    folder_row = file_row.mediafolder

    if folder_row is None:
        return generate_failure_response('File does not have a parent', messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checks(folder_row):
        return generate_failure_response('User is not allowed to edit a file in a folder with a higher rating limit',
                                         messages=[msg_access_denied_content_rating()])

    if not folder_group_checks(folder_row):
        return generate_failure_response(
            'User is not allowed to edit a file in a folder owned by another security group',
            messages=[msg_access_denied_content_rating()])

    primary_folder = current_app.config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER]
    archive_folder = current_app.config[PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER]

    # Get the Paths
    old_file = get_data_for_mediafile(file_row, primary_folder, archive_folder)
    # Flip the path
    file_row.archive = not file_row.archive
    new_file = get_data_for_mediafile(file_row, primary_folder, archive_folder)

    if os.path.exists(old_file):
        try:
            shutil.copyfile(old_file, new_file)
            if os.path.exists(new_file):
                db.session.commit()
                os.unlink(old_file)
                return generate_success_response('', messages=[msg_file_migrated()])
        except Exception as e:
            logging.exception(e)

    return generate_failure_response('Failed to migrate file!', messages=[msg_action_failed()])


@media_blueprint.route('/file/delete', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def delete_media_file(user_details: dict) -> tuple:
    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    file_id = clean_string(request.form.get('file_id'))

    file_row = find_file_by_id(file_id)

    if file_row is None:
        return generate_failure_response('Could not find requested file', messages=[msg_action_cancelled_wrong()])

    folder_row = file_row.mediafolder

    if folder_row is None:
        return generate_failure_response('File does not have a parent', messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checks(folder_row):
        return generate_failure_response('User is not allowed to delete a file in a folder with a higher rating limit',
                                         messages=[msg_access_denied_content_rating()])

    if not folder_group_checks(folder_row):
        return generate_failure_response(
            'User is not allowed to delete a file in a folder with a different security group',
            messages=[msg_access_denied_content_rating()])

    primary_folder = current_app.config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER]
    archive_folder = current_app.config[PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER]

    if file_row.preview:
        preview_file_name = os.path.join(primary_folder, file_row.id + '_prev.webp')
        if os.path.exists(preview_file_name) and os.path.isfile(preview_file_name):
            os.unlink(preview_file_name)
        else:
            logging.warning(f'Could not erase preview for for {file_row.id}')

    if file_row.archive:
        data_file_name = os.path.join(archive_folder, file_row.id + '.dat')
    else:
        data_file_name = os.path.join(primary_folder, file_row.id + '.dat')

    if os.path.exists(data_file_name) and os.path.isfile(data_file_name):
        os.unlink(data_file_name)

    db.session.delete(file_row)
    db.session.commit()

    return generate_success_response('File deleted', messages=[msg_file_deleted()])


@media_blueprint.route('/file/move', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def move_media_file(user_details: dict) -> tuple:
    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    file_id = clean_string(request.form.get('file_id'))
    dest_folder_id = clean_string(request.form.get('folder_id'))

    file_row = find_file_by_id(file_id)

    if file_row is None:
        return generate_failure_response('Could not find requested file', messages=[msg_action_cancelled_wrong()])

    # Source Folder Check

    folder_row = file_row.mediafolder

    if folder_row is None:
        return generate_failure_response('File needs to be inside of a folder', messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checks(folder_row):
        return generate_failure_response('User is not allowed to move a file in a folder with a higher rating limit',
                                         messages=[msg_access_denied_content_rating()])

    if not folder_group_checks(folder_row):
        return generate_failure_response(
            'User is not allowed to move a file in a folder with a different security group',
            messages=[msg_access_denied_content_rating()])

    # Destination Folder Check

    target_folder_row = find_folder_by_id(dest_folder_id)

    if target_folder_row is None:
        return generate_failure_response('Destination folder does not exist', messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checks(target_folder_row):
        return generate_failure_response('User is not allowed to move a file into a folder with a higher rating limit',
                                         messages=[msg_access_denied_content_rating()])

    if not folder_group_checks(target_folder_row):
        return generate_failure_response(
            'User is not allowed to move a file into a folder with a different security group',
            messages=[msg_access_denied_content_rating()])

    if target_folder_row.id == folder_row.id:
        return generate_failure_response(
            'Source folder should not equal dest folder', messages=[msg_action_cancelled_wrong()])

    # Update the pointer
    file_row.folder_id = target_folder_row.id

    db.session.commit()

    return generate_success_response('File Moved', messages=[msg_file_moved()])


# Upload random files

@media_blueprint.route('/folder/upload/file', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def upload_file(user_details):
    # Get the JSON file name from the query parameters
    folder_id = clean_string(request.form.get('folder_id'))
    uploaded_file = request.files['file']

    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    # If JSON file name is not provided, return an error message
    if is_blank(folder_id):
        return generate_failure_response('folder_id is required', messages=[msg_missing_parameter('folder_id')])

    # Check if the file is an image
    if uploaded_file.filename == '':
        return generate_failure_response('filename is required', messages=[msg_missing_parameter('filename')])

    # Make sure the folder exists
    existing_row = find_folder_by_id(folder_id)
    if existing_row is None:
        return generate_failure_response('Could not find folder', messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checks(existing_row) or not folder_group_checks(existing_row):
        return generate_failure_response('User does not have access to the target folder',
                                         messages=[msg_access_denied_content_rating()])

    new_file = insert_file(existing_row.id, uploaded_file.filename, uploaded_file.mimetype, False, False,
                           uploaded_file.content_length, datetime.now(timezone.utc), db.session)

    if new_file is None:
        return generate_failure_response(
            'Could not insert file', messages=[msg_action_cancelled_wrong()])

    primary_folder = current_app.config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER]
    target_file = os.path.join(primary_folder, new_file.id + '.dat')

    uploaded_file.save(target_file)

    new_file.filesize = Path(target_file).stat().st_size

    existing_row.last_date = datetime.now(timezone.utc).date()

    db.session.commit()

    return generate_success_response('File uploaded', messages=[msg_operation_complete()])

# Upload Note

@media_blueprint.route('/folder/upload/note', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def upload_note(user_details):
    """
    Upload a note as a text file. Accepts POST form data with folder_id (string) and note_text (string).
    Returns success response on upload, failure response if parameters are missing, folder not found, or user lacks access.
    """
    folder_id = clean_string(request.form.get('folder_id'))
    note_text = request.form.get('note_text', '')

    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    if is_blank(folder_id):
        return generate_failure_response('folder_id is required', messages=[msg_missing_parameter('folder_id')])

    if is_blank(note_text):
        return generate_failure_response('note_text is required', messages=[msg_missing_parameter('note_text')])

    existing_row = find_folder_by_id(folder_id)
    if existing_row is None:
        return generate_failure_response('Could not find folder', messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checks(existing_row) or not folder_group_checks(existing_row):
        return generate_failure_response('User does not have access to the target folder',
                                         messages=[msg_access_denied_content_rating()])

    now = datetime.now(timezone.utc)
    filename = f'note_{now.strftime("%Y%m%d")}_{now.strftime("%H%M%S")}.txt'

    new_file = insert_file(existing_row.id, filename, 'text/plain', False, False,
                           len(note_text.encode('utf-8')), datetime.now(timezone.utc), db.session)

    if new_file is None:
        return generate_failure_response(
            'Could not insert file', messages=[msg_action_cancelled_wrong()])

    primary_folder = current_app.config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER]
    target_file = os.path.join(primary_folder, new_file.id + '.dat')

    with open(target_file, 'w', encoding='utf-8') as f:
        f.write(note_text)

    new_file.filesize = Path(target_file).stat().st_size

    existing_row.last_date = datetime.now(timezone.utc).date()

    db.session.commit()

    return generate_success_response('Note uploaded', messages=[msg_operation_complete()])


# Getting / Setting Previews


@media_blueprint.route('/folder/upload/preview', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def upload_media_preview(user_details):
    # Get the JSON file name from the query parameters
    folder_id = clean_string(request.form.get('folder_id'))
    image_file = request.files['image']

    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    # If JSON file name is not provided, return an error message
    if is_blank(folder_id):
        return generate_failure_response('folder_id is required', messages=[msg_missing_parameter('folder_id')])

    # Check if the file is an image
    if image_file.filename == '':
        return generate_failure_response('image is required', messages=[msg_missing_parameter('image')])

    # Make sure the folder exists
    existing_row = find_folder_by_id(folder_id)
    if existing_row is None:
        return generate_failure_response('Could not find folder', messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checks(existing_row) or not folder_group_checks(existing_row):
        return generate_failure_response('User does not have access to the target folder',
                                         messages=[msg_access_denied_content_rating()])

    primary_folder = current_app.config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER]

    target_file = os.path.join(primary_folder, folder_id + '_prev.webp')

    try:
        image = Image.open(image_file)
        # Resize the image if needed
        max_size = (256, 256)
        image.thumbnail(max_size)
        image.save(target_file, 'WEBP')
    except Exception:
        return generate_failure_response('Preview was not a valid format', messages=[msg_action_failed()])

    existing_row.preview = True
    db.session.commit()

    return generate_success_response('Preview updated', messages=[msg_operation_complete()])


@media_blueprint.route('/item/preview/<folder_id>', methods=['GET'])
@feature_required_with_cookie(media_blueprint, VIEW_MEDIA)
def serve_media_thumbnail(user_details, folder_id):
    # Prevent path traversal attacks

    folder_id = secure_filename(folder_id)

    primary_folder = current_app.config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER]

    # Construct the file path
    target_file = os.path.join(primary_folder, folder_id + '_prev.webp')

    # Check if the file exists
    if os.path.exists(target_file) and os.path.isfile(target_file):
        # Create a response
        response = make_response(send_from_directory(os.path.dirname(target_file), os.path.basename(target_file)))

        # Set cache control headers
        expires_at = datetime.now() + timedelta(hours=5)
        response.headers['Cache-Control'] = 'public, max-age=18000'  # 5 hours cache
        response.headers['Expires'] = expires_at.strftime('%a, %d %b %Y %H:%M:%S GMT')

        return response
    else:

        # Create a response
        response = make_response(send_from_directory('.', '404.png'), 404)

        # Set cache control headers
        expires_at = datetime.now() + timedelta(minutes=5)
        response.headers['Cache-Control'] = 'public, max-age=300'  # 3 minute cache
        response.headers['Expires'] = expires_at.strftime('%a, %d %b %Y %H:%M:%S GMT')

        return response


# Getting actual Content

@media_blueprint.route('/download/<file_id>', methods=['GET', 'POST'])
@feature_required_with_cookie(media_blueprint, VIEW_MEDIA)
def download_media_file(user_details, file_id):
    """
    Download a file from the server
    :return: File contents
    """
    if not current_app.config[PROPERTY_SERVER_MEDIA_READY]:
        return generate_failure_response(
            'This feature is not ready.  Please configure the app properties and restart the server.')

    # Process Parameters
    file_id = clean_string(file_id)

    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    if not is_guid(file_id):
        return generate_failure_response('invalid file_id value', 404)

    file = find_file_by_id(file_id)

    if file is None:
        return generate_failure_response('file not found', 404)

    is_archive = file.archive
    filename = file.filename
    mimetype = file.mime_type

    containing_folder = file.mediafolder

    if containing_folder is None:
        return generate_failure_response('file error, missing parent', 400)

    if not folder_rating_checks(containing_folder) or not folder_group_checks(containing_folder):
        return generate_failure_response('User is not allowed to see this folder', 403)

    if is_archive:
        target_folder = current_app.config[PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER]
    else:
        target_folder = current_app.config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER]

    # If JSON file name is not provided, return an error message
    if is_blank(filename):
        return generate_failure_response('filename not provided')

    target_path = os.path.join(target_folder, file_id + '.dat')

    if target_path is None or not os.path.isfile(target_path):
        return generate_failure_response('requested file not found', 404)

    response = make_response(send_file(target_path, as_attachment=True, download_name=filename))

    # Apply a specific CSP for the file download to limit exposure
    strict_csp = (
        "default-src 'none'; "  # Block all external sources
        "script-src 'self'; "  # Allow scripts from the current domain only
        "style-src 'self'; "  # Allow styles only from the current domain
        "img-src 'self'; "  # Images only from the current domain
    )
    response.headers['Content-Security-Policy'] = strict_csp
    response.headers['Content-Type'] = mimetype

    return response


@media_blueprint.route('/download_batch/<file_ids>', methods=['GET', 'POST'])
@feature_required_with_cookie(media_blueprint, VIEW_MEDIA)
def download_multiple_files(user_details, file_ids):
    """
    Download multiple files as a zip archive with no compression.
    """
    if not current_app.config[PROPERTY_SERVER_MEDIA_READY]:
        return generate_failure_response(
            'This feature is not ready. Please configure the app properties and restart the server.')

    file_ids_param = clean_string(file_ids)
    file_ids = [clean_string(fid) for fid in file_ids_param.split(',') if is_guid(fid)]

    if not file_ids:
        return generate_failure_response('No valid file IDs provided.', 400)

    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    unique_filenames = {}
    files_to_zip = []

    result_file_name = ''

    for file_id in file_ids:
        file = find_file_by_id(file_id)
        if not file:
            continue

        folder = file.mediafolder
        if not folder or not folder_group_checks(folder) or not folder_rating_checks(folder):
            continue

        if result_file_name == '':
            result_file_name = safe_filename(folder.name) + '.zip'

        target_folder = current_app.config[
            PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER if file.archive else PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER
        ]
        file_path = os.path.join(target_folder, file_id + '.dat')
        if not os.path.isfile(file_path):
            continue

        mimetype = file.mime_type
        base_name = file.filename or file_id
        name, ext = os.path.splitext(base_name)

        count = 1

        if is_blank(ext):
            ext = mimetypes.guess_extension(mimetype)

        final_name = f"{base_name}{ext}"

        # Ensure filename is unique within zip
        while final_name in unique_filenames:
            final_name = f"{name}_{count}{ext}"
            count += 1

        unique_filenames[final_name] = True
        files_to_zip.append((file_path, final_name))

    if not files_to_zip:
        return generate_failure_response('No valid files found for download.', 404)

    temp_dir = tempfile.gettempdir()
    zip_filename = f"{uuid.uuid4()}.zip"
    zip_path = os.path.join(temp_dir, zip_filename)

    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_STORED) as zipf:
        for file_path, arc_name in files_to_zip:
            zipf.write(file_path, arcname=arc_name)

    @after_this_request
    def remove_file(response):
        try:
            os.remove(zip_path)
        except Exception:
            current_app.logger.exception("Failed to remove temporary zip file")
        return response

    return send_file(
        zip_path,
        as_attachment=True,
        download_name=result_file_name,
        mimetype='application/zip'
    )


@media_blueprint.route('/view', methods=['GET'])
@feature_required_with_cookie(media_blueprint, VIEW_MEDIA)
def view_media_file(user_details):
    """
    Download a file from the server
    :return: File contents
    """
    if not current_app.config[PROPERTY_SERVER_MEDIA_READY]:
        return generate_failure_response(
            'This feature is not ready.  Please configure the app properties and restart the server.')

    # Process Query Parameters
    file_id = clean_string(request.args.get('file_id'))

    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    if not is_guid(file_id):
        return generate_failure_response('invalid file_id value', 404)

    file = find_file_by_id(file_id)

    if file is None:
        return generate_failure_response('file not found', 404)

    is_archive = file.archive
    filename = file.filename
    mimetype = file.mime_type

    containing_folder = file.mediafolder

    if containing_folder is None:
        return generate_failure_response('file error, missing parent', 400)

    if not folder_rating_checks(containing_folder) or not folder_group_checks(containing_folder):
        return generate_failure_response('User is not allowed to see this folder', 403)

    if is_archive:
        target_folder = current_app.config[PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER]
    else:
        target_folder = current_app.config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER]

    target_path = os.path.join(target_folder, file_id + '.dat')

    if target_path is None or not os.path.isfile(target_path):
        return generate_failure_response('requested file not found', 404)

    response = make_response(send_file(target_path, as_attachment=False, download_name=filename))

    # Apply a specific CSP for the file download to limit exposure
    strict_csp = (
        "default-src 'none'; "  # Block all external sources
        "script-src 'self'; "  # Allow scripts from the current domain only
        "style-src 'self'; "  # Allow styles only from the current domain
        "img-src 'self'; "  # Images only from the current domain
    )

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Range"
    response.headers["Accept-Ranges"] = "bytes"

    response.headers['Content-Security-Policy'] = strict_csp
    response.headers['Content-Type'] = mimetype
    response.headers['Cross-Origin-Resource-Policy'] = 'cross-origin'

    return response


@media_blueprint.route('/stream', methods=['GET'])
@feature_required_with_cookie(media_blueprint, VIEW_MEDIA)
def stream_media_file(user_details):
    """
    Stream a file from the server
    :return: File contents
    """
    if not current_app.config[PROPERTY_SERVER_MEDIA_READY]:
        return generate_failure_response(
            'This feature is not ready.  Please configure the app properties and restart the server.')

    file_id = clean_string(request.args.get('file_id'))

    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    if not is_guid(file_id):
        return generate_failure_response('invalid file_id value', 404)

    file = find_file_by_id(file_id)

    if file is None:
        return generate_failure_response('file not found', 404)

    is_archive = file.archive
    mimetype = file.mime_type

    containing_folder = file.mediafolder

    if containing_folder is None:
        return generate_failure_response('file error, missing parent', 400)

    if not folder_rating_checks(containing_folder) or not folder_group_checks(containing_folder):
        return generate_failure_response('User is not allowed to see this folder', 403)

    target_path = get_data_for_mediafile(file, current_app.config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER],
                                         current_app.config[PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER])

    if target_path is None or not os.path.isfile(target_path):
        return generate_failure_response('requested file not found', 404)

    range_header = request.headers.get('Range', None)
    if range_header:
        # Handle byte range requests for partial content
        try:
            start, end = parse_range_header(range_header, os.path.getsize(target_path))
            length = end - start + 1
            response = Response(
                stream_with_context(read_file_chunk(target_path, start, length)),
                206,  # Partial Content
                mimetype=mimetype,
                headers={
                    'Content-Range': f'bytes {start}-{end}/{os.path.getsize(target_path)}',
                    'Accept-Ranges': 'bytes',
                    'Content-Length': str(length),
                }
            )
            return response
        except ValueError:
            return generate_failure_response('Invalid range', 416)  # Range Not Satisfiable

    # Stream the entire file if no range is provided
    response = send_file(target_path, mimetype=mimetype)

    origin = request.headers.get("Origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    else:
        # fallback if no Origin header was sent (like curl/wget)
        response.headers["Access-Control-Allow-Origin"] = "*"

    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Range, Authorization"

    return response


@media_blueprint.route('/request-unsafe-stream', methods=['POST'])
@feature_required_with_cookie(media_blueprint, VIEW_MEDIA)
def request_unsafe_stream_media_file(user_details):
    """
    Stream a file from the server
    :return: File contents
    """
    if not current_app.config[PROPERTY_SERVER_MEDIA_READY]:
        return generate_failure_response(
            'This feature is not ready.  Please configure the app properties and restart the server.')

    # Check post first
    file_id = clean_string(request.form.get('file_id'))
    if not file_id:
        # Fallabck to query
        file_id = clean_string(request.args.get('file_id'))

    # Checkers
    folder_group_checks = get_folder_group_checker(user_details)
    folder_rating_checks = get_folder_rating_checker(user_details)

    if not is_guid(file_id):
        return generate_failure_response('invalid file_id value', 404, messages=[msg_invalid_parameter('file_id')])

    file = find_file_by_id(file_id)

    if file is None:
        return generate_failure_response('file not found', 404, messages=[msg_action_cancelled_wrong()])

    containing_folder = file.mediafolder

    if containing_folder is None:
        return generate_failure_response('file error, missing parent', 400, messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checks(containing_folder) or not folder_group_checks(containing_folder):
        return generate_failure_response('User is not allowed to see this folder', 403,
                                         messages=[msg_access_denied_content_rating()])

    slc: ShortLivedCache = current_app.config[APP_KEY_SLC]

    cache_id = slc.add_item(file.id)

    return generate_success_response('', {"cache_id": cache_id})


@media_blueprint.route('/unsafe-stream', methods=['GET'])
def unsafe_stream_media_file():
    """
    Stream a file from the server
    :return: File contents
    """
    if not current_app.config[PROPERTY_SERVER_MEDIA_READY]:
        return generate_failure_response(
            'This feature is not ready.  Please configure the app properties and restart the server.')

    cache_id = clean_string(request.args.get('cache_id'))

    slc: ShortLivedCache = current_app.config[APP_KEY_SLC]

    cache_item = slc.get_item(cache_id)

    if cache_item is None:
        return generate_failure_response('file not found', 404)

    file_id = cache_item['file_id']

    file = find_file_by_id(file_id)

    if file is None:
        return generate_failure_response('file not found', 404)

    is_archive = file.archive
    mimetype = file.mime_type

    target_path = get_data_for_mediafile(file, current_app.config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER],
                                         current_app.config[PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER])

    if target_path is None or not os.path.isfile(target_path):
        return generate_failure_response('requested file not found', 404)

    range_header = request.headers.get('Range', None)
    if range_header:
        # Handle byte range requests for partial content
        try:
            start, end = parse_range_header(range_header, os.path.getsize(target_path))
            length = end - start + 1
            response = Response(
                stream_with_context(read_file_chunk(target_path, start, length)),
                206,  # Partial Content
                mimetype=mimetype,
                headers={
                    'Content-Range': f'bytes {start}-{end}/{os.path.getsize(target_path)}',
                    'Accept-Ranges': 'bytes',
                    'Content-Length': str(length),
                }
            )
            return response
        except ValueError:
            return generate_failure_response('Invalid range', 416)  # Range Not Satisfiable

    # Stream the entire file if no range is provided
    response = send_file(target_path, mimetype=mimetype)

    origin = request.headers.get("Origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    else:
        # fallback if no Origin header was sent (like curl/wget)
        response.headers["Access-Control-Allow-Origin"] = "*"

    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Range"

    return response


# Node Logic

@media_blueprint.route('/nodes', methods=['POST'])
@feature_required(media_blueprint, VIEW_MEDIA | MEDIA_PLUGINS)
def get_media_nodes(user_details: dict) -> tuple:
    """
        Retrieve a list of nodes from the Media service.

        Args:
        user_details (dict): Details of the authenticated user.

        Returns:
        tuple: JSON response with the list of node, message and status code.
        """
    if not current_app.config[PROPERTY_SERVER_MEDIA_READY]:
        return generate_failure_response(
            'This feature is not ready.  Please configure the app properties and restart the server.')

    folder_id = clean_string(request.form.get('node_id'))

    folder_data = []
    max_rating = get_media_max_rating(user_details)
    max_rating_checker = get_folder_rating_checker(user_details)

    folder_checker = get_folder_group_checker(user_details)

    if is_not_blank(folder_id):

        # Make sure the requested parent folder exists!
        current_folder = find_folder_by_id(folder_id)
        if current_folder is None:
            return generate_failure_response('Node not found', 404, messages=[msg_access_denied_content_rating()])

        # And the user can see it!
        if not max_rating_checker(current_folder):
            return generate_failure_response('User is not allowed to view content out of their rating zone',
                                             messages=[msg_access_denied_content_rating()])

        if not folder_checker(current_folder):
            return generate_failure_response('User is not allowed to see a node that is owned by another group',
                                             messages=[msg_access_denied_content_rating()])

        # Grab the folders
        folder_rows = find_folders_in_folder(folder_id, None, max_rating, 0, 0, db_session=None)
    else:
        # Grab Root Folders
        folder_rows = find_root_folders(None, max_rating, 0, 0, db_session=None)

    for row in folder_rows:
        if folder_checker(row) and max_rating_checker(row):
            folder_data.append(
                {"id": row.id, "name": row.name, "rating": row.rating}
            )

    return generate_success_response('', {"nodes": folder_data})


@media_blueprint.route('/node', methods=['POST'])
@feature_required(media_blueprint, VIEW_MEDIA | MEDIA_PLUGINS)
def get_media_node(user_details: dict) -> tuple:
    """
        Retrieve a node from the Media service.

        Args:
        user_details (dict): Details of the authenticated user.

        Returns:
        tuple: JSON response with a node, message and status code.
        """
    if not current_app.config[PROPERTY_SERVER_MEDIA_READY]:
        return generate_failure_response(
            'This feature is not ready.  Please configure the app properties and restart the server.')

    folder_id = clean_string(request.form.get('node_id'))

    max_rating_checker = get_folder_rating_checker(user_details)

    folder_checker = get_folder_group_checker(user_details)

    if is_not_blank(folder_id):

        current_folder = find_folder_by_id(folder_id)

        # Make sure the folder exists!
        if current_folder is None:
            return generate_failure_response('Node not found', 404, messages=[msg_action_cancelled_wrong()])

        # And the user can see it!
        if not max_rating_checker(current_folder):
            return generate_failure_response('User is not allowed to view content out of their rating zone',
                                             messages=[msg_access_denied_content_rating()])

        if not folder_checker(current_folder):
            return generate_failure_response('User is not allowed to see a folder that is owned by another group',
                                             messages=[msg_access_denied_content_rating()])

    else:
        # We need a NODE ID
        return generate_failure_response('node_id is required')

    return generate_success_response('', {
        "node": {"id": current_folder.id, "name": current_folder.name, "rating": current_folder.rating}})


# Grouping Logic

@media_blueprint.route('/list/groups', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def list_groups(user_details):
    """
    List all groups from a Media user's point of view.
    """

    user_features = get_user_features(user_details)

    if user_features & MANAGE_APP == MANAGE_APP:
        groups = get_all_groups()
    else:
        user_group_id = get_user_group_id(user_details)
        groups = []
        if user_group_id is not None:
            group = get_group_by_id(user_group_id)
            if group is not None:
                groups.append(group)

    group_list = []

    for group in groups:
        row = {'id': group.id, 'name': group.name, 'description': ''}
        group_list.append(row)

    return generate_success_response('', {"groups": group_list})


# Recent History

@media_blueprint.route('/list/history', methods=['POST'])
@feature_required(media_blueprint, VIEW_MEDIA)
def list_history(user_details):
    user_uid = get_uid(user_details)

    max_rating = get_media_max_rating(user_details)

    rows = find_progress_entries(user_uid, max_rating)

    results = []

    for row, folder_name, folder_id in rows:

        user_progress = row.progress
        if user_progress is None:
            progress = '0'
        else:
            progress = f'{user_progress:.5f}'

        the_time = convert_datetime_to_yyyymmdd(row.timestamp)

        results.append(
            {"folder_name": folder_name, "folder_id": folder_id, "file_id": row.file_id, "name": row.file.filename,
             "mime_type": row.file.mime_type, "preview": row.file.preview,
             "progress": progress, "timestamp": the_time})

    return generate_success_response('', {"history": results})


# Recent History

@media_blueprint.route('/list/tags', methods=['POST'])
@feature_required(media_blueprint, VIEW_MEDIA)
def list_tags(user_details):
    rows = get_all_tags()

    results = []

    for row in rows:
        results.append(
            {"bit": row.bit, "value": (1 << row.bit), "short": row.short_tag, "long": row.long_tag,
             "description": row.description, })

    return generate_success_response('', {"tags": results})


@media_blueprint.route('/get/tag', methods=['POST'])
@feature_required(media_blueprint, VIEW_MEDIA)
def get_tag(user_details):
    bit_value = clean_string(request.form.get('bit'))

    # Validate input parameters
    if is_blank(bit_value):
        return generate_failure_response('bit parameter required', 400, messages=[msg_missing_parameter('bit')])

    if not is_integer(bit_value):
        return generate_failure_response('bit parameter is not an integer', 400,
                                         messages=[msg_invalid_parameter('bit')])

    row = get_tag_row(int(bit_value), db.session)

    if not row:
        return generate_failure_response('tag not found', 404)

    result = {"bit": row.bit, "value": (1 << row.bit), "short": row.short_tag, "long": row.long_tag,
              "description": row.description, }

    return generate_success_response('', {"tag": result})


@media_blueprint.route('/new/tag', methods=['POST'])
@feature_required_silent(media_blueprint, MANAGE_MEDIA)
def create_tag():
    """
    Create a new group with the provided details.
    """
    bit_value = clean_string(request.form.get('bit'))
    short_name = clean_string(request.form.get('short'))
    long_name = clean_string(request.form.get('long'))
    description = clean_string(request.form.get('description'))

    # Validate input parameters
    if is_blank(bit_value):
        return generate_failure_response('bit parameter required', 400, messages=[msg_missing_parameter('bit')])
    if is_blank(short_name):
        return generate_failure_response('short parameter required', 400, messages=[msg_missing_parameter('short')])
    if is_blank(long_name):
        return generate_failure_response('long parameter required', 400, messages=[msg_missing_parameter('long')])

    new_tag = MediaFolderTag(bit=bit_value, short_tag=short_name, long_tag=long_name, description=description)

    try:
        db.session.add(new_tag)
        db.session.commit()

    except IntegrityError as e:
        logging.exception(e)
        db.session.rollback()
        return generate_failure_response(f'Tag {short_name} already exists or other exception, please see log', 400,
                                         messages=[msg_action_cancelled_wrong()])

    return generate_success_response(f'Tag {short_name} created', messages=[msg_operation_complete()])


@media_blueprint.route('/remove/tag', methods=['POST'])
@feature_required_silent(media_blueprint, MANAGE_MEDIA)
def delete_tag():
    """
    Delete a user by user_id. The current user cannot delete themselves.
    """
    tag_bit = clean_string(request.form.get('bit'))
    if not is_integer(tag_bit):
        return generate_failure_response('bit parameter is not an integer', 400,
                                         messages=[msg_invalid_parameter('bit')])
    bit = int(tag_bit)

    item = MediaFolderTag.query.get(bit)
    if not item:
        return generate_failure_response('Tag not found', 404, messages=[msg_action_failed_missing()])

    db.session.delete(item)
    db.session.commit()

    return generate_success_response('Tag deleted')


@media_blueprint.route('/update/tag', methods=['POST'])
@feature_required_silent(media_blueprint, MANAGE_MEDIA)
def update_tag():
    """
    Update the value of a property.
    """
    bit_id = clean_string(request.form.get('bit'))
    short = clean_string(request.form.get('short'))
    long = clean_string(request.form.get('long'))
    description = clean_string(request.form.get('description'))

    if is_blank(bit_id):
        return generate_failure_response('bit parameter is required', 400,
                                         messages=[msg_missing_parameter('bit')])
    if is_blank(short):
        return generate_failure_response('short parameter is required', 400,
                                         messages=[msg_missing_parameter('short')])
    if is_blank(long):
        return generate_failure_response('long parameter is required', 400,
                                         messages=[msg_missing_parameter('long')])

    if not is_integer(bit_id):
        return generate_failure_response('bit parameter is not an integer', 400,
                                         messages=[msg_invalid_parameter('bit')])

    item = MediaFolderTag.query.get(int(bit_id))
    if not item:
        return generate_failure_response('Tag not found', 404, messages=[msg_action_failed_missing()])

    item.short_tag = short
    item.long_tag = long
    item.description = description

    db.session.commit()

    return generate_success_response(f'Tag {short} updated', messages=[msg_operation_complete()])


@media_blueprint.route('/apply/tag', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def apply_tag(user_details):
    """
    Update the value of a property.
    """

    folder_id = clean_string(request.form.get('folder_id'))
    bit_id = clean_string(request.form.get('bit'))

    if is_blank(bit_id):
        return generate_failure_response('bit parameter is required', 400,
                                         messages=[msg_missing_parameter('bit')])
    if is_blank(folder_id):
        return generate_failure_response('folder_id parameter is required', 400,
                                         messages=[msg_missing_parameter('folder_id')])

    if not is_integer(bit_id):
        return generate_failure_response('bit parameter is not an integer', 400,
                                         messages=[msg_invalid_parameter('bit')])

    folder_group_checker = get_folder_group_checker(user_details)
    folder_rating_checker = get_folder_rating_checker(user_details)

    folder_row = find_folder_by_id(folder_id)

    if folder_row is None:
        return generate_failure_response('Could not find requested folder', messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checker(folder_row.rating):
        return generate_failure_response('User is not allowed to see a folder with a higher rating limit',
                                         messages=[msg_access_denied_content_rating()])

    # App Admins see everything
    if not folder_group_checker(folder_row):
        return generate_failure_response('User is not allowed to see a folder that is owned by another group',
                                         messages=[msg_access_denied_content_rating()])

    folder_row.add_folder_tag(int(bit_id))

    db.session.commit()

    return generate_success_response(f'Tag {bit_id} applied to folder', messages=[msg_operation_complete()])


@media_blueprint.route('/detach/tag', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def detach_tag(user_details):
    """
    Update the value of a property.
    """

    folder_id = clean_string(request.form.get('folder_id'))
    bit_id = clean_string(request.form.get('bit'))

    if is_blank(bit_id):
        return generate_failure_response('bit parameter is required', 400,
                                         messages=[msg_missing_parameter('bit')])
    if is_blank(folder_id):
        return generate_failure_response('folder_id parameter is required', 400,
                                         messages=[msg_missing_parameter('folder_id')])

    if not is_integer(bit_id):
        return generate_failure_response('bit parameter is not an integer', 400,
                                         messages=[msg_invalid_parameter('bit')])

    folder_group_checker = get_folder_group_checker(user_details)
    folder_rating_checker = get_folder_rating_checker(user_details)

    folder_row = find_folder_by_id(folder_id)

    if folder_row is None:
        return generate_failure_response('Could not find requested folder', messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checker(folder_row.rating):
        return generate_failure_response('User is not allowed to see a folder with a higher rating limit',
                                         messages=[msg_access_denied_content_rating()])

    # App Admins see everything
    if not folder_group_checker(folder_row):
        return generate_failure_response('User is not allowed to see a folder that is owned by another group',
                                         messages=[msg_access_denied_content_rating()])

    folder_row.remove_folder_tag(int(bit_id))

    db.session.commit()

    return generate_success_response(f'Tag {bit_id} removed from folder', messages=[msg_operation_complete()])


# ==============================================================================
# Folder Key Values: Manage per-folder key/value rows
# ==============================================================================

def _acquire_folder_for_access(user_details: dict, folder_id: str) -> tuple:
    """
    Resolve a folder by id and verify the user is allowed to manage it.

    Args:
    user_details (dict): Details of the authenticated user.
    folder_id (str): The folder identifier to resolve.

    Returns:
    tuple: (folder, None) on success, or (None, failure_response) when the folder
    is missing or the user is not permitted to manage it.
    """
    folder_group_checker = get_folder_group_checker(user_details)
    folder_rating_checker = get_folder_rating_checker(user_details)

    folder_row = find_folder_by_id(folder_id)

    if folder_row is None:
        return None, generate_failure_response('Could not find requested folder',
                                               messages=[msg_action_cancelled_wrong()])

    if not folder_rating_checker(folder_row.rating):
        return None, generate_failure_response('User is not allowed to see a folder with a higher rating limit',
                                               messages=[msg_access_denied_content_rating()])

    # App Admins see everything
    if not folder_group_checker(folder_row):
        return None, generate_failure_response('User is not allowed to see a folder that is owned by another group',
                                               messages=[msg_access_denied_content_rating()])

    return folder_row, None


@media_blueprint.route('/keys/list', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def list_media_folder_keys(user_details: dict) -> tuple:
    """
    Retrieve all key/value rows stored for a folder.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the list of key/value rows and HTTP status code.
    """
    folder_id = clean_string(request.form.get('folder_id'))

    if is_blank(folder_id):
        return generate_failure_response('folder_id parameter is required',
                                         messages=[msg_missing_parameter('folder_id')])

    folder_row, error = _acquire_folder_for_access(user_details, folder_id)
    if error is not None:
        return error

    items = []
    for row in find_media_folder_key_values(folder_id):
        items.append({"id": row.id, "folder": row.folder_id, "key": row.key,
                      "value": row.value if row.value is not None else "", "purpose": row.purpose})

    return generate_success_response('', {'items': items})


@media_blueprint.route('/keys/get', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def get_media_folder_key(user_details: dict) -> tuple:
    """
    Retrieve a single key/value row for a folder.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the key/value row and HTTP status code.
    """
    folder_id = clean_string(request.form.get('folder_id'))
    row_id = clean_string(request.form.get('row_id'))

    if is_blank(folder_id):
        return generate_failure_response('folder_id parameter is required',
                                         messages=[msg_missing_parameter('folder_id')])

    if is_blank(row_id):
        return generate_failure_response('row_id parameter is required',
                                         messages=[msg_missing_parameter('row_id')])

    if not is_integer(row_id):
        return generate_failure_response('row_id parameter is invalid', messages=[msg_invalid_parameter('row_id')])

    folder_row, error = _acquire_folder_for_access(user_details, folder_id)
    if error is not None:
        return error

    row = find_media_folder_key_value(folder_id, int(row_id))

    if row is None:
        return generate_failure_response('Key not found', messages=[msg_action_cancelled_wrong()])

    return generate_success_response('', {'info': {"id": row.id, "folder": row.folder_id, "key": row.key,
                                                   "value": row.value if row.value is not None else "",
                                                   "purpose": row.purpose}})


@media_blueprint.route('/keys/insert', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def insert_media_folder_key(user_details: dict) -> tuple:
    """
    Add a key/value row for a folder.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the status of the operation and HTTP status code.
    """
    folder_id = clean_string(request.form.get('folder_id'))
    key = clean_string(request.form.get('key'))
    value = clean_string(request.form.get('value'))
    purpose = clean_string(request.form.get('purpose'))

    if is_blank(folder_id):
        return generate_failure_response('folder_id parameter is required',
                                         messages=[msg_missing_parameter('folder_id')])

    if is_blank(key):
        return generate_failure_response('key parameter is required', messages=[msg_missing_parameter('key')])

    if is_not_blank(purpose) and not is_integer(purpose):
        return generate_failure_response('purpose parameter is invalid', messages=[msg_invalid_parameter('purpose')])

    folder_row, error = _acquire_folder_for_access(user_details, folder_id)
    if error is not None:
        return error

    effective_value = value if is_not_blank(value) else None
    effective_purpose = int(purpose) if is_not_blank(purpose) else MEDIA_FOLDER_KEY_PURPOSE_DEFAULT

    row = add_media_folder_key_value(db.session, folder_id, key, effective_value, effective_purpose)
    if row is None:
        return generate_failure_response('Key already exists or other exception, please see log', 400,
                                         messages=[msg_action_cancelled_wrong()])

    return generate_success_response('Key added successfully', {'id': row.id},
                                     messages=[msg_operation_complete()])


@media_blueprint.route('/keys/update', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def update_media_folder_key(user_details: dict) -> tuple:
    """
    Update an existing key/value row for a folder.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the status of the operation and HTTP status code.
    """
    folder_id = clean_string(request.form.get('folder_id'))
    row_id = clean_string(request.form.get('row_id'))
    value = clean_string(request.form.get('value'))
    purpose = clean_string(request.form.get('purpose'))

    if is_blank(folder_id):
        return generate_failure_response('folder_id parameter is required',
                                         messages=[msg_missing_parameter('folder_id')])

    if is_blank(row_id):
        return generate_failure_response('row_id parameter is required',
                                         messages=[msg_missing_parameter('row_id')])

    if not is_integer(row_id):
        return generate_failure_response('row_id parameter is invalid', messages=[msg_invalid_parameter('row_id')])

    if is_not_blank(purpose) and not is_integer(purpose):
        return generate_failure_response('purpose parameter is invalid', messages=[msg_invalid_parameter('purpose')])

    folder_row, error = _acquire_folder_for_access(user_details, folder_id)
    if error is not None:
        return error

    effective_value = value if is_not_blank(value) else None
    effective_purpose = int(purpose) if is_not_blank(purpose) else None

    if update_media_folder_key_value(db.session, folder_id, int(row_id), effective_value, effective_purpose) is None:
        return generate_failure_response('Key not found', messages=[msg_action_cancelled_wrong()])

    return generate_success_response('Key updated successfully', messages=[msg_operation_complete()])


@media_blueprint.route('/keys/delete', methods=['POST'])
@feature_required(media_blueprint, MANAGE_MEDIA)
def delete_media_folder_key(user_details: dict) -> tuple:
    """
    Remove a key/value row for a folder.

    Args:
    user_details (dict): Details of the authenticated user.

    Returns:
    tuple: JSON response with the status of the operation and HTTP status code.
    """
    folder_id = clean_string(request.form.get('folder_id'))
    row_id = clean_string(request.form.get('row_id'))

    if is_blank(folder_id):
        return generate_failure_response('folder_id parameter is required',
                                         messages=[msg_missing_parameter('folder_id')])

    if is_blank(row_id):
        return generate_failure_response('row_id parameter is required',
                                         messages=[msg_missing_parameter('row_id')])

    if not is_integer(row_id):
        return generate_failure_response('row_id parameter is invalid', messages=[msg_invalid_parameter('row_id')])

    folder_row, error = _acquire_folder_for_access(user_details, folder_id)
    if error is not None:
        return error

    if remove_media_folder_key_value(db.session, folder_id, int(row_id)):
        return generate_success_response('Key removed successfully', messages=[msg_operation_complete()])
    else:
        return generate_failure_response('Key not found', messages=[msg_action_cancelled_wrong()])
