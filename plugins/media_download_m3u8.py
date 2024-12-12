import argparse
import os.path
import shutil
import subprocess
from datetime import datetime

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_MEDIA
from file_utils import is_valid_url, temporary_folder
from media_queries import find_folder_by_id, insert_file
from media_utils import get_data_for_mediafile
from plugin_system import ActionMediaFolderPlugin, plugin_url_arg, plugin_select_arg, \
    plugin_select_values, plugin_filename_arg
from text_utils import is_blank
from thread_utils import TaskWrapper


class DownloadFromM3u8Task(ActionMediaFolderPlugin):
    """
    Download from YTube
    """

    def __init__(self):
        super().__init__()

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
            plugin_url_arg('URL', 'url', 'The link to the m3u8 file.')
        )

        result.append(
            plugin_filename_arg('Filename', 'filename', 'The name of the file.')
        )

        #result.append(plugin_select_arg('Send Headers', 'headers', 'n', PLUGIN_VALUES_Y_N, 'Send headers with command?'))

        result.append(
            plugin_select_arg('Description', 'dest', 'primary',
                              plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'))
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
        return DownloadM3u8("Download M3u8", f'Downloading {filename} from M3u8 to folder ' + args['folder_id'], args['folder_id'], filename, args['url'],
                            args['dest'], self.primary_path,
                            self.archive_path, self.temp_path)


class DownloadM3u8(TaskWrapper):
    def __init__(self, name, description, folder_id, filename, url, dest, primary_path, archive_path, temp_path):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.filename = filename
        self.url = url
        self.dest = dest
        self.primary_path = primary_path
        self.archive_path = archive_path
        self.temp_path = temp_path

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

            arguments = ['-nostdin', '-i', self.url, '-c', 'copy', temp_file]

            # Run the program with the provided arguments
            process = subprocess.Popen(['ffmpeg'] + arguments, cwd=temp_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Wait for the process to finish
            stdout, stderr = process.communicate()  # Capture the output and error streams

            return_code = str(process.returncode)

            if return_code == '0':
                self.set_worked()

                if os.path.exists(temp_file) and os.path.isfile(temp_file):

                    # Get file size
                    file_size = os.path.getsize(temp_file)

                    if file_size > 0:

                        # Get created time and convert to readable format
                        created_time = os.path.getctime(temp_file)
                        created_datetime = datetime.fromtimestamp(created_time)

                        mime_type = 'video/mp4'  # MIME type

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

            else:
                self.error(f'Return Code {return_code}')

                error_text = stderr.decode('utf-8')
                self.error(error_text)

                self.set_failure()
