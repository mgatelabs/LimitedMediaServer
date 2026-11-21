import argparse
import logging
import mimetypes
import os.path
import platform
import shutil
from datetime import date as date_type, datetime

import requests
from flask_sqlalchemy.session import Session

from curl_utils import custom_curl_get, is_cloudflare_block
from feature_flags import MANAGE_MEDIA
from file_utils import is_valid_url, temporary_folder
from html_utils import get_headers, get_base_url
from media_queries import find_folder_by_id, insert_file
from media_utils import get_data_for_mediafile
from plugin_methods import plugin_filename_arg, plugin_url_arg, plugin_select_arg, plugin_select_values
from plugin_system import ActionMediaFolderPlugin
from text_utils import is_blank
from thread_utils import TaskWrapper
from utility import random_sleep


class DownloadFilePlugin(ActionMediaFolderPlugin):
    """
    Download from YTube
    """
    AI_QUICK_DESCRIPTION = ('Downloads a single file from a direct web URL and saves it into a '
                            'media folder as a registered media file.')
    AI_LONG_DESCRIPTION = (
        'Fetches one file from a direct URL (not a video or audio streaming service) and adds '
        'it to the chosen media folder. The download is written to a temporary file first - '
        'using either the system HTTP downloader (default) or, on Linux, the Google Curl '
        'downloader - then checked: Cloudflare anti-bot blocks and zero-length downloads are '
        'rejected. On success the file is registered in the database with a guessed MIME type, '
        'moved into storage on the chosen disk (Primary or Archive, default Primary), and the '
        'folder\'s last-access date is bumped. Required arguments: URL, Filename, and Origin '
        '(the referring page sent as the Origin header). Location and Method are optional with '
        'defaults.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'dlfile'

    def get_sort(self):
        return {'id': 'media_dl.file', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Save File from Web'

    def get_action_id(self):
        return 'action.download.file'

    def get_action_icon(self):
        return 'download'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(
            plugin_url_arg('URL', 'url', 'The link to the file to grab.', '', "yes", "url", 'origin', 'Origin')
        )

        result.append(
            plugin_filename_arg('Filename', 'filename', 'The name of the file.')
        )

        result.append(
            plugin_select_arg('Location', 'dest', 'primary',
                              plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'), '', 'media', adv='Y')
        )

        result.append(
            plugin_url_arg('Origin', 'origin', 'The origin for the Url.', '', 'no', "Origin")
        )

        if platform.system() != 'Linux':
            download_options = plugin_select_values('Default Downloader', 'system')
        else:
            download_options = plugin_select_values('Default Downloader', 'system', 'Google Curl Downloader', 'gcurl')

        result.append(
            plugin_select_arg('Method', 'meth', 'system', download_options, 'Which download subsystem to use?', adv='Y')
        )

        return result

    def process_action_args(self, args):
        results = []

        if 'url' not in args or args['url'] is None or args['url'] == '':
            results.append('url is required')

        if 'origin' not in args or args['origin'] is None or args['origin'] == '':
            results.append('origin is required')

        if 'filename' not in args or args['filename'] is None or args['filename'] == '':
            results.append('filename is required')

        if not is_valid_url(args['url']):
            results.append('url is not valid')

        if 'dest' not in args or is_blank(args['dest']):
            results.append('dest is required')
        elif not (args['dest'] == 'primary' or args['dest'] == 'archive'):
            results.append('Invalid dest value')

        if 'meth' not in args or is_blank(args['meth']):
            results.append('meth is required')
        elif not (args['meth'] == 'system' or args['meth'] == 'gcurl'):
            results.append('Invalid meth value')

        if len(results) > 0:
            return results
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        filename = args['filename']
        return DownloadFileJob("Download File", f'Downloading {filename} from Web to folder ' + args['folder_id'],
                               args['folder_id'], filename, args['url'], args['origin'].strip(), args['dest'],
                               args['meth'], self.primary_path, self.archive_path, self.temp_path)


class DownloadFileJob(TaskWrapper):
    def __init__(self, name, description, folder_id, filename, url, origin, dest, meth, primary_path, archive_path,
                  temp_path, priority_override = 0):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.filename = filename
        url_list = [u.strip() for u in (url or '').split(';') if u.strip()]
        origin_list = [o.strip() for o in (origin or '').split(';')] if origin else []
        while len(origin_list) < len(url_list):
            origin_list.append('')
        self.url = ';'.join(url_list)
        self.origin = ';'.join(origin_list)
        self.dest = dest
        self.meth = meth
        self.priority = priority_override
        self.primary_path = primary_path
        self.archive_path = archive_path
        self.temp_path = temp_path
        self.ref_folder_id = folder_id

    def get_gcurl_file(self, file_url: str, local_path: str):
        headers = get_headers(file_url, False, self, False, self.origin)
        return custom_curl_get(file_url, headers, local_path, self, True)

    def get_system_file(self, file_url: str, local_path: str):
        try:
            # Send a GET request to the file URL
            headers = get_headers(file_url, False, self, False, self.origin)
            with requests.get(file_url, stream=True, headers=headers) as response:
                response.raise_for_status()  # Raise an error for HTTP requests with a bad status code
                # Open the local file in write-binary mode
                with open(local_path, 'wb') as file:
                    # Write the response content to the file in chunks
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:  # Filter out keep-alive new chunks
                            file.write(chunk)
            # print(f"File downloaded successfully and saved to {local_path}")
            return True
        except requests.exceptions.RequestException as e:
            # print(f"An error occurred: {e}")
            logging.exception(e)
            return False

    def run(self, db_session: Session):

        if is_blank(self.primary_path) or is_blank(self.archive_path) or is_blank(self.temp_path):
            self.critical('This feature is not ready.  Please configure the app properties and restart the server.')

        source_row = find_folder_by_id(self.folder_id, db_session)
        if source_row is None:
            self.critical('Source Folder not found')
            self.set_failure()
            return

        self.ref_folder_name = source_row.name if hasattr(source_row, 'name') else str(source_row.id)
        self.ref_folder_preview = source_row.preview == True

        is_archive = self.dest == 'archive'

        with temporary_folder(self.temp_path, self) as temp_folder:

            temp_file = os.path.join(temp_folder, 'download.text')

            url_list = [u.strip() for u in self.url.split(';') if u.strip()]
            origin_list = [o.strip() for o in self.origin.split(';')] if self.origin else []
            while len(origin_list) < len(url_list):
                origin_list.append('')

            if not url_list:
                self.error('Could not download file')
                self.set_failure()
                return

            if self.meth not in ('gcurl', 'system'):
                self.error('Unknown request method')
                self.set_failure()
                return

            success = False
            for index, (file_url, file_origin) in enumerate(zip(url_list, origin_list)):
                if file_origin and not is_valid_url(file_origin):
                    file_origin = file_url

                self.origin = file_origin

                if index > 0:
                    self.warn(f'File failed to download, trying alternative source: {index + 1}/{len(url_list)}')
                    random_sleep(12, 12, self)

                self.trace(f"Before {'Curl' if self.meth == 'gcurl' else 'System'} Download: {file_url}")
                if self.meth == 'gcurl':
                    success = self.get_gcurl_file(file_url, temp_file)
                else:
                    success = self.get_system_file(file_url, temp_file)

                if success and os.path.exists(temp_file) and os.path.isfile(temp_file) \
                        and not is_cloudflare_block(temp_file) and os.path.getsize(temp_file) > 0:
                    break

                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except OSError:
                        pass

            if not success:
                self.error('Could not download file')
                self.set_failure()
                return

            if os.path.exists(temp_file) and os.path.isfile(temp_file):

                if is_cloudflare_block(temp_file):
                    self.error('Cloudflare block detected in downloaded file (403 equivalent)')
                    self.set_failure()
                    return

                self.set_worked()

                # Get file size
                file_size = os.path.getsize(temp_file)

                if file_size > 0:

                    # Get created time and convert to readable format
                    created_time = os.path.getctime(temp_file)
                    created_datetime = datetime.fromtimestamp(created_time)

                    mime_type, _ = mimetypes.guess_type(self.filename)  # MIME type

                    # If MIME type couldn't be guessed, skip the file
                    if mime_type is None:
                        self.error(f"{self.filename}: MIME type couldn't be determined")
                        self.set_failure()
                        return

                    new_file = insert_file(source_row.id, self.filename, mime_type, is_archive, False, file_size,
                                           created_datetime, db_session)

                    dest_path = get_data_for_mediafile(new_file, self.primary_path, self.archive_path)

                    shutil.move(str(temp_file), str(dest_path))

                    source_row.last_date = date_type.today()
                    db_session.commit()
                else:
                    self.error('Zero length file, skipping')
                    self.set_failure()
            else:
                self.error('Could not locate downloaded file')
                self.set_failure()
