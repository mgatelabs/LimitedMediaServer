import argparse
import os.path

import paramiko
from flask import current_app
from flask_sqlalchemy.session import Session

import series_tools
from feature_flags import MANAGE_APP, RESERVED_3, RESERVED_4, RESERVED_1
from plugin_system import ActionPlugin
from thread_utils import TaskWrapper


class SyncVideos(ActionPlugin):
    AI_QUICK_DESCRIPTION = ('Pushes every video series from the local server to a remote host '
                            'over SFTP, uploading only the files the remote folder does not '
                            'already have.')
    AI_LONG_DESCRIPTION = (
        'One-way outbound sync of the video library (the SERIES_OUT path and its VIDEO_ARCHIVE '
        'counterpart) to a configured remote server. The remote connection is not a task '
        'argument: username, password, host, port, and remote path come from the command-line '
        'flags (or app configuration), so the AI action itself takes no action-specific '
        'arguments. For each series found in the local library, a sync task is created that '
        'connects via SFTP, creates the remote series folder if missing, and compares file '
        'names: files present locally (in both the series and archive locations) but missing on '
        'the remote are uploaded, while files already on the remote are skipped. Nothing is ever '
        'downloaded, deleted, or renamed on the remote; a cancel request stops the transfer '
        'loop. Success reports upload and skip counts.')

    def __init__(self):
        super().__init__()
        self.username = ''
        self.password = ''
        self.port = 22
        self.host = ''
        self.path = ''

    def get_sort(self):
        return {'id': 'sync', 'sequence': 0}

    def add_args(self, parser: argparse):
        parser.add_argument("-ssh_username", type=str, help="SSH Username", required=False)
        parser.add_argument("-ssh_password", type=str, help="SSH Password", required=False)
        parser.add_argument("-ssh_port", type=int, help="SSH Port", required=False)
        parser.add_argument("-ssh_host", type=str, help="SSH Host", required=False)
        parser.add_argument("-ssh_path", type=str, help="SSH Path", required=False)

    def use_args(self, args):
        self.username = args.ssh_username
        self.password = args.ssh_password
        self.host = args.ssh_host
        self.port = args.ssh_port
        self.path = args.ssh_path

    def get_action_name(self):
        return 'Sync Content'

    def get_action_id(self):
        return 'action.sync.folders'

    def get_action_icon(self):
        return 'sync_alt'

    def get_action_args(self):
        return []

    def process_action_args(self, args):
        return None

    def get_feature_flags(self):
        return MANAGE_APP | RESERVED_3 | RESERVED_1 | RESERVED_4

    def get_category(self):
        return 'series'

    def is_ready(self):
        return self.username is not None and len(self.username) > 0 and self.password is not None and len(self.password) > 0 and self.host is not None and len(self.host) > 0 and self.path is not None and len(self.path) > 0

    def create_task(self, db_session: Session, args):
        video_series = current_app.config['SERIES_OUT']
        video_archive = current_app.config['VIDEO_ARCHIVE']

        work_data = series_tools.get_library_items(video_series, True, True)

        result = []

        for work in work_data:
            series_id = work['id']

            result.append(
                CreateSyncFolderRequest(series_id, self.username, self.password, self.host, self.port, self.path,
                                        video_series,
                                        video_archive, series_id))

        return result


class ProgressTracker:
    def __init__(self, logger: TaskWrapper):
        self.logger = logger

    def update(self, bytes_transferred, total_size):
        progress = (bytes_transferred / total_size) * 100
        self.logger.update_percent(progress)


class CreateSyncFolderRequest(TaskWrapper):
    def __init__(self, description: str, username: str, password: str, host: str, port, host_path: str, video_path: str,
                 archive_folder: str, folder_name: str):
        super().__init__("Sync", description)
        self.username = username
        self.password = password
        self.port = port
        self.host = host
        self.host_path = host_path
        self.video_path = video_path
        self.archive_folder = archive_folder
        self.folder_name = folder_name

    def run(self, db_session):
        try:

            # Connect to SSH server
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.host, port=self.port, username=self.username, password=self.password)

            folder_source = os.path.join(self.video_path, self.folder_name)
            folder_archive = os.path.join(self.archive_folder, self.folder_name)
            folder_dest = os.path.join(self.host_path, self.folder_name)

            # List files in destination folder
            sftp = ssh.open_sftp()

            try:
                sftp.listdir(folder_dest)
            except IOError:
                sftp.mkdir(folder_dest)

            dest_files = sftp.listdir(folder_dest)

            skip_count = 0
            upload_count = 0

            source_files = []
            archive_files = []

            if os.path.isdir(folder_source):
                source_files = sorted(os.listdir(folder_source))

            if os.path.isdir(folder_archive):
                archive_files = sorted(os.listdir(folder_archive))

            total_files = len(source_files) + len(archive_files)

            current_index = 0

            for file_name in source_files:

                current_index = current_index + 1

                if self.is_cancelled:
                    break

                self.update_progress((current_index / total_files) * 100.0)

                source_path = os.path.join(folder_source, file_name)
                dest_path = os.path.join(folder_dest, file_name)
                # Check if file already exists in destination
                if file_name not in dest_files:
                    # Transfer file via SFTP
                    self.info('Uploading: ' + file_name)
                    self.set_worked()
                    upload_count = upload_count + 1
                    sftp.put(source_path, dest_path, callback=ProgressTracker(self).update)
                else:
                    skip_count = skip_count + 1

            for file_name in archive_files:

                current_index = current_index + 1

                if self.is_cancelled:
                    break

                self.update_progress((current_index / total_files) * 100.0)

                source_path = os.path.join(folder_archive, file_name)
                dest_path = os.path.join(folder_dest, file_name)
                # Check if file already exists in destination
                if file_name not in dest_files:
                    # Transfer file via SFTP
                    self.info('Uploading: ' + file_name)
                    upload_count = upload_count + 1
                    sftp.put(source_path, dest_path)
                else:
                    skip_count = skip_count + 1

            self.debug('Upload Count: ' + str(upload_count))
            self.debug('Skip Count: ' + str(skip_count))
            self.info("Sync Finished")

            sftp.close()
            ssh.close()

        except Exception as e:
            self.critical(str(e))
            self.set_failure(True)
