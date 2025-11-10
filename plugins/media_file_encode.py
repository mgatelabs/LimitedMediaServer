import argparse
import logging
import mimetypes
import os
import shutil
from datetime import datetime
from pathlib import Path

from flask_sqlalchemy.session import Session

from constants import PROPERTY_SERVER_MEDIA_ENCODER_HOST, PROPERTY_SERVER_MEDIA_ENCODER_PORT
from db import MediaFile
from feature_flags import MANAGE_MEDIA
from ffmpeg_utils import encode_video, FFMPEG_PRESET, FFMPEG_PRESET_VALUES, FFMPEG_CRF, FFMPEG_CRF_VALUES, \
    get_ffmpeg_f_argument_from_mimetype, FFMPEG_AUDIO_BIT, FFMPEG_STEREO, FFMPEG_AUDIO_BIT_RATE_VALUES, \
    FFMPEG_STEREO_VALUES
from file_utils import temporary_folder
from media_queries import insert_file, find_files_in_folder
from media_utils import get_data_for_mediafile, get_file_by_user, \
    get_folder_by_user, describe_file_size_change
from plugin_system import ActionMediaFilePlugin, ActionMediaFilesPlugin
from text_utils import is_not_blank, is_blank, clean_string
from thread_utils import TaskWrapper


class EncodeForFilePlugin(ActionMediaFilePlugin):
    """
    Re-encode a file using FFMPEG
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'medenc'
        self.media_encoder_host = None
        self.media_encoder_port = 8080

    def absorb_config(self, config):
        super().absorb_config(config)
        self.media_encoder_port = config[PROPERTY_SERVER_MEDIA_ENCODER_PORT]
        self.media_encoder_host = config[PROPERTY_SERVER_MEDIA_ENCODER_HOST]
        if self.media_encoder_host is not None and len(self.media_encoder_host) == 0:
            self.media_encoder_host = None

    def get_sort(self):
        return {'id': 'media_file_encode', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Encode File'

    def get_action_id(self):
        return 'action.file.encode'

    def get_action_icon(self):
        return 'play_arrow'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(FFMPEG_PRESET)
        result.append(FFMPEG_CRF)
        result.append(FFMPEG_AUDIO_BIT)
        result.append(FFMPEG_STEREO)

        return result

    def process_action_args(self, args):

        results = []

        if 'ffmpeg_preset' not in args or is_blank(args['ffmpeg_preset']):
            results.append('ffmpeg_preset is required')
        else:
            args['ffmpeg_preset'] = clean_string(args['ffmpeg_preset'])

            if args['ffmpeg_preset'] not in FFMPEG_PRESET_VALUES:
                results.append('unknown ffmpeg_preset value')

        if 'ffmpeg_crf' not in args or is_blank(args['ffmpeg_crf']):
            results.append('ffmpeg_preset is required')
        else:
            args['ffmpeg_crf'] = clean_string(args['ffmpeg_crf'])

            if args['ffmpeg_crf'] not in FFMPEG_CRF_VALUES:
                results.append('unknown ffmpeg_crf value')
        # Audio Bit Rate
        if 'ffmpeg_abr' not in args or is_blank(args['ffmpeg_abr']):
            results.append('ffmpeg_abr is required')
        else:
            args['ffmpeg_abr'] = clean_string(args['ffmpeg_abr'])

            if args['ffmpeg_abr'] not in FFMPEG_AUDIO_BIT_RATE_VALUES:
                results.append('unknown ffmpeg_abr value')
        # Mix Down
        if 'ffmpeg_mix' not in args or is_blank(args['ffmpeg_mix']):
            results.append('ffmpeg_mix is required')
        else:
            args['ffmpeg_mix'] = clean_string(args['ffmpeg_mix'])

            if args['ffmpeg_mix'] not in FFMPEG_STEREO_VALUES:
                results.append('unknown ffmpeg_mix value')

        if len(results) > 0:
            return results
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        return EncodeJob("EncodeFile", 'Encoding: ' + args['file_id'], args['file_id'], args['ffmpeg_preset'],
                         args['ffmpeg_crf'],
                         self.primary_path, self.archive_path, self.temp_path, int(args['ffmpeg_abr']),
                         args['ffmpeg_mix'] == 't', self.media_encoder_host, self.media_encoder_port)


class EncodeForFilesPlugin(ActionMediaFilesPlugin):
    """
    Re-encode a file using FFMPEG
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'medencs'
        self.media_encoder_host = None
        self.media_encoder_port = 8080

    def absorb_config(self, config):
        super().absorb_config(config)
        self.media_encoder_port = config[PROPERTY_SERVER_MEDIA_ENCODER_PORT]
        self.media_encoder_host = config[PROPERTY_SERVER_MEDIA_ENCODER_HOST]
        if self.media_encoder_host is not None and len(self.media_encoder_host) == 0:
            self.media_encoder_host = None

    def get_sort(self):
        return {'id': 'media_files_encode', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Encode Files'

    def get_action_id(self):
        return 'action.files.encode'

    def get_action_icon(self):
        return 'play_arrow'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(FFMPEG_PRESET)
        result.append(FFMPEG_CRF)
        result.append(FFMPEG_AUDIO_BIT)
        result.append(FFMPEG_STEREO)

        return result

    def process_action_args(self, args):

        results = []

        if 'ffmpeg_preset' not in args or is_blank(args['ffmpeg_preset']):
            results.append('ffmpeg_preset is required')
        else:
            args['ffmpeg_preset'] = clean_string(args['ffmpeg_preset'])

            if args['ffmpeg_preset'] not in FFMPEG_PRESET_VALUES:
                results.append('unknown ffmpeg_preset value')

        if 'ffmpeg_crf' not in args or is_blank(args['ffmpeg_crf']):
            results.append('ffmpeg_preset is required')
        else:
            args['ffmpeg_crf'] = clean_string(args['ffmpeg_crf'])

            if args['ffmpeg_crf'] not in FFMPEG_CRF_VALUES:
                results.append('unknown ffmpeg_crf value')
        # Audio Bit Rate
        if 'ffmpeg_abr' not in args or is_blank(args['ffmpeg_abr']):
            results.append('ffmpeg_abr is required')
        else:
            args['ffmpeg_abr'] = clean_string(args['ffmpeg_abr'])

            if args['ffmpeg_abr'] not in FFMPEG_AUDIO_BIT_RATE_VALUES:
                results.append('unknown ffmpeg_abr value')
        # Mix Down
        if 'ffmpeg_mix' not in args or is_blank(args['ffmpeg_mix']):
            results.append('ffmpeg_mix is required')
        else:
            args['ffmpeg_mix'] = clean_string(args['ffmpeg_mix'])

            if args['ffmpeg_mix'] not in FFMPEG_STEREO_VALUES:
                results.append('unknown ffmpeg_mix value')

        if len(results) > 0:
            return results
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):

        file_list = args['file_id'].split(",")

        result = []

        for file_id in file_list:
            result.append(EncodeJob("EncodeFile", 'Encoding: ' + file_id, file_id, args['ffmpeg_preset'],
                                    args['ffmpeg_crf'],
                                    self.primary_path, self.archive_path, self.temp_path, int(args['ffmpeg_abr']),
                                    args['ffmpeg_mix'] == 't', self.media_encoder_host, self.media_encoder_port))

        return result


class EncodeJob(TaskWrapper):
    def __init__(self, name, description, file_id, ffmpeg_preset: str, ffmpeg_crf: str, primary_folder: str,
                 archive_folder: str,
                 temp_folder: str, audio_bit_rate: int = 128, stereo: bool = True, encoder_host: str | None = None,
                 encoder_port: int | None = 8080):
        super().__init__(name, description)
        self.file_id = file_id
        self.folder_id = None
        self.primary_folder = primary_folder
        self.archive_folder = archive_folder
        self.temp_folder = temp_folder
        self.ffmpeg_preset = ffmpeg_preset
        self.ffmpeg_crf = int(ffmpeg_crf)
        self.weight = 70
        if encoder_host is not None and len(encoder_host) > 0:
            self.weight = 10
        self.audio_bit_rate = audio_bit_rate
        self.stereo = stereo
        self.encoder_host = encoder_host
        self.encoder_port = encoder_port

    def run(self, db_session: Session):

        # Sanity Check
        if is_blank(self.primary_folder) or is_blank(self.archive_folder) or is_blank(self.temp_folder):
            self.critical('This feature is not ready.  Please configure the app properties and restart the server.')

        to_process: list[MediaFile] = []

        if self.folder_id is not None:
            try:
                if self.can_trace():
                    self.trace('Folder Logic')
                folder_row = get_folder_by_user(self.folder_id, self.user, db_session)
                if self.can_trace():
                    self.trace('Getting Files')
                self.ref_folder_id = folder_row.id
                files = find_files_in_folder(folder_row.id, None, 0, 1000, db_session=db_session)
                for file in files:
                    if file.mime_type.startswith('video/'):
                        if self.can_trace():
                            self.trace(f'Adding File {file.filename}')
                        to_process.append(file)
            except ValueError as ve:
                logging.exception(ve)
                self.error(str(ve))
                self.set_failure()
                return

        elif self.file_id is not None:
            try:
                if self.can_trace():
                    self.trace('File Logic')

                file_row, folder_row = get_file_by_user(self.file_id, self.user, db_session)

                if file_row.mime_type.startswith('video/'):
                    to_process.append(file_row)
                    self.ref_folder_id = folder_row.id
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
            with temporary_folder(self.temp_folder, self) as temp_folder:

                total_files = len(to_process)
                index = 0
                for file in to_process:

                    if self.is_cancelled:
                        self.info('Leaving Early')
                        return

                    index = index + 1

                    self.update_progress((index / total_files) * 100.0)

                    source_file = get_data_for_mediafile(file, self.primary_folder, self.archive_folder)

                    desired_format = get_ffmpeg_f_argument_from_mimetype(file.mime_type)

                    dest_file = os.path.join(temp_folder, 'temp.mp4')

                    self.info(f'Working on {file.filename}')

                    modified_encoder_host = None

                    if self.encoder_host is not None:
                        modified_encoder_host = 'http://' + self.encoder_host + ":" + str(self.encoder_port)

                    if encode_video(source_file, dest_file, desired_format, self.ffmpeg_preset, self.ffmpeg_crf,
                                    self.stereo, self.audio_bit_rate, log=self, server_url=modified_encoder_host):

                        src_path = Path(temp_folder) / 'temp.mp4'

                        file_name = file.filename + '_encoded'
                        file_size = src_path.stat().st_size
                        created_time = datetime.fromtimestamp(src_path.stat().st_ctime)
                        mime_type, _ = mimetypes.guess_type(src_path)

                        is_archive = False

                        # Try to insert the object
                        new_file = insert_file(folder_row.id, file_name, mime_type, is_archive, False, file_size,
                                               created_time,
                                               db_session)

                        if is_blank(new_file.id):
                            self.critical('file does not have an ID')
                            self.set_failure()
                            return

                        # Move file to destination folder

                        dest_path = get_data_for_mediafile(new_file, self.primary_folder, self.archive_folder)

                        if self.can_trace():
                            self.trace(f'Dest MediaFile: {new_file.id}')

                        self.info(describe_file_size_change(file.filesize, new_file.filesize))

                        shutil.move(str(src_path), str(dest_path))

                        self.set_worked()
                    else:
                        self.set_failure()
                        self.error('Did not convert file')
                        return
        finally:
            if is_not_blank(temp_folder) and os.path.exists(temp_folder):
                shutil.rmtree(temp_folder)
