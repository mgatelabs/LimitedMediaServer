import json
import os
import tempfile
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse
import mimetypes

import requests
from bs4 import BeautifulSoup

from curl_utils import custom_curl_get, read_temp_file, custom_curl_post, custom_curl_headers
from thread_utils import TaskWrapper

def download_unsecure_file(url, destination_folder, filename, headers=None, task_logger: TaskWrapper = None):
    """
    Download a file from the given URL and save it to the specified path with the given filename.

    Args:
    url (str): The URL of the file to download.
    destination_folder (str): The path of the folder where the file will be saved.
    filename (str): The name of the file.

    Returns:
    bool: True if the download was successful, False otherwise.
    """
    if headers is None:
        headers = {}
    try:
        # Create destination folder if it doesn't exist
        os.makedirs(destination_folder, exist_ok=True)

        # Get the file content from the URL
        response = requests.get(url, headers=headers)

        if response.status_code == 403:
            print("Not authorized:", url)
            if task_logger is not None:
                task_logger.add_log("Not authorized")
            return False

        # Check if the response status is 404 (Not Found)
        if response.status_code == 404:
            print("File not found:", url)
            if task_logger is not None:
                task_logger.add_log("File not found")
            return False

        response.raise_for_status()  # Raise an exception for bad status codes

        # Save the file to the specified path
        file_path = os.path.join(destination_folder, filename)
        with open(file_path, 'wb') as file:
            file.write(response.content)

        print("File downloaded successfully:", file_path)
        return True
    except Exception as e:
        task_logger.add_log("Error downloading file")
        print("Error downloading file:", e)
        return False


def download_secure_file(url, destination_folder, filename, headers=None, task_logger: TaskWrapper = None):
    """
    Download a file from the given URL and save it to the specified path with the given filename.

    Args:
    url (str): The URL of the file to download.
    destination_folder (str): The path of the folder where the file will be saved.
    filename (str): The name of the file.

    Returns:
    bool: True if the download was successful, False otherwise.
    """
    if headers is None:
        headers = {}
    try:
        # Create destination folder if it doesn't exist
        os.makedirs(destination_folder, exist_ok=True)
        file_path = os.path.join(destination_folder, filename)
        if custom_curl_get(url, headers, file_path, task_logger):
            return True
    except Exception as e:
        task_logger.critical(f'Error downloading file {url}')
        return False


def download_secure_text(url, headers=None, task_logger: TaskWrapper = None):
    """
    Download a text-based file from the given URL and return the text

    Args:
    url (str): The URL of the file to download.
    destination_folder (str): The path of the folder where the file will be saved.
    filename (str): The name of the file.

    Returns:
    bool: True if the download was successful, False otherwise.
    """
    if headers is None:
        headers = {}

    # Get a temporary file path
    temp_file_path = tempfile.mktemp()

    try:
        if custom_curl_get(url, headers, temp_file_path, task_logger):
            return read_temp_file(temp_file_path)
    except Exception as e:
        if task_logger is not None:
            task_logger.add_log(f'Error downloading file {url}')
        return False
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def download_secure_text_post(url, headers=None, task_logger: TaskWrapper = None):
    """
    Download a text-based file from the given URL and return the text

    Args:
    url (str): The URL of the file to download.
    destination_folder (str): The path of the folder where the file will be saved.
    filename (str): The name of the file.

    Returns:
    bool: True if the download was successful, False otherwise.
    """
    if headers is None:
        headers = {}

    # Get a temporary file path
    temp_file_path = tempfile.mktemp()

    try:
        if custom_curl_post(url, None, headers, temp_file_path, task_logger):
            return read_temp_file(temp_file_path)
    except Exception as e:
        if task_logger is not None:
            task_logger.add_log(f'Error downloading file {url}')
        return False
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def download_secure_header_get(url, headers=None, task_logger: TaskWrapper = None):
    """
    Download a text-based file from the given URL and return the text

    Args:
    url (str): The URL of the file to download.
    destination_folder (str): The path of the folder where the file will be saved.
    filename (str): The name of the file.

    Returns:
    bool: True if the download was successful, False otherwise.
    """
    if headers is None:
        headers = {}

    # Get a temporary file path
    temp_file_path = tempfile.mktemp()

    try:
        if custom_curl_headers(url, headers, temp_file_path, task_logger):
            return read_temp_file(temp_file_path)
    except Exception as e:
        if task_logger is not None:
            task_logger.add_log(f'Error downloading file {url}')
        return False
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def download_html(url):
    """
    Downloads HTML content from the specified URL.

    Args:
    url (str): The URL of the webpage to download.

    Returns:
    str: The HTML content of the webpage.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.text
    except requests.exceptions.RequestException as e:
        print("Error downloading HTML:", e)
        return None


def parse_html(html_content):
    """
    Parses HTML content and returns a BeautifulSoup object.

    Args:
    html_content (str): The HTML content to parse.

    Returns:
    BeautifulSoup object: Parsed HTML content.
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        return soup
    except Exception as e:
        print("Error parsing HTML:", e)
        return None


def ensure_trailing_slash(url):
    if not url.endswith('/'):
        url += '/'
    return url


def remove_trailing_slash(s: str) -> str:
    if s.endswith('/'):
        return s[:-1]
    return s


def get_base_url(url):
    parsed_url = urlparse(url)
    # Reassemble the base URL with scheme and domain
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"
    return base_url

def get_authority_url(url):
    parsed_url = urlparse(url)
    # Reassemble the base URL with scheme and domain
    base_url = f"{parsed_url.netloc}"
    return base_url

def replace_url_ending(url, new_part):
    return "/".join(url.rsplit("/", 1)[:-1]) + "/" + new_part

def get_headers_when_empty(headers, url, task_wrapper: TaskWrapper, alt_url: str = None):
    if headers is not None:
        return headers

    if not os.path.exists('headers.json'):
        task_wrapper.critical(f"File headers.json does not exist.")
        return False

    return get_headers(url, True, task_wrapper, False, alt_url)

def has_valid_headers():
    file_path = './headers.json'

    if not os.path.exists(file_path):
        return False

    # Get the last modification time of the file
    modified_time = datetime.fromtimestamp(os.path.getmtime(file_path))

    # Calculate the time 2 hours ago
    time_limit = datetime.now() - timedelta(hours=8)

    return modified_time >= time_limit

def get_headers(url: str, is_page: bool, task_wrapper: TaskWrapper, test: bool = False, alt_url: str = None, ignore_errors: bool = False) -> \
        Optional[dict[str, str]]:
    """
    Get the headers from the headers.json file and return them as a dictionary.

    Args:
    url (str): URL of the page or media to obtain.
    is_page (bool): True if the URL is for a page, False if it is for media.
    task_wrapper (TaskWrapper): TaskWrapper object for logging.
    test (bool): True if running in test mode, False otherwise.
    alt_url (str): Alternative URL to use as the referer. Default is None.

    Returns:
    Optional[dict[str, str]]: Dictionary containing the headers, or None if an error occurs.
    """

    file_path = './headers.json'
    if test:
        file_path = '../headers.json'

    if not os.path.exists(file_path):
        # Look up one folder
        file_path = '../headers.json'

    with open(file_path, 'r') as file:
        try:
            headers = json.load(file)

            if is_page:
                headers["accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
            else:
                headers["accept"] = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
            headers["Accept-Encoding"] = "gzip, deflate, br, zstd"

            # Use alt_url if provided, otherwise use url
            referer_url = alt_url if alt_url and len(alt_url) > 0 else url

            if task_wrapper is not None and task_wrapper.can_trace():
                task_wrapper.trace(f'referer_url: {referer_url}')
                task_wrapper.trace(f'cleaned_referer_url: {get_base_url(referer_url)}')

            headers["referer"] = get_base_url(referer_url)
            headers["authority"] = get_authority_url(referer_url)

            return headers
        except json.JSONDecodeError:
            task_wrapper.error(f"Failed to load JSON from headers.json.")
            if not ignore_errors:
                task_wrapper.set_failure(True)
            return None


def guess_file_extension(url: str) -> str:
    # Extract the path from the URL
    path = urlparse(url).path

    # Guess the MIME type based on the URL's path
    mime_type, _ = mimetypes.guess_type(path)

    # Mapping of MIME types to extensions
    valid_extensions = {"image/webp": "webp", "image/jpeg": "jpeg", "image/jpg": "jpg", "image/png": "png"}

    # Return the guessed extension or default to 'jpg'
    return valid_extensions.get(mime_type, "jpg")