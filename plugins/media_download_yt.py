from datetime import date as date_type
import argparse
import os.path
import subprocess

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_MEDIA
from file_utils import temporary_folder
from media_queries import find_folder_by_id
from media_utils import ingest_file
from plugin_methods import plugin_url_arg
from plugin_system import ActionMediaFolderPlugin
from text_utils import is_blank
from thread_utils import TaskWrapper


class DownloadYtPlugin(ActionMediaFolderPlugin):
    """
    Download from YTube
    """
    AI_QUICK_DESCRIPTION = ('Downloads a video (or playlist/page) with yt-dlp, recodes it to MP4 '
                            'with the thumbnail embedded, and ingests the result into a media folder.')
    AI_LONG_DESCRIPTION = (
        'Uses the yt-dlp command-line tool to download a video - a single video link, a playlist, '
        'or a page - into a temporary folder and then ingests each produced file into the chosen '
        'media folder. The download is forced to MP4/M4A (yt-dlp "-S res,ext:mp4:m4a" "--recode '
        'mp4") and the video\'s thumbnail is embedded. Every file written into the temp folder is '
        'registered in the database (guessed MIME type) and moved into storage on the chosen '
        'disk (Primary or Archive, default Primary); files with an unknown MIME type are skipped '
        'with a warning. Requires the yt-dlp executable to be installed and reachable on PATH '
        'plus an ffmpeg codec for the recode. Required argument: URL. Destination is optional '
        'with a default of Primary Disk.')

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
            plugin_url_arg('URL', 'url', 'Link to the video, playlist, page.', clear_after='yes')
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
        return DownloadYtJob("Download YT", 'Downloading from YT ' + args['url'], args['folder_id'], args['url'],
                             args['dest'], self.primary_path,
                             self.archive_path, self.temp_path)


class DownloadYtJob(TaskWrapper):
    def __init__(self, name, description, folder_id, video, dest, primary_path, archive_path, temp_path):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.video = video
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

            arguments = ['-S', "res,ext:mp4:m4a", '--recode', 'mp4', '--embed-thumbnail',
                         self.video]

            # Run the program with the provided arguments
            process = subprocess.Popen(['yt-dlp'] + arguments, cwd=temp_folder)

            # Wait for the process to finish
            process.wait()

            return_code = str(process.returncode)

            if return_code == '0' or return_code == '1':
                self.set_worked()

                possible_filenames = os.listdir(temp_folder)

                by_video_lookup = {'*': possible_filenames}

                for video_key, sample_list in by_video_lookup.items():

                    for item in sample_list:

                        # Get the full path
                        item_full_path = os.path.join(temp_folder, item)

                        if ingest_file(item_full_path, item, source_row.id, is_archive, self.primary_path,
                                       self.archive_path, db_session, self):
                            if self.can_debug():
                                self.debug(f'Ingested: {item}')

                source_row.last_date = date_type.today()
                db_session.commit()

            else:
                self.error(f'Return Code {return_code}')
                self.set_failure()
