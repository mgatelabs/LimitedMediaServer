import argparse
import logging
import os
import shutil
from typing import Optional

from flask_sqlalchemy.session import Session

from db import MediaFile
from feature_flags import MANAGE_MEDIA
from ffmpeg_utils import get_media_info
from media_utils import get_data_for_mediafile, \
    get_file_by_user
from plugin_system import ActionMediaFilePlugin
from text_utils import is_not_blank, is_blank
from thread_utils import TaskWrapper


class MediaInfoForFilePlugin(ActionMediaFilePlugin):
    """
    Subtitle a file using FFMPEG
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'medinfo'

    def get_sort(self):
        return {'id': 'media_file_info', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Media Info'

    def get_action_id(self):
        return 'action.file.info'

    def get_action_icon(self):
        return 'title'

    def get_action_args(self):
        result = super().get_action_args()

        return result

    def process_action_args(self, args):
        results = []

        if len(results) > 0:
            return results
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        return MediaInfoJob("MediaInfo", 'Info: ' + args['file_id'], args['file_id'], self.primary_path,
                            self.archive_path,
                            self.temp_path)


class MediaInfoJob(TaskWrapper):
    def __init__(self, name, description, file_id: Optional[str], primary_folder: str, archive_folder: str,
                 temp_folder: str):
        super().__init__(name, description)
        self.file_id = file_id
        self.primary_folder = primary_folder
        self.archive_folder = archive_folder
        self.temp_folder = temp_folder

    def run(self, db_session: Session):

        # Sanity Check
        if is_blank(self.primary_folder) or is_blank(self.archive_folder) or is_blank(self.temp_folder):
            self.critical('This feature is not ready.  Please configure the app properties and restart the server.')

        to_process: list[MediaFile] = []

        if self.file_id is not None:
            try:
                if self.can_trace():
                    self.trace('File Logic')

                file_row, folder_row = get_file_by_user(self.file_id, self.user, db_session)

                if file_row.mime_type.startswith('video/'):
                    to_process.append(file_row)
                else:
                    self.error(f'Given file mime-type {file_row.mime_type} is not a video')

            except ValueError as ve:
                logging.exception(ve)
                self.error(str(ve))
                self.set_failure()
                return
        else:
            self.set_failure()
            self.error('Invalid run configuration')
            return

        if len(to_process) == 0:
            self.set_failure()
            self.error('No files to process')
            return

        temp_folder = ''
        try:

            total_files = len(to_process)
            index = 0
            for file in to_process:

                if self.is_cancelled:
                    self.info('Leaving Early')
                    return

                index = index + 1

                self.update_progress((index / total_files) * 100.0)

                source_file = get_data_for_mediafile(file, self.primary_folder, self.archive_folder)

                get_media_info(source_file, self)

        finally:
            if is_not_blank(temp_folder) and os.path.exists(temp_folder):
                shutil.rmtree(temp_folder)
