import argparse
import logging
import os
import shutil
import subprocess
from datetime import datetime

from flask_sqlalchemy.session import Session

from db import MediaFile
from feature_flags import MANAGE_MEDIA
from ffmpeg_utils import generate_video_thumbnail, probe_media
from file_utils import temporary_folder
from image_utils import resize_image
from media_queries import insert_file
from media_utils import get_data_for_mediafile, get_file_by_user, \
    clean_files_for_mediafile, get_preview_for_mediafile
from plugin_system import ActionMediaFilesPlugin
from plugin_methods import plugin_string_arg, plugin_select_arg, plugin_select_values
from text_utils import is_not_blank, is_blank, clean_string
from thread_utils import TaskWrapper


class MuxFilesPlugin(ActionMediaFilesPlugin):
    """
    Mux exactly 2 media files: the video stream from the file that contains video and the
    audio stream from the other file are stream-copied (no re-encode) into a single MP4,
    the result is registered as a new file, and both source files are deleted.
    """
    AI_QUICK_DESCRIPTION = ('Muxes exactly 2 media files into one MP4 by stream-copying the video '
                            'stream from the file that contains video and the audio stream from the '
                            'other file (detected via ffprobe), registers the result as a new file, '
                            'and deletes both source files.')
    AI_LONG_DESCRIPTION = (
        'Combines exactly two selected media files into a single new MP4 using a local ffmpeg '
        'stream-copy remux (no re-encoding, no remote encoder). Takes exactly two comma-separated '
        'file ids; both files must have a video/ MIME type. Each file is probed with ffprobe and '
        'classified: exactly one file must contain a video stream (the video source) and the '
        'other file must contain an audio stream (the audio source). If both files contain video '
        'streams, or if either required stream is missing, the job fails without touching the '
        'sources. The remux runs: ffmpeg -i <video> -i <audio> -map 0:v:0 -map 1:a:0 -c copy '
        '-shortest -movflags +faststart <output>, so the first video stream and the first audio '
        'stream are copied as-is and the output is trimmed to the shorter stream. The result is '
        'registered in the video source\'s folder as video/mp4, named exactly the same as the '
        'video source\'s filename by default (the Postfix is blank by default), or with the '
        'Postfix added before the .mp4 extension when one is provided, moved to the '
        'Primary or Archive disk, and a preview thumbnail is generated. After the mux succeeds '
        'both source files are always deleted (physical file + DB row); there is no keep/purge '
        'choice. If the sources live in different folders the result is registered in the folder '
        'of the first selected file. Requires ffmpeg and ffprobe.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'medmuxs'

    def get_sort(self):
        return {'id': 'media_files_mux', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Mux Files'

    def get_action_id(self):
        return 'action.files.mux'

    def get_action_icon(self):
        return 'join'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(plugin_string_arg('Postfix', 'postfix',
                                        'Optional suffix added before the extension; blank by default, '
                                        'in which case the result keeps the video source\'s name'))

        result.append(
            plugin_select_arg('Location', 'dest', 'primary',
                              plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'), '', 'media',
                              adv='Y')
        )

        return result

    def process_action_args(self, args):

        results = []

        if 'file_id' not in args or is_blank(args['file_id']):
            results.append('file_id is required')
        else:
            file_ids = [clean_string(x) for x in args['file_id'].split(',') if is_not_blank(x)]
            if len(file_ids) != 2:
                results.append('exactly 2 file ids are required, got ' + str(len(file_ids)))
            elif file_ids[0] == file_ids[1]:
                results.append('the two file ids must be different')
            else:
                args['file_id'] = ','.join(file_ids)

        if 'postfix' not in args or is_blank(args['postfix']):
            args['postfix'] = ''
        else:
            args['postfix'] = clean_string(args['postfix'])

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

        file_list = args['file_id'].split(",")

        return MuxJob("MuxFiles", 'Muxing: ' + args['file_id'], file_list,
                      self.primary_path, self.archive_path,
                      self.temp_path,
                      postfix=args['postfix'], dest=args['dest'])


class MuxJob(TaskWrapper):

    def __init__(self, name, description, file_ids: list, primary_folder: str,
                 archive_folder: str,
                 temp_folder: str, postfix: str = '', dest: str | None = 'primary'):
        super().__init__(name, description)
        self.file_ids = file_ids
        self.folder_id = None
        self.primary_folder = primary_folder
        self.archive_folder = archive_folder
        self.temp_folder = temp_folder
        self.dest = dest
        self.postfix = postfix
        self.weight = 70

    def _purge_source(self, file: MediaFile, db_session: Session):
        try:
            clean_files_for_mediafile(file, self.primary_folder, self.archive_folder)
            db_session.delete(file)
            self.info(f'Deleted source file: {file.filename}')
        except OSError as e:
            self.warn(f'Failed to delete source file {file.filename}: {e}')

    @staticmethod
    def _stream_flags(metadata: dict) -> tuple[bool, bool]:
        has_video = any(s.get('codec_type') == 'video' for s in metadata.get('streams', []))
        has_audio = any(s.get('codec_type') == 'audio' for s in metadata.get('streams', []))
        return has_video, has_audio

    def _run_mux(self, video_path: str, audio_path: str, dest_file: str) -> bool:

        try:
            self.info('Starting local ffmpeg mux (stream copy)...')

            command = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", audio_path,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c", "copy",
                "-shortest",
                "-movflags", "+faststart",
                dest_file
            ]

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

            self.info("FFMPEG mux completed successfully.")
            return True

        except Exception as e:
            self.error(f"Local mux failed: {e}")
            logging.exception(e)
            return False

    def run(self, db_session: Session):

        # Sanity Check
        if is_blank(self.primary_folder) or is_blank(self.archive_folder) or is_blank(self.temp_folder):
            self.critical('This feature is not ready.  Please configure the app properties and restart the server.')

        # Load phase
        file_rows: list[MediaFile] = []
        folder_row = None

        for file_id in self.file_ids:
            try:
                if self.can_trace():
                    self.trace(f'Loading File {file_id}')

                file_row, file_folder = get_file_by_user(file_id, self.user, db_session)

            except ValueError as ve:
                self.set_failure()
                self.error(f'Could not load file {file_id}: {ve}')
                return

            if not file_row.mime_type.startswith('video/'):
                self.set_failure()
                self.error(f'File {file_row.filename} mime-type {file_row.mime_type} is not a video')
                return

            file_rows.append(file_row)
            if folder_row is None:
                folder_row = file_folder

        if folder_row is None or len(file_rows) != 2:
            self.set_failure()
            self.error('Expected exactly 2 video files to process')
            return

        self.ref_folder_id = folder_row.id
        self.ref_folder_name = folder_row.name if hasattr(folder_row, 'name') else str(folder_row.id)
        self.ref_folder_preview = folder_row.preview == True

        with temporary_folder(self.temp_folder, self) as temp_folder:

            # Probe phase
            entries = []
            for index, file in enumerate(file_rows, start=1):

                if self.is_cancelled:
                    self.info('Leaving Early')
                    return

                self.update_progress((index / 4.0) * 100.0)

                source_file = get_data_for_mediafile(file, self.primary_folder, self.archive_folder)
                self.info(f'Probing {file.filename}')

                metadata = probe_media(source_file, self)
                if metadata is None:
                    self.set_failure()
                    self.error(f'Probe failed for {file.filename}')
                    return

                has_video, has_audio = self._stream_flags(metadata)
                self.info(f'{file.filename}: video={has_video}, audio={has_audio}')
                entries.append({'file': file, 'path': source_file, 'has_video': has_video, 'has_audio': has_audio})

            # Selection phase
            self.update_progress(2.0 / 4.0 * 100.0)

            video_entries = [e for e in entries if e['has_video']]
            if len(video_entries) != 1:
                self.set_failure()
                self.error(f'Expected exactly 1 file with a video stream, found {len(video_entries)}')
                return

            video_entry = video_entries[0]
            audio_entry = next((e for e in entries if e is not video_entry and e['has_audio']), None)
            if audio_entry is None:
                self.set_failure()
                other = next(e for e in entries if e is not video_entry)
                self.error(f'File {other["file"].filename} does not contain an audio stream')
                return

            self.info(f'Video source: {video_entry["file"].filename}, audio source: {audio_entry["file"].filename}')

            # Mux phase
            self.update_progress(3.0 / 4.0 * 100.0)

            dest_file = os.path.join(temp_folder, 'temp.mp4')

            if not self._run_mux(video_entry['path'], audio_entry['path'], dest_file):
                self.set_failure()
                self.error('Did not mux files')
                return

            if not os.path.exists(dest_file) or os.path.getsize(dest_file) == 0:
                self.set_failure()
                self.error('Muxed file is missing or empty')
                return

            # Install phase
            self.update_progress(100.0)

            src_path = os.path.join(temp_folder, 'temp.mp4')
            base, ext = os.path.splitext(video_entry['file'].filename)
            if is_blank(self.postfix):
                file_name = video_entry['file'].filename
            else:
                file_name = base + self.postfix + '.mp4'

            file_size = os.path.getsize(src_path)
            created_time = datetime.fromtimestamp(os.path.getctime(src_path))

            is_archive = self.dest is not None and self.dest == 'archive'

            self.info(f'Muxing into {file_name}')

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

            shutil.move(src_path, dest_path)

            for entry in entries:
                self._purge_source(entry['file'], db_session)

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
