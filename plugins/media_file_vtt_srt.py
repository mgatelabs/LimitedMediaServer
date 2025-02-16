import argparse
import logging
import mimetypes
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask_sqlalchemy.session import Session

from constants import MAX_WORKERS
from db import MediaFile, MediaFolder
from feature_flags import MANAGE_MEDIA
from ffmpeg_utils import FFMPEG_PRESET, FFMPEG_PRESET_VALUES, FFMPEG_CRF, FFMPEG_CRF_VALUES, \
    get_ffmpeg_f_argument_from_mimetype, burn_subtitles_to_video, FFMPEG_AUDIO_BIT, FFMPEG_AUDIO_BIT_RATE_VALUES, \
    FFMPEG_STEREO, FFMPEG_STEREO_VALUES
from file_utils import temporary_folder
from media_queries import insert_file, find_file_by_filename, find_files_in_folder
from media_utils import get_data_for_mediafile, \
    get_filename_with_extension, convert_vtt_to_srt, get_folder_by_user, get_file_by_user, describe_file_size_change
from number_utils import is_integer_with_sign
from plugin_methods import plugin_string_arg
from plugin_system import ActionMediaFilePlugin, ActionMediaFolderPlugin, ActionMediaFilesPlugin
from text_utils import is_not_blank, is_blank, clean_string
from thread_utils import TaskWrapper


class Vtt2SrtForFilePlugin(ActionMediaFilePlugin):
    """
    Subtitle a file using FFMPEG
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'vtt2srt'

    def get_sort(self):
        return {'id': 'media_file_vrt_srt', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'VTT to SRT'

    def get_action_id(self):
        return 'action.file.vrt2str'

    def get_action_icon(self):
        return 'title'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(plugin_string_arg('Offset', 'offset', 'Subtitle Offset in seconds'))

        return result

    def process_action_args(self, args):
        results = []

        if 'offset' not in args or is_blank(args['offset']):
            args['offset'] = 0
        else:
            args['offset'] = clean_string(args['offset'])

            if not is_integer_with_sign(args['offset']):
                results.append('offset is not a valid integer')

        if len(results) > 0:
            return results
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        return Vtt2SrtJob("Vtt2Srt", 'Fixing: ' + args['file_id'], args['file_id'], self.primary_path, self.archive_path,
                           self.temp_path, int(args['offset']))

class Vtt2SrtForFilesPlugin(ActionMediaFilesPlugin):
    """
    Subtitle a file using FFMPEG
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'vtt2srt'

    def get_sort(self):
        return {'id': 'media_file_vrt_srt', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'VTT to SRT'

    def get_action_id(self):
        return 'action.files.vrt2str'

    def get_action_icon(self):
        return 'title'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(plugin_string_arg('Offset', 'offset', 'Subtitle Offset in seconds'))

        return result

    def process_action_args(self, args):
        results = []

        if 'offset' not in args or is_blank(args['offset']):
            args['offset'] = 0
        else:
            args['offset'] = clean_string(args['offset'])

            if not is_integer_with_sign(args['offset']):
                results.append('offset is not a valid integer')

        if len(results) > 0:
            return results
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        return Vtt2SrtJob("Vtt2Srt", 'Fixing: ' + args['file_id'], args['file_id'], self.primary_path, self.archive_path,
                           self.temp_path, int(args['offset'], True))



class Vtt2SrtJob(TaskWrapper):
    def __init__(self, name, description, file_id: Optional[str], primary_folder: str, archive_folder: str, temp_folder: str, offset:int = 0, multiple_files: bool = False):
        super().__init__(name, description)
        self.file_id = file_id
        self.primary_folder = primary_folder
        self.archive_folder = archive_folder
        self.temp_folder = temp_folder
        self.weight = 10
        self.offset = offset
        self.multiple_files = multiple_files

    def find_subtitle_for_file(self, file: MediaFile, temp_folder: str, offset: int = 0) -> \
    Optional[str]:

            vtt_file = get_data_for_mediafile(file, self.primary_folder, self.archive_folder)
            srt_file = os.path.join(temp_folder, 'temp.srt')
            if not convert_vtt_to_srt(vtt_file, srt_file, offset):
                self.set_failure()
                self.error('Could not convert VTT file to SRT')
                return None
            else:
                return srt_file

    def run(self, db_session: Session):

        # Sanity Check
        if is_blank(self.primary_folder) or is_blank(self.archive_folder) or is_blank(self.temp_folder):
            self.critical('This feature is not ready.  Please configure the app properties and restart the server.')

        to_process: list[MediaFile] = []

        if self.file_id is not None:
            try:
                if self.can_trace():
                    self.trace('File Logic')

                if self.multiple_files:
                    file_list = self.file_id.split(",")
                    for file in file_list:
                        file_row, folder_row = get_file_by_user(file, self.user, db_session)

                        if file_row.mime_type.startswith('text/vtt'):
                            to_process.append(file_row)
                        else:
                            self.error(f'Given file {file_row.filename} mime-type {file_row.mime_type} is not a vtt file')
                else:
                    file_row, folder_row = get_file_by_user(self.file_id, self.user, db_session)

                    if file_row.mime_type.startswith('text/vtt'):
                        to_process.append(file_row)
                    else:
                        self.error(f'Given file {file_row.filename} mime-type {file_row.mime_type} is not a vtt file')

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
            with temporary_folder(self.temp_folder, self) as temp_folder:

                self.info(f'Created Temp Folder: {temp_folder}')

                total_files = len(to_process)
                index = 0
                for file in to_process:

                    if self.is_cancelled:
                        self.info('Leaving Early')
                        return

                    index = index + 1

                    self.update_progress((index / total_files) * 100.0)

                    self.info(f'Working on {file.filename}')

                    srt_file = self.find_subtitle_for_file(file, temp_folder, self.offset)

                    if srt_file is None:
                        self.warn('Could not find srt / vtt file')
                        continue

                    self.info('Found Subtitle File, Working...')

                    src_path = Path(temp_folder) / 'temp.srt'

                    file_name = get_filename_with_extension(file.filename, 'srt')
                    file_size = src_path.stat().st_size
                    created_time = datetime.fromtimestamp(src_path.stat().st_ctime)
                    mime_type, _ = mimetypes.guess_type(src_path)

                    is_archive = False

                    # Try to insert the object
                    new_file = insert_file(folder_row.id, file_name, mime_type, is_archive, False, file_size,
                                           created_time, db_session)

                    if is_blank(new_file.id):
                        self.critical('file does not have an ID')
                        self.set_failure()
                        continue

                    # Move file to destination folder

                    dest_path = get_data_for_mediafile(new_file, self.primary_folder, self.archive_folder)

                    if self.can_trace():
                        self.trace(f'Dest File: {new_file.id}')

                    self.info(describe_file_size_change(file.filesize, new_file.filesize))

                    shutil.move(str(src_path), str(dest_path))

                    self.set_worked()
        finally:
            if is_not_blank(temp_folder) and os.path.exists(temp_folder):
                shutil.rmtree(temp_folder)
