import os

from auth_utils import get_user_features, get_user_group_id, get_user_media_limit
from db import MediaFile, MediaFolder
from feature_flags import MANAGE_APP


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
