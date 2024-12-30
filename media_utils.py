import logging
import os
from typing import Optional
from datetime import datetime
import mimetypes
import shutil

from flask_sqlalchemy.session import Session
from webvtt import WebVTT

from auth_utils import get_user_features, get_user_group_id, get_user_media_limit
from db import MediaFile, MediaFolder, db
from feature_flags import MANAGE_APP
from media_queries import find_folder_by_id, find_file_by_id, insert_file
from text_utils import is_guid
from thread_utils import TaskWrapper


def clean_files_for_mediafile(file: MediaFile, primary_path: str, archive_path: str):
    # Preview
    file_path = get_preview_for_mediafile(file, primary_path)

    if os.path.exists(file_path) and os.path.isfile(file_path):
        os.unlink(file_path)

    # Look for the file
    file_path = get_data_for_mediafile(file, primary_path, archive_path)

    if os.path.exists(file_path) and os.path.isfile(file_path):
        os.unlink(file_path)


def get_preview_for_mediafile(file: MediaFile, primary_path: str) -> str:
    return os.path.join(primary_path, file.id + '_prev.png')


def get_data_for_mediafile(file: MediaFile, primary_path: str, archive_path: str) -> str:
    # Look for the file
    if file.archive:
        return os.path.join(archive_path, file.id + '.dat')
    else:
        return os.path.join(primary_path, file.id + '.dat')


def calculate_offset_limit(offset, limit, folder_count, file_count):
    total_count = folder_count + file_count
    if offset >= total_count:
        # Offset is beyond the total items, no items to fetch
        return {
            "folders_needed": False,
            "folder_offset": None,
            "folder_limit": None,
            "files_needed": False,
            "file_offset": None,
            "file_limit": None,
        }

    # Determine the remaining items to fetch after applying the offset
    remaining_limit = min(limit, total_count - offset)

    # Check if we need to fetch folders
    if offset < folder_count:
        folder_offset = offset
        folder_limit = min(folder_count - folder_offset, remaining_limit)
        remaining_limit -= folder_limit
        folders_needed = True
    else:
        # Offset is beyond the folders, start directly with files
        folder_offset = None
        folder_limit = None
        folders_needed = False

    # Check if we need to fetch files
    if remaining_limit > 0:
        if offset >= folder_count:
            file_offset = offset - folder_count
        else:
            file_offset = 0
        file_limit = remaining_limit
        files_needed = True
    else:
        file_offset = None
        file_limit = None
        files_needed = False

    return {
        "folders_needed": folders_needed,
        "folder_offset": folder_offset,
        "folder_limit": folder_limit,
        "files_needed": files_needed,
        "file_offset": file_offset,
        "file_limit": file_limit,
    }


def parse_range_header(header, video_size):
    """
    Utility to figure out what BYTES are requested
    :param header:
    :param video_size:
    :return:
    """
    # Extract start and end positions from the range header
    if header.startswith('bytes='):
        parts = header.split('=')[1].split('-')
        start = int(parts[0])
        end = int(parts[1]) if parts[1] else video_size - 1
    else:
        start, end = 0, video_size - 1
    return start, end


def read_file_chunk(filepath, start, length, chunk_size=8192):
    """
    Generator to read a file in chunks.
    """
    with open(filepath, 'rb') as f:
        f.seek(start)
        remaining = length
        while remaining > 0:
            chunk = f.read(min(chunk_size, remaining))
            if not chunk:
                break
            yield chunk
            remaining -= len(chunk)


def get_media_max_rating(user_details):
    max_rating = 0
    if 'limits' in user_details and 'media' in user_details['limits']:
        max_rating = user_details['limits']['media']
    return max_rating


def _folder_group_user_has_no_group(folder: MediaFolder) -> bool:
    return folder.owning_group_id is None


def _folder_group_user_is_admin(folder: MediaFolder) -> bool:
    return True


def get_folder_group_checker(user_details):
    features = get_user_features(user_details)
    if (features & MANAGE_APP) == MANAGE_APP:
        return _folder_group_user_is_admin
    group_id = get_user_group_id(user_details)
    if group_id is None:
        return _folder_group_user_has_no_group

    def _folder_group_user_has_access(folder: MediaFolder) -> bool:
        return folder.owning_group_id is None or folder.owning_group_id == group_id

    return _folder_group_user_has_access


def _folder_rating_unlimited(folder: MediaFolder) -> bool:
    return True


def get_folder_rating_checker(user_details):
    max_level = get_user_media_limit(user_details)
    # Can see all
    if max_level == 200:
        return _folder_rating_unlimited

    # Need to make a limiter
    def _folder_rating_limit_user(folder: MediaFolder) -> bool:
        return folder.rating <= max_level

    return _folder_rating_limit_user


def user_can_see_rating(user_details, rating: int) -> bool:
    return rating <= get_user_media_limit(user_details)


def get_filename_with_extension(video_filename, file_ending: str):
    """Return the SRT filename for a given video filename."""
    base_name, _ = os.path.splitext(video_filename)
    return f"{base_name}.{file_ending}"


def convert_vtt_to_srt(vtt_file, srt_file):
    try:
        """Convert a VTT file to SRT format."""
        vtt = WebVTT.read(vtt_file)
        with open(srt_file, 'w', encoding='utf-8') as f:
            for i, caption in enumerate(vtt):
                f.write(f"{i + 1}\n")
                f.write(f"{caption.start} --> {caption.end}\n")
                f.write(f"{caption.text}\n\n")
        return True
    except Exception as e:
        logging.exception(e)
        return False


def get_file_by_user(file_id: str, user_details, db_session: Session = db.session) -> Optional[
    tuple[MediaFile, MediaFolder]]:
    if not is_guid(file_id):
        raise ValueError('file_id is not a valid GUID')

    file = find_file_by_id(file_id, db_session)

    if file is None:
        raise ValueError('Could not find file')

    folder = file.mediafolder

    if folder is None:
        raise ValueError('Could not find folder')

    folder_rating_checker = get_folder_rating_checker(user_details)
    folder_group_checker = get_folder_group_checker(user_details)

    # Make sure they can see it
    if not folder_rating_checker(folder):
        raise ValueError('User does not have access to folder via Rating Limit')

    if not folder_group_checker(folder):
        raise ValueError('User does not have access to folder via Security Group')

    return file, folder


def get_folder_by_user(folder_id: str, user_details, db_session: Session = db.session) -> Optional[MediaFolder]:
    if not is_guid(folder_id):
        raise ValueError('file_id is not a valid GUID')

    folder = find_folder_by_id(folder_id, db_session)

    if folder is None:
        raise ValueError('Could not find folder')

    folder_rating_checker = get_folder_rating_checker(user_details)
    folder_group_checker = get_folder_group_checker(user_details)

    # Make sure they can see it
    if not folder_rating_checker(folder):
        raise ValueError('User does not have access to folder via Rating Limit')

    if not folder_group_checker(folder):
        raise ValueError('User does not have access to folder via Security Group')

    return folder


def describe_file_size_change(old_size, new_size):
    """
    Describes the change in file size between two values in a human-readable format.

    :param old_size: Original file size in bytes.
    :param new_size: New file size in bytes.
    :return: A string describing the change in size.
    """

    def format_size(size):
        # Helper function to format bytes into a human-readable size
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"

    change = new_size - old_size
    percentage_change = (change / old_size) * 100 if old_size != 0 else float('inf')
    old_size_str = format_size(old_size)
    new_size_str = format_size(new_size)

    if change > 0:
        return f"The file increased in size by {percentage_change:.2f}% ({old_size_str} to {new_size_str})."
    elif change < 0:
        return f"The file decreased in size by {abs(percentage_change):.2f}% ({old_size_str} to {new_size_str})."
    else:
        return f"The file size did not change ({old_size_str})."

def ingest_file(item_path: str, item_name: str, folder_id: str, is_archive: bool, primary_path: str, archive_path: str, db_session: Session, task_wrapper: TaskWrapper) -> bool:
    if os.path.isfile(item_path):
        # Get file size
        file_size = os.path.getsize(item_path)

        # Get created time and convert to readable format
        created_time = os.path.getctime(item_path)
        created_datetime = datetime.fromtimestamp(created_time)

        mime_type, _ = mimetypes.guess_type(item_path)  # MIME type

        if mime_type is not None:

            modified_name = str(item_name)

            new_file = insert_file(folder_id, modified_name, mime_type, is_archive, False,
                                   file_size, created_datetime, db_session)

            dest_path = get_data_for_mediafile(new_file, primary_path, archive_path)

            shutil.move(str(item_path), str(dest_path))

            return True
        else:
            task_wrapper.warn(f'Ignoring file {item_name}, unknown MIME TYPE')

    return False