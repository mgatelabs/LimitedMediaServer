import argparse
import os
from datetime import datetime, timezone

from PIL import Image
from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_MEDIA
from ffmpeg_utils import get_media_info
from media_queries import find_folder_by_id, find_files_in_folder
from media_utils import get_data_for_mediafile
from plugin_methods import plugin_select_arg, plugin_select_values
from plugin_system import ActionMediaFolderPlugin
from thread_utils import TaskWrapper

# Relative color mode names for images
_COLOR_MODES = {
    '1': 'Black & White',
    'L': 'Grayscale',
    'P': 'Palette (Indexed)',
    'RGB': 'sRGB (Color)',
    'RGBA': 'sRGBA (Color + Alpha)',
    'LAB': 'CIE LAB (Color)',
    'LAb': 'CIE L*a*b* (Color)',
    'HSV': 'HSV (Color)',
    'YCbCr': 'YCbCr (Color)',
}

# Struct for collected file data — mimics a lightweight namedtuple
_FileRecord = {'filename': '', 'mime': '', 'size_str': '', 'date_str': '', 'metadata': '',
               'details': [], 'cat': 'other', '_width': None, '_height': None, '_codec': '', '_fps': '',
               '_audio_codec': '', '_channels': '', '_sample_rate': '', '_duration': '', '_bit_rate': '', '_fmt': '',
               '_mode_name': ''}


def _format_size(size_bytes: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(size_bytes) < 1024.0:
            return f'{size_bytes:.2f} {unit}'
        size_bytes /= 1024.0
    return f'{size_bytes:.2f} PB'


def _format_duration(seconds) -> str:
    if not seconds or isinstance(seconds, (int, float)) and seconds <= 0:
        return 'N/A'
    seconds = int(float(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f'{h}:{m:02d}:{s:02d}'
    return f'{m:02d}:{s:02d}'


def _format_relative(dt: datetime) -> str:
    # Ensure dt is aware by replacing timezone with UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = now - dt
    total_seconds = int(delta.total_seconds())

    if total_seconds < 0:
        return 'in the future'

    if total_seconds < 60:
        return f'{total_seconds}s ago'
    minutes = total_seconds // 60
    if minutes < 60:
        return f'{minutes}m ago' if minutes != 1 else '1m ago'
    hours = minutes // 60
    if hours < 24:
        return f'{hours}h ago' if hours != 1 else '1h ago'
    days = hours // 24
    if days < 30:
        return f'{days}d ago' if days != 1 else '1d ago'
    months = days // 30
    if months < 12:
        return f'{months}mo ago' if months != 1 else '1mo ago'
    years = months // 12
    return f'{years}y ago' if years != 1 else '1y ago'


def _get_color_mode_name(mode: str) -> str:
    return _COLOR_MODES.get(mode, mode)


class MediaInfoForFolderPlugin(ActionMediaFolderPlugin):
    """
    Generates a markdown report of all media files in a folder.
    """
    AI_QUICK_DESCRIPTION = ('Generates a Markdown report of every file in a media folder, '
                            'with type, size, age, and probed media details, written to the '
                            'task log.')
    AI_LONG_DESCRIPTION = (
        'Read-only inspection of one folder. Every file registered in the given folder is '
        'inspected: images are opened with Pillow for resolution, color mode, and format; '
        'video and audio files are probed with ffprobe for resolution, codec, frame rate, '
        'channels, sample rate, duration, and bit rate; anything else reports its extension. '
        'The result is written as a Markdown report to the task log only - nothing is modified, '
        'moved, or re-encoded. Two report formats are available via Mode: Detail (default) '
        'renders a per-file property table in file order, and List renders one summary table per '
        'category (Images, Video, Audio, Other) with filename, type, size, created, and a '
        'metadata column. Requires ffprobe for video/audio probing and Pillow for image '
        'inspection.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'mediafolderinfo'

    def get_sort(self):
        return {'id': 'media_folder_info', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Media Folder Info'

    def get_action_id(self):
        return 'action.folder.info'

    def get_action_icon(self):
        return 'folder'

    def get_action_args(self):
        result = super().get_action_args()
        result.append(
            plugin_select_arg('Mode', 'mode', 'default',
                              plugin_select_values('Detail', 'default', 'List', 'list'),
                              'Report format')
        )
        return result

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def process_action_args(self, args):
        results = []
        if 'folder_id' not in args or not args['folder_id']:
            results.append('folder_id is required')
        return results if results else None

    def create_task(self, db_session: Session, args):
        return MediaInfoFolderTask(
            "MediaFolderInfo",
            f'Info: {args.get("folder_name", args["folder_id"])}',
            args['folder_id'],
            self.primary_path,
            self.archive_path,
            self.temp_path,
            args.get('mode', 'default'),
        )


class MediaInfoFolderTask(TaskWrapper):
    def __init__(self, name, description, folder_id: str, primary_folder: str, archive_folder: str, temp_folder: str,
                 mode='default'):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.primary_folder = primary_folder
        self.archive_folder = archive_folder
        self.temp_folder = temp_folder
        self.mode = mode

    def _get_file_path(self, file_row) -> str | None:
        try:
            return get_data_for_mediafile(file_row, self.primary_folder, self.archive_folder)
        except Exception:
            return None

    def run(self, db_session: Session):
        folder = find_folder_by_id(self.folder_id, db_session)
        if folder is None:
            self.critical('Folder not found in database.')
            self.set_failure()
            return

        self.trace("Before Find Files")

        files = list(find_files_in_folder(self.folder_id, db_session=db_session))
        if not files:
            self.info(f'Folder "{folder.name}" contains no files.', _markdown=True)
            return

        self.trace("After Find Files")

        self.trace("Before Process Files")

        # Phase 1: process each file with progress updates
        records = []
        total = len(files)
        for idx, file_row in enumerate(files):
            filepath = self._get_file_path(file_row)
            file_size = file_row.filesize or 0
            mime = file_row.mime_type or 'application/octet-stream'
            filename = file_row.filename or 'Unknown'

            if file_row.created:
                if hasattr(file_row.created, 'strftime'):
                    date_str = _format_relative(file_row.created)
                else:
                    date_str = str(file_row.created)
            else:
                date_str = 'N/A'

            rec = dict(_FileRecord)
            rec['filename'] = filename
            rec['mime'] = mime
            rec['size_str'] = _format_size(file_size)
            rec['date_str'] = date_str
            rec['metadata'] = ''
            rec['details'] = []
            rec['cat'] = 'other'

            if mime.startswith('image/'):
                rec['cat'] = 'image'
                if filepath and os.path.isfile(filepath):
                    try:
                        with Image.open(filepath) as img:
                            w, h = img.size
                            mode_name = _get_color_mode_name(img.mode)
                            fmt = img.format or ''
                            rec['metadata'] = '{}×{}'.format(w, h)
                            rec['_width'] = w
                            rec['_height'] = h
                            rec['_mode_name'] = mode_name
                            rec['_fmt'] = fmt
                    except Exception:
                        pass

            elif mime.startswith('video/'):
                rec['cat'] = 'video'
                if filepath and os.path.isfile(filepath):
                    media = get_media_info(filepath, self, print_details=False)
                    if media and media.get('streams'):
                        video_streams = [s for s in media['streams'] if s.get('type') == 'video']
                        if video_streams:
                            vs = video_streams[0]
                            w, h = vs.get('width'), vs.get('height')
                            codec_str = (vs.get('codec') or '').upper()
                            fps = vs.get('fps')
                            res = '{}×{}'.format(w, h) if w and h else 'Unknown'
                            rec['metadata'] = '{} {}'.format(res, codec_str) if codec_str else res
                            rec['_width'] = w
                            rec['_height'] = h
                            rec['_codec'] = codec_str
                            rec['_fps'] = fps
                        rec['_duration'] = _format_duration(media.get('duration'))
                        rec['_bit_rate'] = media.get('bit_rate')

            elif mime.startswith('audio/'):
                rec['cat'] = 'audio'
                if filepath and os.path.isfile(filepath):
                    media = get_media_info(filepath, self, print_details=False)
                    if media and media.get('streams'):
                        audio_streams = [s for s in media['streams'] if s.get('type') == 'audio']
                        if audio_streams:
                            as_ = audio_streams[0]
                            codec_str = (as_.get('codec') or '').upper()
                            channels = as_.get('channels')
                            sample_rate = as_.get('sample_rate', '')

                            parts = []
                            if codec_str:
                                parts.append(codec_str)
                            if channels:
                                parts.append('{}ch'.format(channels))
                            if sample_rate:
                                try:
                                    sr = int(sample_rate)
                                    sr_str = '{:.1f} kHz'.format(sr / 1000) if sr >= 1000 else '{} Hz'.format(sr)
                                    parts.append(sr_str)
                                except (ValueError, TypeError):
                                    pass
                            rec['metadata'] = '/'.join(parts)

                            rec['_audio_codec'] = codec_str
                            rec['_channels'] = channels
                            rec['_sample_rate'] = sample_rate
                        rec['_duration'] = _format_duration(media.get('duration'))
                        rec['_bit_rate'] = media.get('bit_rate')

            else:
                ext = os.path.splitext(filename)[1].lstrip('.').upper() if '.' in filename else ''
                rec['metadata'] = ext or 'N/A'

            records.append(rec)

            # Update progress after each file
            self.update_progress(((idx + 1) / total) * 100.0)

        # Phase 2: render the final report (no heavy work, so no progress needed)
        md_lines = [
            '## Media Folder Info',
            '',
            f'**Folder:** `{folder.name}` ({self.folder_id})',
            '',
            f'**Files processed:** {len(records)}',
            '',
        ]

        self.trace("After Process Files")

        self.trace("Before Render")

        if self.mode == 'list':
            md_lines.extend(self._render_list_mode(records))
        else:
            md_lines.extend(self._render_detail_mode(records))

        self.trace("After Render")

        self.info('\n'.join(md_lines), _markdown=True)
        self.set_worked()

    def _render_detail_mode(self, records):
        lines = []

        for idx, rec in enumerate(records, 1):
            lines.extend([
                f'### {idx}. `{rec["filename"]}`',
                '',
                '| Property | Value |',
                '|---|---|',
                f'| Type | `{rec["mime"]}` |',
                f'| Size | {rec["size_str"]} |',
                f'| Last Modified | {rec["date_str"]} |',
            ])

            mime = rec['mime']

            if mime.startswith('image/'):
                mode_name = rec.get('_mode_name', '')
                width = rec.get('_width')
                height = rec.get('_height')
                fmt = rec.get('_fmt', 'Unknown')
                if width is not None and height is not None:
                    lines.extend([
                        '| Color Mode | `{}` |'.format(mode_name),
                        '| Resolution | **{}×{}** |'.format(width, height),
                        '| Format | `{}` |'.format(fmt.upper()),
                    ])

            elif mime.startswith('video/'):
                width = rec.get('_width')
                height = rec.get('_height')
                codec = rec.get('_codec', '')
                fps = rec.get('_fps')
                if width is not None and height is not None:
                    lines.extend([
                        '| Resolution | **{}×{}** |'.format(width, height),
                        '| Codec | `{}` |'.format(codec),
                    ])
                if fps:
                    lines.append('| Frame Rate | {} fps |'.format(fps))
                duration = rec.get('_duration')
                bit_rate = rec.get('_bit_rate')
                if duration:
                    lines.append('| Duration | {} |'.format(duration))
                if bit_rate:
                    lines.append('| Bit Rate | `{}` |'.format(bit_rate))

            elif mime.startswith('audio/'):
                codec = rec.get('_audio_codec', '')
                channels = rec.get('_channels')
                sample_rate = rec.get('_sample_rate')
                if codec:
                    lines.append('| Codec | `{}` |'.format(codec))
                if channels:
                    lines.append('| Channels | {} |'.format(channels))
                if sample_rate:
                    try:
                        sr = int(sample_rate)
                        if sr >= 1000:
                            lines.append('| Sample Rate | {:.1f} kHz |'.format(sr / 1000))
                        else:
                            lines.append('| Sample Rate | {} Hz |'.format(sr))
                    except (ValueError, TypeError):
                        pass
                duration = rec.get('_duration')
                bit_rate = rec.get('_bit_rate')
                if duration:
                    lines.append('| Duration | {} |'.format(duration))
                if bit_rate:
                    lines.append('| Bit Rate | `{}` |'.format(bit_rate))

        return lines

    def _render_list_mode(self, records):
        images = [r for r in records if r['cat'] == 'image']
        videos = [r for r in records if r['cat'] == 'video']
        audios = [r for r in records if r['cat'] == 'audio']

        # Non-media files (anything not image/video/audio)
        others = [r for r in records if r['cat'] == 'other']

        return self._format_table_sections(images, videos, audios, others)

    def _format_table_sections(self, images, videos, audios, others):
        lines = []

        for category_name, items in [('Images', images), ('Video', videos), ('Audio', audios), ('Other', others)]:
            if not items:
                continue
            lines.append('### {} ({} files)'.format(category_name, len(items)))
            lines.append('')
            lines.append('| Filename | Type | Size | Created | Metadata |')
            lines.append('|---|---|---|---|---|')
            for rec in items:
                meta_display = rec['metadata'] if rec['metadata'] else 'N/A'
                lines.append('| `{}` | `{}` | {} | {} | {} |'.format(rec['filename'], rec['mime'], rec['size_str'],
                                                                     rec['date_str'], meta_display))
            lines.append('')

        return lines
