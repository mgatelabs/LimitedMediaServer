import argparse
import mimetypes
import os.path
import shutil
import subprocess
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_MEDIA
from file_utils import temporary_folder
from media_queries import find_folder_by_id, insert_file
from media_utils import get_data_for_mediafile
from plugin_system import ActionMediaFolderPlugin, plugin_string_arg
from text_utils import is_blank
from thread_utils import TaskWrapper


def extract_query_variable(url, variable_name):
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    if variable_name in query_params:
        return query_params[variable_name][0]  # Return the first value if multiple values are present
    else:
        return None  # Variable not found

class DownloadFromYtTask(ActionMediaFolderPlugin):
    """
    Download from YTube
    """

    def __init__(self):
        super().__init__()

    def get_sort(self):
        return {'id': 'media_dl.yt', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Save Video from YT'

    def get_action_id(self):
        return 'action.download.yt'

    def get_action_icon(self):
        return 'download'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(
            plugin_string_arg('URL', 'url', 'The youtube link to a video.  It should have ?v= in the string.')
        )

        result.append({
            "name": "Destination?",
            "id": "dest",
            "description": "Where should these files be stored?",
            "type": "select",
            "default": "primary",
            "values": [{"id": 'primary', "name": 'Primary Disk'}, {"id": 'archive', "name": 'Archive Disk'}]
        })

        return result

    def process_action_args(self, args):
        results = []

        if 'url' not in args or args['url'] is None or args['url'] == '':
            results.append('url is required')
        else:
            if args['url'].startswith('https://'):
                v = extract_query_variable(args['url'], 'v')
                args['url'] = v

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
        return DownloadYt("Download YT", 'Downloading from YT ' + args['url'], args['folder_id'], args['url'], args['dest'], self.primary_path,
                          self.archive_path, self.temp_path)


class DownloadYt(TaskWrapper):
    def __init__(self, name, description, folder_id, video, dest, primary_path, archive_path, temp_path):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.video = video
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

            arguments = ['-S', "res,ext:mp4:m4a", '--recode', 'mp4', '--embed-thumbnail',
                         'https://www.youtube.com/?v=' + self.video]

            # Run the program with the provided arguments
            process = subprocess.Popen(['yt-dlp'] + arguments, cwd=temp_folder)

            # Wait for the process to finish
            process.wait()

            return_code = str(process.returncode)

            if return_code == '0':
                self.set_worked()

                for item in os.listdir(temp_folder):
                    # Get the full path
                    item_full_path = os.path.join(temp_folder, item)

                    # Check if it is a file (not a directory)
                    if os.path.isfile(item_full_path):
                        # Get file size
                        file_size = os.path.getsize(item_full_path)

                        # Get created time and convert to readable format
                        created_time = os.path.getctime(item_full_path)
                        created_datetime = datetime.fromtimestamp(created_time)

                        mime_type, _ = mimetypes.guess_type(item_full_path)  # MIME type

                        if mime_type is not None:

                            new_file = insert_file(source_row.id, str(item), mime_type, is_archive, False, file_size,
                                                   created_datetime, db_session)

                            dest_path = get_data_for_mediafile(new_file, self.primary_path, self.archive_path)

                            shutil.move(str(item_full_path), str(dest_path))

                        else:
                            self.warn(f'Ignoring file {item}, unknown MIME TYPE')
            else:
                self.error(f'Return Code {return_code}')
                self.set_failure()
