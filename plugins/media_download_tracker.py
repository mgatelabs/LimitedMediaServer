import argparse
import base64
import json
import logging

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_MEDIA
from file_utils import is_valid_url
from media_queries import find_folder_by_id
from media_utils import get_folder_rating_checker, get_folder_group_checker
from plugin_methods import plugin_long_string_arg, plugin_select_arg, plugin_select_values, \
    plugin_media_folder_chooser_folder_arg
from plugin_system import ActionMediaFolderPlugin, ActionMediaPlugin
from plugins.media_download_file import DownloadFileJob
from plugins.media_download_m3u8 import DownloadM3u8Job
from plugins.media_download_m3u8_ex import DownloadM3u8JobEx
from text_utils import is_blank
from thread_utils import RunReport


class DownloadTrackerPlugin(ActionMediaFolderPlugin):
    """
    Import exported tracker extension payload (base64 JSON) and queue download jobs for each group item.
    """
    AI_QUICK_DESCRIPTION = ('Imports a payload exported from the Media Tracker browser extension and '
                            'queues a download job for every file it contains.')
    AI_LONG_DESCRIPTION = (
        'Takes the base64-encoded JSON payload produced by the Media Tracker browser extension '
        'and turns it into a set of download jobs targeting the currently-focused media folder. '
        'Each group in the payload becomes one or more downloads: HLS streams (m3u8_vtt and '
        'audio-only m3u8_audio) are downloaded as MP4 via the chosen M3u8 method (Advanced/Ex '
        'or Simple/ffmpeg), with companion .vtt subtitles for m3u8_vtt groups, while '
        'mp3/mp4/vtt/file groups are saved as direct files. '
        'The job also writes an import report noting any groups whose URLs or folders were '
        'invalid. Required arguments: Tracker Payload (the pasted base64 JSON). Location, M3u8 '
        'Method (default Advanced/Ex), and HTTP2 (default No) are optional. Runs against the '
        'selected folder as the default destination.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'dltracker'

    def get_sort(self):
        return {'id': 'media_dl.tracker', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Import from Media Tracker'

    def get_action_id(self):
        return 'action.download.tracker'

    def get_action_icon(self):
        return 'download'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(
            plugin_long_string_arg(
                'Tracker Payload',
                'payload',
                'Paste the base64-encoded JSON exported from the Media Tracker browser extension here.',
                'com'
            )
        )

        result.append(
            plugin_select_arg(
                'Location', 'dest', 'primary',
                plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'),
                '', 'media'
            )
        )

        result.append(
            plugin_select_arg(
                'M3u8 Method', 'm3u8_meth', 'ex',
                plugin_select_values('Advanced (Ex)', 'ex', 'Simple (ffmpeg)', 'simple'),
                'Which M3u8 downloader to use?', adv='Y'
            )
        )

        result.append(
            plugin_select_arg('HTTP2', 'usehttp2', '0',
                              plugin_select_values('No', '0', 'Yes', '1'), 'Use HTTP2 for Faster Downloads?', 'media')
        )

        return result

    def process_action_args(self, args):
        return _process_tracker_args(args, require_folder=True)

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        return _create_tracker_task(args, self.primary_path, self.archive_path, self.temp_path)


def _process_tracker_args(args, require_folder: bool):
    results = []

    if 'payload' not in args or is_blank(args['payload']):
        results.append('payload is required')
        return results

    raw = args['payload'].strip()

    try:
        decoded = base64.b64decode(raw).decode('utf-8')
        groups = json.loads(decoded)
    except Exception as e:
        logging.exception('Failed to decode tracker payload')
        results.append(f'payload is not valid base64 JSON: {e}')
        return results

    if not isinstance(groups, list) or len(groups) == 0:
        results.append('payload decoded but contains no groups')
        return results

    args['_groups'] = groups

    if 'dest' not in args or is_blank(args['dest']):
        results.append('dest is required')
    elif args['dest'] not in ('primary', 'archive'):
        results.append('Invalid dest value')

    if 'usehttp2' not in args or is_blank(args['usehttp2']):
        results.append('usehttp2 is required')
    elif not (args['usehttp2'] == '0' or args['usehttp2'] == '1'):
        results.append('Invalid http2 value')

    if require_folder and ('folder_id' not in args or is_blank(args['folder_id'])):
        results.append('folder_id is required')

    return results if results else None


def _create_tracker_task(args, primary_path, archive_path, temp_path):
    groups = args['_groups']
    dest = args['dest']
    default_folder_id = args.get('folder_id') or ''
    m3u8_meth = args.get('m3u8_meth', 'ex')
    user_details = args.get('_user_details')

    folder_rating_checker = get_folder_rating_checker(user_details) if user_details else None
    folder_group_checker = get_folder_group_checker(user_details) if user_details else None

    return _build_tracker_jobs(
        groups, dest, default_folder_id, m3u8_meth,
        folder_rating_checker, folder_group_checker,
        primary_path, archive_path, temp_path, args['usehttp2'] == '1'
    )


def _build_tracker_jobs(groups, dest, default_folder_id, m3u8_meth,
                        folder_rating_checker, folder_group_checker,
                        primary_path, archive_path, temp_path, useHttp2: bool = False):
    m3u8_jobs = []
    vtt_jobs = []
    file_jobs = []
    entry_jobs = []

    for group in groups:
        try:
            group_name = group.get('n', 'unknown')
            group_type = group.get('t', 'file')
            items = group.get('items', [])
            group_folder_id = group.get('folder_id', '').strip() if group.get('folder_id') else ''

            report = RunReport('Import Report', f'Tracker import report for group {group_name}')

            # Resolve folder: use group-level folder_id if present and accessible
            folder_id = default_folder_id
            if group_folder_id:
                group_folder_row = find_folder_by_id(group_folder_id)
                if group_folder_row is None:
                    report.add_warn(f'folder_id {group_folder_id!r} not found — using default folder')
                elif folder_rating_checker and not folder_rating_checker(group_folder_row):
                    report.add_warn(f'folder_id {group_folder_id!r} access denied (rating) — using default folder')
                elif folder_group_checker and not folder_group_checker(group_folder_row):
                    report.add_warn(f'folder_id {group_folder_id!r} access denied (group) — using default folder')
                else:
                    folder_id = group_folder_id

            if not folder_id:
                report.add_error(f'No folder available for group {group_name!r} — skipping all jobs for this group')
                m3u8_jobs.append(report)
                continue

            if group_type in ('m3u8_vtt', 'm3u8_audio'):
                stream_items = [it for it in items if it.get('t') == 'STREAM']
                # Audio-only HLS groups (m3u8_audio) carry no subtitle items
                subtitle_items = [it for it in items if it.get('t') == 'SUBTITLE'] if group_type == 'm3u8_vtt' else []

                stream_urls = []
                stream_origins = []
                for it in stream_items:
                    url = it.get('url', '').strip()
                    if not is_valid_url(url):
                        report.add_warn(f'Invalid STREAM url {url!r} — skipping item')
                        continue
                    origin = it.get('origin', '').strip()
                    stream_urls.append(url)
                    stream_origins.append(origin if is_valid_url(origin) else url)

                sub_urls = []
                sub_origins = []
                for it in subtitle_items:
                    url = it.get('url', '').strip()
                    if not is_valid_url(url):
                        report.add_warn(f'Invalid SUBTITLE url {url!r} — skipping item')
                        continue
                    origin = it.get('origin', '').strip()
                    sub_urls.append(url)
                    sub_origins.append(origin if is_valid_url(origin) else url)

                stream_url = ';'.join(stream_urls)
                stream_origin = ';'.join(stream_origins)
                sub_url = ';'.join(sub_urls)
                sub_origin = ';'.join(sub_origins)

                filename = group_name + '.mp4'

                if stream_url:
                    if m3u8_meth == 'ex':
                        m3u8_jobs.append(
                            DownloadM3u8JobEx('Download M3u8', f'Downloading {filename} from M3u8 ({folder_id})',
                                              folder_id, filename, stream_url,
                                              stream_origin, dest,
                                              primary_path, archive_path, temp_path, useHttp2)
                        )
                    else:
                        m3u8_jobs.append(
                            DownloadM3u8Job(
                                'Download M3u8',
                                f'Downloading {filename} from M3u8 ({folder_id})',
                                folder_id, filename, stream_url,
                                dest, primary_path, archive_path, temp_path
                            )
                        )
                else:
                    report.add_warn(f'No valid STREAM url found — skipping m3u8 job for {filename}')

                vtt_filename = group_name + '.vtt'

                if sub_url:
                    #  Set the priority for VTT files higher, so they all come down first
                    vtt_jobs.append(
                        DownloadFileJob(
                            'Download VTT',
                            f'Downloading {vtt_filename} from Web ({folder_id})',
                            folder_id, vtt_filename, sub_url,
                            sub_origin,
                            dest, 'gcurl',
                            primary_path, archive_path, temp_path, 1
                        )
                    )
                elif group_type == 'm3u8_vtt':
                    report.add_warn(f'No valid SUBTITLE url found — skipping vtt job for {vtt_filename}')
            elif group_type == 'mp3':
                # file group — each item is a standalone file download
                for item in items:
                    item_url = item.get('url', '').strip()
                    item_origin = item.get('origin', '').strip()

                    if not is_valid_url(item_url):
                        report.add_warn(f'Item has invalid url {item_url!r} — skipping')
                        continue

                    file_jobs.append(
                        DownloadFileJob(
                            'Download MP3',
                            f'Downloading {group_name}.mp3 from Web ({folder_id})',
                            folder_id, group_name + '.mp3', item_url,
                            item_origin if is_valid_url(item_origin) else item_url,
                            dest, 'system',
                            primary_path, archive_path, temp_path
                        )
                    )
            elif group_type == 'mp4':
                # file group — each item is a standalone file download
                for item in items:
                    item_url = item.get('url', '').strip()
                    item_origin = item.get('origin', '').strip()

                    if not is_valid_url(item_url):
                        report.add_warn(f'Item has invalid url {item_url!r} — skipping')
                        continue

                    file_jobs.append(
                        DownloadFileJob(
                            'Download MP4',
                            f'Downloading {group_name}.mp4 from Web ({folder_id})',
                            folder_id, group_name + '.mp4', item_url,
                            item_origin if is_valid_url(item_origin) else item_url,
                            dest, 'system',
                            primary_path, archive_path, temp_path
                        )
                    )
            elif group_type == 'vtt':
                # file group — each item is a standalone file download
                for item in items:
                    item_url = item.get('url', '').strip()
                    item_origin = item.get('origin', '').strip()

                    if not is_valid_url(item_url):
                        report.add_warn(f'Item has invalid url {item_url!r} — skipping')
                        continue

                    file_jobs.append(
                        DownloadFileJob(
                            'Download VTT',
                            f'Downloading {group_name}.vtt from Web ({folder_id})',
                            folder_id, group_name + '.vtt', item_url,
                            item_origin if is_valid_url(item_origin) else item_url,
                            dest, 'system',
                            primary_path, archive_path, temp_path
                        )
                    )
            else:
                # file group — each item is a standalone file download
                for item in items:
                    item_url = item.get('url', '').strip()
                    item_origin = item.get('origin', '').strip()

                    if not is_valid_url(item_url):
                        report.add_warn(f'Item has invalid url {item_url!r} — skipping')
                        continue

                    file_jobs.append(
                        DownloadFileJob(
                            'Download File',
                            f'Downloading {group_name} from Web ({folder_id})',
                            folder_id, group_name, item_url,
                            item_origin if is_valid_url(item_origin) else item_url,
                            dest, 'system',
                            primary_path, archive_path, temp_path
                        )
                    )

            if report.has_entries():
                entry_jobs.append(report)

        except Exception:
            logging.exception('tracker: unexpected error processing group %r', group)

    return entry_jobs + vtt_jobs + file_jobs + m3u8_jobs


class DownloadTrackerMediaPlugin(ActionMediaPlugin):
    """
    Global (non-folder-scoped) variant of DownloadTrackerPlugin.
    Accessible from the main media menu; the user picks a fallback folder via a folder chooser.
    """
    AI_QUICK_DESCRIPTION = ('Standalone version of the Media Tracker import: paste the exported '
                            'payload and pick a fallback folder for items that do not name one.')
    AI_LONG_DESCRIPTION = (
        'The global, not-folder-scoped version of the Media Tracker import. It accepts the same '
        'base64-encoded JSON payload exported by the Media Tracker browser extension and queues '
        'the same kinds of downloads (HLS streams as MP4, including audio-only m3u8_audio '
        'groups, plus .vtt subtitles for m3u8_vtt groups, direct files for mp3/mp4/vtt/file '
        'groups, plus an import report for '
        'invalid entries). Unlike the folder-bound variant it is reachable from the main media '
        'menu and requires a Default Folder that is used whenever a payload group does not '
        'specify (or does not have access to) its own folder. Per-group folder access is checked '
        'against the calling user\'s ratings and groups. Required arguments: Tracker Payload and '
        'Default Folder. Location, M3u8 Method (default Advanced/Ex), and HTTP2 (default No) '
        'are optional.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'dltracker'

    def get_sort(self):
        return {'id': 'media_dl.tracker.global', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Import from Media Tracker'

    def get_action_id(self):
        return 'action.download.tracker.global'

    def get_action_icon(self):
        return 'download'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(
            plugin_long_string_arg(
                'Tracker Payload',
                'payload',
                'Paste the base64-encoded JSON exported from the Media Tracker browser extension here.',
                'com'
            )
        )

        result.append(
            plugin_media_folder_chooser_folder_arg(
                'Default Folder', 'folder_id',
                'Fallback folder used when a group does not specify its own folder.'
            )
        )

        result.append(
            plugin_select_arg(
                'Location', 'dest', 'primary',
                plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'),
                '', 'media'
            )
        )

        result.append(
            plugin_select_arg(
                'M3u8 Method', 'm3u8_meth', 'ex',
                plugin_select_values('Advanced (Ex)', 'ex', 'Simple (ffmpeg)', 'simple'),
                'Which M3u8 downloader to use?', adv='Y'
            )
        )

        result.append(
            plugin_select_arg('HTTP2', 'usehttp2', '0',
                              plugin_select_values('No', '0', 'Yes', '1'), 'Use HTTP2 for Faster Downloads?', 'media')
        )

        return result

    def process_action_args(self, args):
        return _process_tracker_args(args, require_folder=False)

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        return _create_tracker_task(args, self.primary_path, self.archive_path, self.temp_path)
