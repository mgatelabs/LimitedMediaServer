import argparse
import logging
import mimetypes
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask_sqlalchemy.session import Session

from db import MediaFile, MediaFolder
from feature_flags import MANAGE_MEDIA
from ffmpeg_utils import FFMPEG_PRESET, FFMPEG_PRESET_VALUES, FFMPEG_CRF, FFMPEG_CRF_VALUES, \
    get_ffmpeg_f_argument_from_mimetype, FFMPEG_AUDIO_BIT, FFMPEG_AUDIO_BIT_RATE_VALUES, \
    FFMPEG_STEREO, FFMPEG_STEREO_VALUES, encode_video, generate_video_thumbnail, FFMPEG_RESOLUTION, \
    FFMPEG_RESOLUTION_VALUES
from file_utils import temporary_folder
from image_utils import resize_image
from media_queries import insert_file, find_file_by_filename, find_files_in_folder
from media_utils import get_data_for_mediafile, \
    get_filename_with_extension, convert_vtt_to_srt, get_folder_by_user, get_file_by_user, describe_file_size_change, \
    get_preview_for_mediafile, clean_files_for_mediafile
from number_utils import is_integer_with_sign
from plugin_methods import plugin_string_arg, plugin_select_arg, plugin_select_values, FFMPEG_LOCAL_ONLY
from plugin_system import ActionMediaFilePlugin, ActionMediaFilesPlugin, ActionMediaFolderPlugin
from text_utils import is_not_blank, is_blank, clean_string
from thread_utils import TaskWrapper


class SubtitleForFilePlugin(ActionMediaFilePlugin):
    """
    Subtitle a file using FFMPEG
    """
    AI_QUICK_DESCRIPTION = ('Burns a matching .srt/.vtt subtitle track into one video file and '
                            'registers the result as a new media file.')
    AI_LONG_DESCRIPTION = (
        'Burns hard subtitles into a single video file. It looks in the file\'s folder for a '
        'subtitle file with the same base name (first a .srt, then a .vtt); a .vtt is converted '
        'to .srt in a temp folder using the Offset (in seconds, signed) before encoding. The '
        'video is re-encoded to H.264 MP4 (libx264, AAC, faststart) with the subtitle track baked '
        'in via ffmpeg\'s subtitles filter, honoring the shared Preset / constant-rate-factor / '
        'audio bit-rate / stereo mix-down / optional max-resolution options and using a remote '
        'encoder service when configured. The output is registered as a new file with the Postfix '
        '(default "_sub"), moved to the Primary or Archive disk, thumbnailed, and the video and '
        'subtitle sources are then kept, purged, or timestamp-renamed per Clean Up. Files with no '
        'matching subtitle are skipped with a warning. Required arguments: Preset, CRF, Audio Bit '
        'Rate, Mix-down, and Location. Offset, Postfix, Clean Up, Max Resolution, and Local '
        'Encoding Only are optional. Requires ffmpeg.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'medsub'

    def get_sort(self):
        return {'id': 'media_file_subtitle', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Burn Subtitles'

    def get_action_id(self):
        return 'action.file.subtitle'

    def get_action_icon(self):
        return 'title'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(FFMPEG_PRESET)
        result.append(FFMPEG_CRF)
        result.append(FFMPEG_AUDIO_BIT)
        result.append(FFMPEG_STEREO)
        result.append(FFMPEG_RESOLUTION)
        result.append(plugin_string_arg('Offset', 'offset', 'Subtitle Offset in seconds'))
        result.append(plugin_string_arg('Postfix', 'postfix', 'Suffix added before the extension (default: _sub)'))

        result.append(
            plugin_select_arg('Location', 'dest', 'primary',
                              plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'), '', 'media',
                              adv='Y')
        )

        result.append(
            plugin_select_arg('Clean Up', 'cleanup', 'keep',
                              plugin_select_values('Keep', 'keep', 'Purge', 'purge', 'Rename', 'rename'),
                               'What to do with the source files after a successful encode.', adv='Y')
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
            results.append('ffmpeg_crf is required')
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


        if 'offset' not in args or is_blank(args['offset']):
            args['offset'] = 0
        else:
            args['offset'] = clean_string(args['offset'])

            if not is_integer_with_sign(args['offset']):
                results.append('offset is not a valid integer')

        if 'postfix' not in args or is_blank(args['postfix']):
            args['postfix'] = '_sub'
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
        return SubtitleEncodeJob("SubtitleFile", 'Encoding: ' + args['file_id'], args['file_id'], None,
                                 args['ffmpeg_preset'], args['ffmpeg_crf'], self.primary_path, self.archive_path,
                                 self.temp_path, int(args['ffmpeg_abr']), args['ffmpeg_mix'] == 't',
                                  int(args['offset']), dest=args['dest'],
                                  postfix=args['postfix'], cleanup=args['cleanup'], resolution=args['ffmpeg_res'],
                                  local_only=args['local_encoding_only'] == 'y')


class SubtitleForFilesPlugin(ActionMediaFilesPlugin):
    """
    Subtitle a file using FFMPEG
    """
    AI_QUICK_DESCRIPTION = ('Burns a matching .srt/.vtt subtitle track into each file of a '
                            'comma-separated list and registers each result as a new media file.')
    AI_LONG_DESCRIPTION = (
        'The multi-file version of the single-file burn-subtitles action. Takes a comma-separated '
        'list of file ids and queues one SubtitleEncodeJob per file (non-video files are skipped '
        'with an error). Each job finds a .srt (preferred) or .vtt companion with the same base '
        'name in the file\'s folder, converting any .vtt to .srt with the signed Offset in '
        'seconds, then re-encodes the video to H.264 MP4 with the subtitle baked in via the '
        'subtitles filter. Output is registered as a new file with the Postfix (default "_sub"), '
        'moved to Primary or Archive, thumbnailed, and the video and subtitle sources are kept, '
        'purged, or timestamp-renamed per Clean Up. Files lacking a subtitle are skipped with a '
        'warning. Shared options (Preset, CRF, Audio Bit Rate, Mix-down, Location are required; '
        'Offset, Postfix, Clean Up, Max Resolution, Local Encoding Only optional) work exactly as '
        'in the single-file action, including the remote-encoder path. Requires ffmpeg.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'medsub'

    def get_sort(self):
        return {'id': 'media_file_subtitle', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Burn Subtitles'

    def get_action_id(self):
        return 'action.files.subtitle'

    def get_action_icon(self):
        return 'title'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(FFMPEG_PRESET)
        result.append(FFMPEG_CRF)
        result.append(FFMPEG_AUDIO_BIT)
        result.append(FFMPEG_STEREO)
        result.append(FFMPEG_RESOLUTION)
        result.append(plugin_string_arg('Offset', 'offset', 'Subtitle Offset in seconds'))
        result.append(plugin_string_arg('Postfix', 'postfix', 'Suffix added before the extension (default: _sub)'))
        result.append(
            plugin_select_arg('Location', 'dest', 'primary',
                              plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'), '', 'media',
                              adv='Y')
        )

        result.append(
            plugin_select_arg('Clean Up', 'cleanup', 'keep',
                              plugin_select_values('Keep', 'keep', 'Purge', 'purge', 'Rename', 'rename'),
                               'What to do with the source files after a successful encode.', adv='Y')
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
            results.append('ffmpeg_crf is required')
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

        if 'offset' not in args or is_blank(args['offset']):
            args['offset'] = 0
        else:
            args['offset'] = clean_string(args['offset'])

            if not is_integer_with_sign(args['offset']):
                results.append('offset is not a valid integer')

        if 'postfix' not in args or is_blank(args['postfix']):
            args['postfix'] = '_sub'
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

        file_list = args['file_id'].split(",")

        result = []

        for file_id in file_list:
            result.append(SubtitleEncodeJob("SubtitleFile", 'Encoding: ' + file_id, file_id, None,
                                            args['ffmpeg_preset'], args['ffmpeg_crf'], self.primary_path,
                                            self.archive_path,
                                            self.temp_path, int(args['ffmpeg_abr']), args['ffmpeg_mix'] == 't',
                                             int(args['offset']), dest=args['dest'],
                                             postfix=args['postfix'], cleanup=args['cleanup'], resolution=args['ffmpeg_res'],
                                             local_only=args['local_encoding_only'] == 'y'))

        return result


class SubtitleForFolderPlugin(ActionMediaFolderPlugin):
    """
    Subtitle a folder using FFMPEG
    """
    AI_QUICK_DESCRIPTION = ('Burns a matching .srt/.vtt subtitle track into every video file in a '
                            'media folder, registering each result as a new media file.')
    AI_LONG_DESCRIPTION = (
        'The folder-wide version of the burn-subtitles action. Processes every video file in the '
        'current folder (up to 1000), one after another in a single task. For each file it looks '
        'for a .srt (preferred) or .vtt companion with the same base name in that same folder, '
        'converting any .vtt to .srt first, then re-encodes the video to H.264 MP4 with the '
        'subtitle baked in via the subtitles filter using the shared Preset / constant-rate-factor '
        '/ audio bit-rate / stereo mix-down / optional max-resolution options and the remote '
        'encoder path when configured. Each output is registered as a new file with the Postfix '
        '(default "_sub"), moved to Primary or Archive, thumbnailed, and the video + subtitle '
        'sources are kept, purged, or timestamp-renamed per Clean Up. Files with no matching '
        'subtitle are skipped with a warning. Note: unlike the file-level variants, this folder '
        'variant does not apply an Offset to VTT-to-SRT conversion. Required arguments: Preset, '
        'CRF, Audio Bit Rate, Mix-down, and Location. Postfix, Clean Up, Max Resolution, and '
        'Local Encoding Only are optional. Requires ffmpeg.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'medsubfol'

    def get_sort(self):
        return {'id': 'media_folder_subtitle', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Burn Subtitles'

    def get_action_id(self):
        return 'action.folder.subtitle'

    def get_action_icon(self):
        return 'title'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(FFMPEG_PRESET)
        result.append(FFMPEG_CRF)
        result.append(FFMPEG_AUDIO_BIT)
        result.append(FFMPEG_STEREO)
        result.append(FFMPEG_RESOLUTION)
        result.append(plugin_string_arg('Offset', 'offset', 'Subtitle Offset in seconds'))
        result.append(plugin_string_arg('Postfix', 'postfix', 'Suffix added before the extension (default: _sub)'))

        result.append(
            plugin_select_arg('Location', 'dest', 'primary',
                              plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'), '', 'media',
                              adv='Y')
        )

        result.append(
            plugin_select_arg('Clean Up', 'cleanup', 'keep',
                              plugin_select_values('Keep', 'keep', 'Purge', 'purge', 'Rename', 'rename'),
                               'What to do with the source files after a successful encode.', adv='Y')
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
            args['postfix'] = '_sub'
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
        return SubtitleEncodeJob("SubtitleFolder", 'Encoding: ' + args['folder_id'], None, args['folder_id'],
                                 args['ffmpeg_preset'], args['ffmpeg_crf'], self.primary_path, self.archive_path,
                                 self.temp_path, int(args['ffmpeg_abr']), args['ffmpeg_mix'] == 't',
                                  dest=args['dest'], postfix=args['postfix'], cleanup=args['cleanup'], resolution=args['ffmpeg_res'],
                                  local_only=args['local_encoding_only'] == 'y')


class SubtitleEncodeJob(TaskWrapper):
    def __init__(self, name, description, file_id: Optional[str], folder_id: Optional[str], ffmpeg_preset: str,
                 ffmpeg_crf: str, primary_folder: str, archive_folder: str, temp_folder: str, audio_bit_rate: int = 128,
                 stereo: bool = True, offset: int = 0, dest: str | None = 'primary', postfix: str = '_sub',
                  cleanup: str = 'keep', resolution: str = 'src', local_only: bool = False):
        super().__init__(name, description)
        self.file_id = file_id
        self.folder_id = folder_id
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
        self.offset = offset
        self.resolution = resolution
        self.local_only = local_only

    def find_subtitle_for_file(self, folder: MediaFolder, file: MediaFile, temp_folder: str, db_session: Session) -> \
            Optional[str]:

        possible_srt_name = get_filename_with_extension(file.filename, 'srt')
        possible_vtt_name = get_filename_with_extension(file.filename, 'vtt')

        srt_row = find_file_by_filename(possible_srt_name, folder.id, db_session)
        vtt_row = find_file_by_filename(possible_vtt_name, folder.id, db_session)
        if srt_row is not None:
            return get_data_for_mediafile(srt_row, self.primary_folder, self.archive_folder)
        elif vtt_row is not None:
            vtt_file = get_data_for_mediafile(vtt_row, self.primary_folder, self.archive_folder)
            srt_file = os.path.join(temp_folder, 'temp.srt')
            if not convert_vtt_to_srt(vtt_file, srt_file, self.offset):
                self.set_failure()
                self.error('Could not convert VTT file to SRT')
                return None
            else:
                return srt_file

    def find_subtitle_row(self, folder: MediaFolder, file: MediaFile, db_session: Session) -> Optional[MediaFile]:
        srt_row = find_file_by_filename(get_filename_with_extension(file.filename, 'srt'), folder.id, db_session)
        if srt_row is not None:
            return srt_row
        return find_file_by_filename(get_filename_with_extension(file.filename, 'vtt'), folder.id, db_session)

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

        folder_row = None

        is_archive = self.dest is not None and self.dest == 'archive'

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

                self.info(f'Created Temp Folder: {temp_folder}')

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

                    srt_file = self.find_subtitle_for_file(folder_row, file, temp_folder, db_session)

                    if srt_file is None:
                        self.warn('Could not find srt / vtt file')
                        continue

                    self.info('Found Subtitle File, Working...')

                    if encode_video(source_file, dest_file, desired_format, self.ffmpeg_preset, self.ffmpeg_crf,
                                    self.stereo, self.audio_bit_rate, log=self,
                                    srt_file=srt_file, resolution=self.resolution, local_only=self.local_only):

                        src_path = Path(temp_folder) / 'temp.mp4'

                        base, ext = os.path.splitext(file.filename)
                        if not ext:
                            file_name = file.filename + '.mp4'
                        else:
                            file_name = base + self.postfix + ext
                        file_size = src_path.stat().st_size
                        created_time = datetime.fromtimestamp(src_path.stat().st_ctime)
                        mime_type, _ = mimetypes.guess_type(src_path)

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
                            self.trace(f'Dest MediaFile: {new_file.id}')

                        self.info(describe_file_size_change(file.filesize, new_file.filesize))

                        shutil.move(str(src_path), str(dest_path))

                        self._apply_cleanup(file, db_session)
                        sub_row = self.find_subtitle_row(folder_row, file, db_session)
                        if sub_row is not None:
                            self._apply_cleanup(sub_row, db_session)
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
                        continue
        finally:
            if is_not_blank(temp_folder) and os.path.exists(temp_folder):
                shutil.rmtree(temp_folder)
