import argparse
import os.path
import shutil
import subprocess
from datetime import date as date_type, datetime
import shlex

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_MEDIA
from file_utils import is_valid_url, temporary_folder
from html_utils import get_base_url, get_headers
from media_queries import find_folder_by_id, insert_file
from media_utils import get_data_for_mediafile
from plugin_system import ActionMediaFolderPlugin
from plugin_methods import plugin_filename_arg, plugin_url_arg, plugin_select_arg, plugin_select_values
from text_utils import is_blank
from thread_utils import TaskWrapper
from utility import random_sleep


class DownloadM3u8Plugin(ActionMediaFolderPlugin):
    """
    Download from YTube
    """
    AI_QUICK_DESCRIPTION = ('Downloads an HLS (M3U8) video stream with ffmpeg into an MP4 file '
                            'in a media folder, without re-encoding.')
    AI_LONG_DESCRIPTION = (
        'Fetches an HLS (.m3u8) live or VOD stream straight from its .m3u8 URL and records it '
        'into an MP4 container using ffmpeg in stream-copy mode, so the video is never '
        're-encoded and quality is preserved. The download is written to a temporary file '
        'first; if ffmpeg fails or the result is zero bytes the task is marked as failed '
        'without touching the media folder. On success the file is registered as '
        'video/mp4, moved into storage on the chosen disk (Primary or Archive, default '
        'Primary), and the media folder\'s last-access date is recorded. Required arguments: '
        'URL (the link to the .m3u8 manifest) and Filename. Location is optional.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'dlm3u8'

    def get_sort(self):
        return {'id': 'media_dl.m3u8', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Save Video from M3u8'

    def get_action_id(self):
        return 'action.download.m3u8'

    def get_action_icon(self):
        return 'download'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(
            plugin_select_arg('Location', 'dest', 'primary',
                              plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'), '', 'media')
        )

        result.append(
            plugin_filename_arg('Filename', 'filename', 'The name of the file.')
        )

        result.append(
            plugin_url_arg('URL', 'url', 'The link to the m3u8 file.', "", "yes", "url")
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

        if len(results) > 0:
            return results
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        filename = args['filename']
        return DownloadM3u8Job("Download M3u8", f'Downloading {filename} from M3u8 to folder ' + args['folder_id'], args['folder_id'], filename, args['url'],
                               args['dest'], self.primary_path,
                               self.archive_path, self.temp_path)


class DownloadM3u8Job(TaskWrapper):
    def __init__(self, name, description, folder_id, filename, url, dest, primary_path, archive_path, temp_path):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.filename = filename
        self.url = url
        self.dest = dest
        self.primary_path = primary_path
        self.archive_path = archive_path
        self.temp_path = temp_path
        self.ref_folder_id = folder_id

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

            temp_file = os.path.join(temp_folder, 'download.mp4')

            url_list = [u.strip() for u in self.url.split(';') if u.strip()]

            if not url_list:
                self.error('Could not download m3u8')
                self.set_failure()
                return

            success = False
            for index, stream_url in enumerate(url_list):

                if index > 0:
                    self.warn(f'File failed to download, trying alternative source: {index + 1}/{len(url_list)}')
                    random_sleep(12, 12, self)

                    if os.path.exists(temp_file):
                        try:
                            os.remove(temp_file)
                        except OSError:
                            pass

                arguments = ['ffmpeg', '-nostdin', '-i', stream_url, '-c', 'copy', temp_file]

                headers = get_headers(stream_url, False, self, False, get_base_url(stream_url), True)

                if headers:
                    for key, value in headers.items():
                        arguments.extend(['-headers', f'{key}: {value}'])

                if self.can_trace():
                    command_str = shlex.join(arguments)
                    self.trace(command_str)

                # Run the program with the provided arguments
                process = subprocess.Popen(arguments, cwd=temp_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                # Wait for the process to finish
                stdout, stderr = process.communicate()  # Capture the output and error streams

                return_code = str(process.returncode)

                if return_code != '0':
                    self.error(f'Return Code {return_code}')

                    error_text = stderr.decode('utf-8')
                    self.error(error_text)
                    continue

                if not (os.path.exists(temp_file) and os.path.isfile(temp_file) and os.path.getsize(temp_file) > 0):
                    self.error('Could not locate downloaded file')
                    continue

                self.url = stream_url
                success = True
                break

            if not success:
                self.set_failure()
                return

            self.set_worked()

            # Get file size
            file_size = os.path.getsize(temp_file)

            self.info(f'Found file with size {file_size}')

            # Get created time and convert to readable format
            created_time = os.path.getctime(temp_file)
            created_datetime = datetime.fromtimestamp(created_time)

            mime_type = 'video/mp4'  # MIME type

            new_file = insert_file(source_row.id, self.filename, mime_type, is_archive, False, file_size,
                                   created_datetime, db_session)

            dest_path = get_data_for_mediafile(new_file, self.primary_path, self.archive_path)

            shutil.move(str(temp_file), str(dest_path))

            source_row.last_date = date_type.today()
            db_session.commit()
