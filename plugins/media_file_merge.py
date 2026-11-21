import argparse
import logging
import os
import shutil
import subprocess
from datetime import datetime

from flask_sqlalchemy.session import Session

from db import MediaFile
from feature_flags import MANAGE_MEDIA
from ffmpeg_utils import FFMPEG_PRESET, FFMPEG_PRESET_VALUES, FFMPEG_CRF, FFMPEG_CRF_VALUES, \
    FFMPEG_AUDIO_BIT, FFMPEG_STEREO, FFMPEG_AUDIO_BIT_RATE_VALUES, FFMPEG_STEREO_VALUES, \
    FFMPEG_RESOLUTION, FFMPEG_RESOLUTION_VALUES, generate_video_thumbnail, probe_media
from file_utils import temporary_folder
from image_utils import resize_image
from media_queries import insert_file
from media_utils import get_data_for_mediafile, get_file_by_user, \
    clean_files_for_mediafile, get_preview_for_mediafile
from plugin_system import ActionMediaFilesPlugin
from plugin_methods import plugin_string_arg, plugin_select_arg, plugin_select_values
from text_utils import is_not_blank, is_blank, clean_string
from thread_utils import TaskWrapper

_RESOLUTION_WIDTH = {'src': None, '4k': 3840, '2k': 2048, '1080': 1920, '720': 1280, '320': 568}


def _build_scale_filter(resolution: str) -> str:
    width = _RESOLUTION_WIDTH.get(resolution.lower())
    if width is None:
        return "scale='iw':-2"
    return f"scale='min({width},iw)':-2"


class MergeFilesPlugin(ActionMediaFilesPlugin):
    """
    Merge a set of media files by taking the best video stream and the best audio
    stream (selected via ffprobe) and re-encoding them into a single file.
    """
    AI_QUICK_DESCRIPTION = ('Merges a group of video files into one new H.264 MP4 by picking '
                            'the best video stream and the best audio stream (via ffprobe) '
                            'across all sources and re-encoding them together.')
    AI_LONG_DESCRIPTION = (
        'Combines several video files into a single new file. Each file in the comma-separated '
        'list must be a video MIME type (others are skipped with a warning); every file is '
        'probed with ffprobe and the highest-quality streams are selected across the whole '
        'group - the best video stream (scored by pixel count, then bit rate) and the best audio '
        'stream (scored by bit rate, then channel count), which may come from two different '
        'source files. Those streams are merged with a local ffmpeg run (always local, no remote '
        'encoder) re-encoded to H.264 MP4 (libx264, high profile, yuv420p, faststart) honoring '
        'the shared Preset / constant-rate-factor / audio bit-rate / stereo mix-down / optional '
        'max-resolution options; if no source has audio the output is video-only. The result is '
        'registered as video/mp4 in the video source file\'s folder, named after that file plus '
        'the Postfix (default "_merge"), moved to the Primary or Archive disk, thumbnailed, and '
        'then every source file is kept, purged, or timestamp-renamed per Clean Up. Files whose '
        'probe fails or that contain no usable streams are skipped with a warning. Required '
        'arguments: Preset, CRF, Audio Bit Rate, Mix-down, and Location. Max Resolution, Postfix, '
        'and Clean Up are optional. Requires ffmpeg and ffprobe.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'medmergs'

    def get_sort(self):
        return {'id': 'media_files_merge', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Merge Files'

    def get_action_id(self):
        return 'action.files.merge'

    def get_action_icon(self):
        return 'join_inner'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(FFMPEG_PRESET)
        result.append(FFMPEG_CRF)
        result.append(FFMPEG_AUDIO_BIT)
        result.append(FFMPEG_STEREO)
        result.append(FFMPEG_RESOLUTION)
        result.append(plugin_string_arg('Postfix', 'postfix', 'Suffix added before the extension (default: _merge)'))

        result.append(
            plugin_select_arg('Location', 'dest', 'primary',
                              plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'), '', 'media',
                              adv='Y')
        )

        result.append(
            plugin_select_arg('Clean Up', 'cleanup', 'keep',
                              plugin_select_values('Keep', 'keep', 'Purge', 'purge', 'Rename', 'rename'),
                              'What to do with the source files after a successful merge.', adv='Y')
        )

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

        if 'postfix' not in args or is_blank(args['postfix']):
            args['postfix'] = '_merge'
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

        return MergeJob("MergeFiles", 'Merging: ' + args['file_id'], file_list, args['ffmpeg_preset'],
                        args['ffmpeg_crf'],
                        self.primary_path, self.archive_path,
                        self.temp_path, int(args['ffmpeg_abr']), args['ffmpeg_mix'] == 't',
                        postfix=args['postfix'], cleanup=args['cleanup'], resolution=args['ffmpeg_res'],
                        dest=args['dest'])


class MergeJob(TaskWrapper):

    def __init__(self, name, description, file_ids: list, ffmpeg_preset: str, ffmpeg_crf: str, primary_folder: str,
                 archive_folder: str,
                 temp_folder: str, audio_bit_rate: int = 128, stereo: bool = True,
                 postfix: str = '_merge', cleanup: str = 'keep', resolution: str = 'src', dest: str | None = 'primary'):
        super().__init__(name, description)
        self.file_ids = file_ids
        self.folder_id = None
        self.primary_folder = primary_folder
        self.archive_folder = archive_folder
        self.temp_folder = temp_folder
        self.ffmpeg_preset = ffmpeg_preset
        self.ffmpeg_crf = int(ffmpeg_crf)
        self.dest = dest
        self.postfix = postfix
        self.cleanup = cleanup
        self.weight = 70
        self.audio_bit_rate = audio_bit_rate
        self.stereo = stereo
        self.resolution = resolution

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

    @staticmethod
    def _probe_file(path: str, log: TaskWrapper) -> dict | None:
        return probe_media(path, log)

    @staticmethod
    def _best_video_stream(metadata: dict) -> tuple[int | None, tuple | None]:
        best_index = None
        best_score = None
        for index, stream in enumerate(metadata.get('streams', [])):
            if stream.get('codec_type') != 'video':
                continue
            width = int(stream.get('width') or 0)
            height = int(stream.get('height') or 0)
            if width == 0 or height == 0:
                continue
            bit_rate = int(stream.get('bit_rate') or 0)
            score = (width * height, bit_rate)
            if best_score is None or score > best_score:
                best_score = score
                best_index = index
        return best_index, best_score

    @staticmethod
    def _best_audio_stream(metadata: dict) -> tuple[int | None, tuple | None]:
        best_index = None
        best_score = None
        for index, stream in enumerate(metadata.get('streams', [])):
            if stream.get('codec_type') != 'audio':
                continue
            bit_rate = int(stream.get('bit_rate') or 0)
            channels = int(stream.get('channels') or 0)
            score = (bit_rate, channels)
            if best_score is None or score > best_score:
                best_score = score
                best_index = index
        return best_index, best_score

    @staticmethod
    def _pick_sources(entries: list) -> tuple[tuple[dict | None, int | None], tuple[dict | None, int | None]]:
        best_video_entry = None
        best_video_index = None
        best_video_score = None
        best_audio_entry = None
        best_audio_index = None
        best_audio_score = None

        for entry in entries:
            video_index, video_score = MergeJob._best_video_stream(entry['metadata'])
            if video_index is not None and (best_video_score is None or video_score > best_video_score):
                best_video_score = video_score
                best_video_index = video_index
                best_video_entry = entry

            audio_index, audio_score = MergeJob._best_audio_stream(entry['metadata'])
            if audio_index is not None and (best_audio_score is None or audio_score > best_audio_score):
                best_audio_score = audio_score
                best_audio_index = audio_index
                best_audio_entry = entry

        return (best_video_entry, best_video_index), (best_audio_entry, best_audio_index)

    def _run_merge(self, video_source: dict, video_index: int, audio_source: dict | None,
                   audio_index: int | None, dest_file: str) -> bool:

        try:
            self.info('Starting local ffmpeg merge...')

            command = ["ffmpeg", "-y"]

            has_audio = audio_source is not None and audio_index is not None

            if has_audio and audio_source['path'] == video_source['path']:
                command.extend(["-i", video_source['path']])
                command.extend(["-map", f"0:{video_index}"])
                command.extend(["-map", f"0:{audio_index}"])
            elif has_audio:
                command.extend(["-i", video_source['path']])
                command.extend(["-i", audio_source['path']])
                command.extend(["-map", f"0:{video_index}"])
                command.extend(["-map", f"1:{audio_index}"])
            else:
                command.extend(["-i", video_source['path']])
                command.extend(["-map", f"0:{video_index}"])

            command.extend([
                "-vf", _build_scale_filter(self.resolution),
                "-c:v", "libx264",
                "-preset", self.ffmpeg_preset,
                "-profile:v", "high",
                "-level", "4.2",
                "-pix_fmt", "yuv420p",
                "-crf", str(self.ffmpeg_crf),
                "-movflags", "+faststart",
            ])

            if has_audio:
                channels = 2 if self.stereo else 1
                command.extend([
                    "-c:a", "aac",
                    "-b:a", f"{self.audio_bit_rate}k",
                    "-ac", str(channels),
                    "-shortest",
                ])

            command.append(dest_file)

            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if result.returncode != 0:
                self.error("FFMPEG failed with error:")
                self.error(result.stderr)
                return False

            self.info("FFMPEG merge completed successfully.")
            return True

        except Exception as e:
            self.error(f"Local merge failed: {e}")
            logging.exception(e)
            return False

    def run(self, db_session: Session):

        # Sanity Check
        if is_blank(self.primary_folder) or is_blank(self.archive_folder) or is_blank(self.temp_folder):
            self.critical('This feature is not ready.  Please configure the app properties and restart the server.')

        to_process: list[MediaFile] = []
        folder_row = None

        for file_id in self.file_ids:
            try:
                if self.can_trace():
                    self.trace(f'Loading File {file_id}')

                file_row, file_folder = get_file_by_user(file_id, self.user, db_session)

                if file_row.mime_type.startswith('video/'):
                    to_process.append(file_row)
                    if folder_row is None:
                        folder_row = file_folder
                else:
                    self.warn(f'Skipping file {file_row.filename}, mime-type {file_row.mime_type} is not a video')

            except ValueError as ve:
                self.warn(f'Could not load file {file_id}: {ve}')

        if folder_row is None:
            self.set_failure()
            self.error('No video files to process')
            return

        self.ref_folder_id = folder_row.id
        self.ref_folder_name = folder_row.name if hasattr(folder_row, 'name') else str(folder_row.id)
        self.ref_folder_preview = folder_row.preview == True

        with temporary_folder(self.temp_folder, self) as temp_folder:

            # Probe phase
            entries = []
            total_files = len(to_process)
            index = 0
            for file in to_process:

                if self.is_cancelled:
                    self.info('Leaving Early')
                    return

                index = index + 1
                self.update_progress((index / (total_files * 3)) * 100.0)

                source_file = get_data_for_mediafile(file, self.primary_folder, self.archive_folder)
                self.info(f'Probing {file.filename}')

                metadata = self._probe_file(source_file, self)
                if metadata is None:
                    self.warn(f'Skipping {file.filename}, probe failed')
                    continue

                has_video = any(s.get('codec_type') == 'video' for s in metadata.get('streams', []))
                has_audio = any(s.get('codec_type') == 'audio' for s in metadata.get('streams', []))

                if not has_video and not has_audio:
                    self.warn(f'Skipping {file.filename}, no video or audio streams')
                    continue

                entries.append({'file': file, 'path': source_file, 'metadata': metadata})

            if len(entries) == 0:
                self.set_failure()
                self.error('No files contain usable media streams')
                return

            # Selection phase
            self.update_progress(100.0 / 3.0)

            (video_source, video_index), (audio_source, audio_index) = self._pick_sources(entries)

            if video_source is None:
                self.set_failure()
                self.error('No file contains a video stream')
                return

            if audio_source is None:
                self.warn('No file contains an audio stream, output will be video only')
            else:
                if audio_source is video_source:
                    self.info(f'Best audio comes from the video source: {audio_source["file"].filename}')
                else:
                    self.info(f'Best video: {video_source["file"].filename}, best audio: {audio_source["file"].filename}')

            # Merge phase
            self.update_progress(200.0 / 3.0)

            dest_file = os.path.join(temp_folder, 'temp.mp4')

            if not self._run_merge(video_source, video_index, audio_source, audio_index, dest_file):
                self.set_failure()
                self.error('Did not merge files')
                return

            if not os.path.exists(dest_file) or os.path.getsize(dest_file) == 0:
                self.set_failure()
                self.error('Merged file is missing or empty')
                return

            # Install phase
            self.update_progress((2 * 100.0) / 3.0)

            src_path = os.path.join(temp_folder, 'temp.mp4')
            base, ext = os.path.splitext(video_source['file'].filename)
            if not ext:
                file_name = video_source['file'].filename + '.mp4'
            else:
                file_name = base + self.postfix + '.mp4'

            file_size = os.path.getsize(src_path)
            created_time = datetime.fromtimestamp(os.path.getctime(src_path))

            is_archive = self.dest is not None and self.dest == 'archive'

            new_file = insert_file(folder_row.id, file_name, 'video/mp4', is_archive, False, file_size,
                                   created_time,
                                   db_session)

            if is_blank(new_file.id):
                self.critical('file does not have an ID')
                self.set_failure()
                return

            dest_path = get_data_for_mediafile(new_file, self.primary_folder, self.archive_folder)

            if self.can_trace():
                self.trace(f'Dest MediaFile: {new_file.id}')

            self.info(f'Merging {len(entries)} file(s) into {file_name}')

            shutil.move(src_path, dest_path)

            for entry in entries:
                self._apply_cleanup(entry['file'], db_session)

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
