import json
import mimetypes
import os
import random
import shutil
import string
import tempfile
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import urlparse

from thread_utils import TaskWrapper, NoOpTaskWrapper


def delete_empty_folders(folder_path, logger: TaskWrapper = None):
    """
    Delete empty folders in the specified directory.

    Args:
    folder_path (str): Directory path to search for empty folders.
    logger (TaskWrapper): TaskWrapper object for logging.
    """
    # Walk through the directory tree from bottom to top
    for root, dirs, files in os.walk(folder_path, topdown=False):
        for directory in dirs:
            dir_path = os.path.join(root, directory)
            # Check if the directory contains any image files
            if not any(file.endswith(('.jpg', '.gif', '.png')) for file in os.listdir(dir_path)):
                # Check if the directory is empty
                if not os.listdir(dir_path):
                    if logger is not None:
                        # Log a warning if a logger is provided
                        logger.set_warning()
                        logger.warn(f'Erased empty folder {dir_path}')
                    # Remove the empty directory
                    os.rmdir(dir_path)


def newest_file_date(folder_path: str) -> int:
    """
    Get the newest file's last modified time in the specified folder.

    Args:
    folder_path (str): Path to the folder containing files.

    Returns:
    int: Date of the newest file in YYYYMMDD format.
    """
    # Initialize variable to hold the newest timestamp
    newest_timestamp: int = 20010101

    # Iterate through files in the folder (1 level deep)
    for filename in os.listdir(folder_path):
        file_path: str = os.path.join(folder_path, filename)

        # Check if the path is a file (and not a directory)
        if os.path.isfile(file_path):
            # Get the file's last modified time
            file_timestamp: int = int(os.path.getmtime(file_path))

            # Update if this file is newer than the current newest
            if file_timestamp > newest_timestamp:
                newest_timestamp = file_timestamp

    # Convert the newest timestamp to an integer format
    newest_date: str = datetime.fromtimestamp(newest_timestamp).strftime('%Y%m%d')

    return int(newest_date)


def read_json_file(json_file: str) -> dict:
    """
    Read and parse a JSON file.

    Args:
    json_file (str): Path to the JSON file.

    Returns:
    dict: Dictionary containing the data from the JSON file.
    """
    with open(json_file, 'r') as file:
        data = json.load(file)
    return data


def create_random_folder(base_path):
    # Generate a random folder name (e.g., 8 random characters)
    random_folder_name = ''.join(random.choices(string.ascii_letters + string.digits, k=12))

    # Create the full path for the new folder
    new_folder_path = os.path.join(base_path, random_folder_name)

    # Create the new folder
    os.makedirs(new_folder_path, exist_ok=True)

    return new_folder_path


def is_valid_mime_type(mime_type):
    # Try to guess an extension based on the MIME type
    extension = mimetypes.guess_extension(mime_type)

    # If there's no extension, the MIME type is likely invalid
    return extension is not None


def is_valid_url(url):
    parsed = urlparse(url)
    return all([parsed.scheme, parsed.netloc])


@contextmanager
def temporary_folder(base_folder=None, task_wrapper: TaskWrapper = NoOpTaskWrapper()):
    """
    Context manager to create a temporary folder, provide it to the block,
    and clean it up afterward.

    :param base_folder: Optional base folder where the temporary folder will be created.
    :param task_wrapper: Optional Logger
    :yield: Path to the temporary folder.
    """
    temp_folder = tempfile.mkdtemp(dir=base_folder)
    try:
        if task_wrapper.can_trace():
            task_wrapper.trace(f'Enter Temp Folder: {temp_folder}')
        yield temp_folder
    finally:
        # Clean up the temporary folder
        shutil.rmtree(temp_folder, ignore_errors=True)
        if task_wrapper.can_trace():
            task_wrapper.trace(f'Exit Temp Folder: {temp_folder}')


def create_timestamped_folder(base_path):
    # Get the current timestamp in "YYYY-MM-DD_HH-MM-SS" format
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # Create the new folder path
    new_folder_path = os.path.join(base_path, timestamp)
    # Create the folder
    os.makedirs(new_folder_path, exist_ok=True)
    # Return the new folder path
    return new_folder_path

def is_text_file(file_path, num_bytes=64):
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(num_bytes)
        # Try decoding as UTF-8 (strict mode to catch encoding issues)
        chunk.decode('utf-8')
        return True  # Successfully decoded as UTF-8, so it's text
    except (UnicodeDecodeError, FileNotFoundError):
        pass

    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(num_bytes + 1)
        # Try decoding as UTF-8 (strict mode to catch encoding issues)
        chunk.decode('utf-8')
        return True  # Successfully decoded as UTF-8, so it's text
    except (UnicodeDecodeError, FileNotFoundError):
        pass

    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(num_bytes + 2)
        # Try decoding as UTF-8 (strict mode to catch encoding issues)
        chunk.decode('utf-8')
        return True  # Successfully decoded as UTF-8, so it's text
    except (UnicodeDecodeError, FileNotFoundError):
        return False


def reset_folder(folder_path):
    # Remove the folder and its contents if it exists
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)

    # Recreate the empty folder
    os.makedirs(folder_path, exist_ok=True)