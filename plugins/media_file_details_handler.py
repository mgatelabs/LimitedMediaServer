import argparse
import logging
from typing import Optional

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_MEDIA
from ffmpeg_utils import get_media_info
from media_utils import get_data_for_mediafile, get_file_by_user
from plugin_system import ActionMediaFilePlugin
from text_utils import is_blank
from thread_utils import TaskWrapper


class MediaFileDetailsPlugin(ActionMediaFilePlugin):
    AI_QUICK_DESCRIPTION = ('Inspects a single media file with ffprobe and logs its container and '
                            'stream details as a readable report.')
    AI_LONG_DESCRIPTION = (
        'A read-only inspection of one media file. It locates the file by id, reports its basic '
        'properties (filename, MIME type, size in KB/bytes, whether it is archived, and its '
        'creation date), and then runs ffprobe over the actual data to capture the container '
        'format, duration, and overall bit rate plus a per-stream breakdown (video codec, width, '
        'height, FPS; audio codec, and so on). The whole result is written to the task log as a '
        'rendered Markdown report, so it is intended for humans/AI reviewing via the task output '
        'rather than for modifying anything. No files, metadata, or database rows are changed. '
        'Requires the ffprobe executable on PATH. No plugin-specific arguments; it operates on '
        'the single file passed to it. Note: this action is not shown in the regular media menu '
        '(available_to_menu) and is reached programmatically.')

    def get_sort(self):
        return {'id': 'media_file_details', 'sequence': 2}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'File Details'

    def get_action_id(self):
        return 'action.file.details'

    def get_action_icon(self):
        return 'info'

    def get_action_args(self):
        return super().get_action_args()

    def process_action_args(self, args):
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        return MediaFileDetailsTask(
            'MediaFileDetails', 'Details: ' + args['file_id'], args['file_id'],
            self.primary_path, self.archive_path, self.temp_path,
        )


class MediaFileDetailsTask(TaskWrapper):

    def __init__(self, name: str, description: str, file_id: Optional[str],
                 primary_folder: str, archive_folder: str, temp_folder: str):
        super().__init__(name, description)
        self.file_id = file_id
        self.primary_folder = primary_folder
        self.archive_folder = archive_folder
        self.temp_folder = temp_folder
        self.priority = 5

    def run(self, db_session: Session):
        if is_blank(self.primary_folder) or is_blank(self.archive_folder) or is_blank(self.temp_folder):
            self.critical('This feature is not ready.  Please configure the app properties and restart the server.')
            return

        if self.file_id is None:
            self.set_failure()
            self.error('Invalid run configuration')
            return

        try:
            file_row, folder_row = get_file_by_user(self.file_id, self.user, db_session)
        except ValueError as ve:
            logging.exception(ve)
            self.error(str(ve))
            self.set_failure()
            return

        filesize_kb = round(file_row.filesize / 1024, 2) if file_row.filesize else 0
        created_str = file_row.created.strftime('%Y-%m-%d %H:%M:%S') if file_row.created else 'Unknown'

        md_lines = [
            '## File Details',
            '',
            '| Property | Value |',
            '|---|---|',
            f'| Filename | `{file_row.filename}` |',
            f'| MIME Type | `{file_row.mime_type}` |',
            f'| File Size | `{filesize_kb} KB ({file_row.filesize} bytes)` |',
            f'| Archive | `{file_row.archive}` |',
            f'| Created | `{created_str}` |',
        ]

        source_file = get_data_for_mediafile(file_row, self.primary_folder, self.archive_folder)
        media_info = get_media_info(source_file, self, print_details=False)

        if media_info is not None:
            md_lines += [
                '',
                '### Media Info',
                '',
                '| Property | Value |',
                '|---|---|',
                f'| Format | `{media_info["format"]}` |',
                f'| Duration | `{media_info["duration"]}` |',
                f'| Bit Rate | `{media_info["bit_rate"]}` |',
                '',
                '#### Streams',
                '',
            ]
            for i, stream in enumerate(media_info.get('streams', []), 1):
                md_lines.append(f'##### Stream {i} ({stream["type"].capitalize()})')
                md_lines.append('')
                md_lines.append('| Property | Value |')
                md_lines.append('|---|---|')
                for key, val in stream.items():
                    md_lines.append(f'| `{key}` | `{val}` |')
                md_lines.append('')

        self.info('\n'.join(md_lines), _markdown=True)
        self.set_worked()
