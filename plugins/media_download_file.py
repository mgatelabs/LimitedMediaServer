import argparse
import logging
import mimetypes
import os.path
import platform
import shutil
from datetime import datetime

import requests
from flask_sqlalchemy.session import Session

from curl_utils import custom_curl_get
from feature_flags import MANAGE_MEDIA
from file_utils import is_valid_url, temporary_folder
from html_utils import get_headers, get_base_url
from media_queries import find_folder_by_id, insert_file
from media_utils import get_data_for_mediafile
from plugin_methods import plugin_filename_arg, plugin_url_arg, plugin_select_arg, plugin_select_values
from plugin_system import ActionMediaFolderPlugin
from text_utils import is_blank
from thread_utils import TaskWrapper


class DownloadFilePlugin(ActionMediaFolderPlugin):
    """
    Download from YTube
    """

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
            plugin_url_arg('URL', 'url', 'The link to the file to grab.', clear_after="yes", arg1="url")
        )

        result.append(
            plugin_filename_arg('Filename', 'filename', 'The name of the file.')
        )

        # result.append(plugin_select_arg('Send Headers', 'headers', 'n', PLUGIN_VALUES_Y_N, 'Send headers with command?'))

        result.append(
            plugin_select_arg('Location', 'dest', 'primary',
                              plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'), '', 'media', adv='Y')
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
                               args['folder_id'], filename, args['url'],
                               args['dest'], args['meth'], self.primary_path,
                               self.archive_path, self.temp_path)


class DownloadFileJob(TaskWrapper):
    def __init__(self, name, description, folder_id, filename, url, dest, meth, primary_path, archive_path, temp_path):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.filename = filename
        self.url = url
        self.dest = dest
        self.meth = meth
        self.primary_path = primary_path
        self.archive_path = archive_path
        self.temp_path = temp_path
        self.ref_folder_id = folder_id

    def get_gcurl_file(self, file_url: str, local_path: str):
        headers = get_headers(file_url, False, self, False, get_base_url(file_url))
        return custom_curl_get(file_url, headers, local_path, self, True)

    def get_system_file(self, file_url: str, local_path: str):
        try:
            # Send a GET request to the file URL
            headers = get_headers(file_url, False, self, False, get_base_url(file_url))
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

        is_archive = self.dest == 'archive'

        with temporary_folder(self.temp_path, self) as temp_folder:

            temp_file = os.path.join(temp_folder, 'download.text')

            if self.meth == 'gcurl':
                self.trace('Before Curl Download')
                if not self.get_gcurl_file(self.url, temp_file):
                    self.error('Could not download file')
                    self.set_failure()
                    return
            elif self.meth == 'system':
                self.trace('Before System Download')
                if not self.get_system_file(self.url, temp_file):
                    self.error('Could not download file')
                    self.set_failure()
                    return
            else:
                self.error('Unknown request method')
                self.set_failure()

            if os.path.exists(temp_file) and os.path.isfile(temp_file):

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
                else:
                    self.error('Zero length file, skipping')
                    self.set_failure()
            else:
                self.error('Could not locate downloaded file')
                self.set_failure()
