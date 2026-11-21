import argparse
import logging
import mimetypes
import os
import shutil
from datetime import datetime
from pathlib import Path

from flask_sqlalchemy.session import Session

from db import MediaFile
from feature_flags import MANAGE_MEDIA
from ffmpeg_utils import encode_video, FFMPEG_PRESET, FFMPEG_PRESET_VALUES, FFMPEG_CRF, FFMPEG_CRF_VALUES, \
    get_ffmpeg_f_argument_from_mimetype, FFMPEG_AUDIO_BIT, FFMPEG_STEREO, FFMPEG_AUDIO_BIT_RATE_VALUES, \
    FFMPEG_STEREO_VALUES, generate_video_thumbnail, FFMPEG_RESOLUTION, FFMPEG_RESOLUTION_VALUES
from file_utils import temporary_folder
from image_utils import resize_image
from media_queries import insert_file, find_files_in_folder
from media_utils import get_data_for_mediafile, get_file_by_user, \
    get_folder_by_user, describe_file_size_change, clean_files_for_mediafile, get_preview_for_mediafile
from plugin_system import ActionMediaFilePlugin, ActionMediaFilesPlugin
from plugin_methods import plugin_string_arg, plugin_select_arg, plugin_select_values, FFMPEG_LOCAL_ONLY
from text_utils import is_not_blank, is_blank, clean_string
from thread_utils import TaskWrapper


class EncodeForFilePlugin(ActionMediaFilePlugin):
    """
    Re-encode a file using FFMPEG
    """
    AI_QUICK_DESCRIPTION = ('Re-encodes one video file to H.264 MP4 with the chosen quality settings, '
                            'registers the result as a new file, and optionally keeps, purges, or '
                            'renames the original.')
    AI_LONG_DESCRIPTION = (
        'Re-encodes a single video file (only files whose MIME type starts with "video/" are '
        'accepted) using ffmpeg (or a remote encoder service when one is configured and '
        '"Local Encoding Only" is No). The encode uses H.264 (libx264, high profile, level 4.2, '
        'yuv420p) with a configurable Preset (default medium), Constant Rate Factor (default 23), '
        'audio as AAC at a selectable bit rate (default 128k), optional stereo mix-down, and an '
        'optional max-resolution scale-down (default: keep source). faststart is applied for web '
        'playback. The result is written to a temp file, registered in the database as a new '
        'media file in the same folder, given the Postfix (default "_enc") before the extension, '
        'moved to the chosen disk (Primary or Archive), and a preview thumbnail is generated. '
        'After a clean encode the source is handled per the Clean Up choice: Keep (default, leave '
        'it), Purge (delete file + DB row), or Rename (prefix the original\'s filename with a '
        'timestamp so it survives alongside the encode). Required arguments: Preset, CRF, Audio '
        'Bit Rate, Mix-down, and Location (dest). Max Resolution, Postfix, Clean Up, and Local '
        'Encoding Only are optional. Requires ffmpeg (and a remote encoder host to use the '
        'remote path).')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'medenc'

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
        result.append(FFMPEG_RESOLUTION)
        result.append(plugin_string_arg('Postfix', 'postfix', 'Suffix added before the extension (default: _enc)'))

        result.append(
            plugin_select_arg('Location', 'dest', 'primary',
                              plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'), '', 'media',
                              adv='Y')
        )

        result.append(
            plugin_select_arg('Clean Up', 'cleanup', 'keep',
                              plugin_select_values('Keep', 'keep', 'Purge', 'purge', 'Rename', 'rename'),
                               'What to do with the source file after a successful encode.', adv='Y')
        )

        result.append(FFMPEG_LOCAL_ONLY)

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
        # Max Resolution
        if 'ffmpeg_res' not in args or is_blank(args['ffmpeg_res']):
            args['ffmpeg_res'] = 'src'
        else:
            args['ffmpeg_res'] = clean_string(args['ffmpeg_res'])
            if args['ffmpeg_res'] not in FFMPEG_RESOLUTION_VALUES:
                results.append('unknown ffmpeg_res value')

        if 'postfix' not in args or is_blank(args['postfix']):
            args['postfix'] = '_enc'
        else:
            args['postfix'] = clean_string(args['postfix'])

        if 'dest' not in args or is_blank(args['dest']):
            results.append('dest is required')
        elif not (args['dest'] == 'primary' or args['dest'] == 'archive'):
            results.append('Invalid dest value')

        if 'cleanup' not in args or is_blank(args['cleanup']):
            args['cleanup'] = 'keep'
        else:
            args['cleanup'] = clean_string(args['cleanup'])
            if args['cleanup'] not in ('keep', 'purge', 'rename'):
                results.append('Invalid cleanup value')

        if 'local_encoding_only' not in args or is_blank(args['local_encoding_only']):
            args['local_encoding_only'] = 'n'
        else:
            args['local_encoding_only'] = clean_string(args['local_encoding_only'])
            if args['local_encoding_only'] not in ('y', 'n'):
                results.append('Invalid local_encoding_only value')

        if len(results) > 0:
            return results
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        return EncodeJob("EncodeFile", 'Encoding: ' + args['file_id'], args['file_id'], args['ffmpeg_preset'],
                         args['ffmpeg_crf'],
                         self.primary_path, self.archive_path, self.temp_path, int(args['ffmpeg_abr']),
                         args['ffmpeg_mix'] == 't',
                         postfix=args['postfix'], cleanup=args['cleanup'], resolution=args['ffmpeg_res'],
                         dest=args['dest'], local_only=args['local_encoding_only'] == 'y')


class EncodeForFilesPlugin(ActionMediaFilesPlugin):
    """
    Re-encode a file using FFMPEG
    """
    AI_QUICK_DESCRIPTION = ('Re-encodes a comma-separated list of video files to H.264 MP4 using '
                            'ffmpeg, registering each result as a new media file.')
    AI_LONG_DESCRIPTION = (
        'The multi-file version of the single-file encode. Takes a comma-separated list of file '
        'ids and queues one EncodeJob per file; non-video files in the list are skipped with an '
        'error. Each job re-encodes its source to H.264 MP4 (libx264 high profile 4.2, yuv420p, '
        'AAC audio, faststart) using the shared Preset, constant-rate-factor, audio bit-rate, '
        'stereo mix-down, and optional max-resolution options, via a remote encoder service when '
        'configured or local ffmpeg otherwise. Each encoded result is registered as a new media '
        'file with the Postfix (default "_enc"), moved to the Primary or Archive disk, and '
        'thumbnailed; each source is then kept, purged, or timestamp-renamed per the Clean Up '
        'choice. Required arguments: Preset, CRF, Audio Bit Rate, Mix-down, and Location. '
        'Requires ffmpeg.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'medencs'

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
        result.append(FFMPEG_RESOLUTION)
        result.append(plugin_string_arg('Postfix', 'postfix', 'Suffix added before the extension (default: _enc)'))
        result.append(
            plugin_select_arg('Location', 'dest', 'primary',
                              plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'), '', 'media',
                              adv='Y')
        )

        result.append(
            plugin_select_arg('Clean Up', 'cleanup', 'keep',
                              plugin_select_values('Keep', 'keep', 'Purge', 'purge', 'Rename', 'rename'),
                               'What to do with the source file after a successful encode.', adv='Y')
        )

        result.append(FFMPEG_LOCAL_ONLY)

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
        # Max Resolution
        if 'ffmpeg_res' not in args or is_blank(args['ffmpeg_res']):
            args['ffmpeg_res'] = 'src'
        else:
            args['ffmpeg_res'] = clean_string(args['ffmpeg_res'])
            if args['ffmpeg_res'] not in FFMPEG_RESOLUTION_VALUES:
                results.append('unknown ffmpeg_res value')

        if 'postfix' not in args or is_blank(args['postfix']):
            args['postfix'] = '_enc'
        else:
            args['postfix'] = clean_string(args['postfix'])

        if 'dest' not in args or is_blank(args['dest']):
            results.append('dest is required')
        elif not (args['dest'] == 'primary' or args['dest'] == 'archive'):
            results.append('Invalid dest value')

        if 'cleanup' not in args or is_blank(args['cleanup']):
            args['cleanup'] = 'keep'
        else:
            args['cleanup'] = clean_string(args['cleanup'])
            if args['cleanup'] not in ('keep', 'purge', 'rename'):
                results.append('Invalid cleanup value')

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
                                    self.primary_path, self.archive_path,
                                    self.temp_path, int(args['ffmpeg_abr']), args['ffmpeg_mix'] == 't',
                                    postfix=args['postfix'], cleanup=args['cleanup'], resolution=args['ffmpeg_res'],
                                    dest=args['dest'], local_only=args['local_encoding_only'] == 'y'))

        return result


class EncodeJob(TaskWrapper):
    def __init__(self, name, description, file_id, ffmpeg_preset: str, ffmpeg_crf: str, primary_folder: str,
                 archive_folder: str,
                 temp_folder: str, audio_bit_rate: int = 128, stereo: bool = True,
                  postfix: str = '_enc', cleanup: str = 'keep', resolution: str = 'src', dest: str | None = 'primary',
                  local_only: bool = False):
        super().__init__(name, description)
        self.file_id = file_id
        self.folder_id = None
        self.primary_folder = primary_folder
        self.archive_folder = archive_folder
        self.temp_folder = temp_folder
        self.ffmpeg_preset = ffmpeg_preset
        self.ffmpeg_crf = int(ffmpeg_crf)
        self.dest = dest
        self.postfix = postfix
        self.cleanup = cleanup
        self.weight = 70 if local_only else 20
        self.audio_bit_rate = audio_bit_rate
        self.stereo = stereo
        self.resolution = resolution
        self.local_only = local_only

    def _apply_cleanup(self, file: MediaFile, db_session: Session):
        if self.cleanup == 'keep':
            return
        try:
            if self.cleanup == 'purge':
                clean_files_for_mediafile(file, self.primary_folder, self.archive_folder)
                db_session.delete(file)
                self.info(f'Purged source file: {file.filename}')
            elif self.cleanup == 'rename':
                stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                file.filename = f'{stamp}_{file.filename}'
                self.info(f'Renamed source record to: {file.filename}')
        except OSError as e:
            self.warn(f'Clean up failed for {file.filename}: {e}')

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
                self.ref_folder_name = folder_row.name if hasattr(folder_row, 'name') else str(folder_row.id)
                self.ref_folder_preview = folder_row.preview == True
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
                    self.ref_folder_name = folder_row.name if hasattr(folder_row, 'name') else str(folder_row.id)
                    self.ref_folder_preview = folder_row.preview == True
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

                    if encode_video(source_file, dest_file, desired_format, self.ffmpeg_preset, self.ffmpeg_crf,
                                    self.stereo, self.audio_bit_rate, resolution=self.resolution,
                                    local_only=self.local_only, log=self):

                        src_path = Path(temp_folder) / 'temp.mp4'

                        base, ext = os.path.splitext(file.filename)
                        if not ext:
                            file_name = file.filename + '.mp4'
                        else:
                            file_name = base + self.postfix + ext
                        file_size = src_path.stat().st_size
                        created_time = datetime.fromtimestamp(src_path.stat().st_ctime)
                        mime_type, _ = mimetypes.guess_type(src_path)

                        is_archive = self.dest is not None and self.dest == 'archive'

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

                        self._apply_cleanup(file, db_session)
                        db_session.commit()

                        self.trace('Finding Preview')
                        preview_path = get_preview_for_mediafile(new_file, self.primary_folder)

                        try:
                            generate_video_thumbnail(dest_path, 'mp4', preview_path, 40)
                            if os.path.exists(preview_path):
                                resize_image(preview_path, preview_path, 256, 'WEBP')
                                new_file.preview = True
                                db_session.commit()
                            else:
                                self.warn("Could not find preview")
                        except Exception as e:
                            logging.exception(e)
                            self.set_failure()

                        self.set_worked()
                    else:
                        self.set_failure()
                        self.error('Did not convert file')
                        return
        finally:
            if is_not_blank(temp_folder) and os.path.exists(temp_folder):
                shutil.rmtree(temp_folder)
