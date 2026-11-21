import argparse
import logging
import os.path
import re

import paramiko

from flask_sqlalchemy.session import Session

from app_properties import AppPropertyDefinition
from app_utils import value_is_integer, value_is_between_int_x_y, value_is_hostname
from constants import MEDIA_FOLDER_KEY_PURPOSE_DEFAULT
from feature_flags import MANAGE_MEDIA
from media_queries import find_all_folders, find_files_in_folder
from media_utils import get_data_for_mediafile
from plugin_system import ActionMediaPlugin
from text_utils import is_not_blank, is_blank
from thread_utils import TaskWrapper

PROPERTY_PLUGIN_MEDIA_SYNC_HOST = 'PLUGIN.MEDIA.SYNC.SSH.HOST'
PROPERTY_PLUGIN_MEDIA_SYNC_USER = 'PLUGIN.MEDIA.SYNC.SSH.USER'
PROPERTY_PLUGIN_MEDIA_SYNC_PASSWORD = 'PLUGIN.MEDIA.SYNC.SSH.PASSWORD'
PROPERTY_PLUGIN_MEDIA_SYNC_PORT = 'PLUGIN.MEDIA.SYNC.SSH.PORT'

# The MediaFolderKeyValue key that holds the per-folder remote destination path.
FOLDER_KEY_SSH_PATH = 'SSH_PATH'

# The MediaFolderKeyValue key that holds the per-folder sync filter: semicolon-delimited
# regular expressions. When present and non-blank, only files whose display name matches
# at least one expression are synced.
FOLDER_KEY_SSH_REGEX = 'SSH_REGEX'


def compile_ssh_regex_patterns(value, folder_name):
    """Compile the semicolon-delimited SSH_REGEX value into a list of regex patterns.

    Invalid expressions are logged and skipped so one bad pattern does not stop the
    rest of the folder from syncing. Returns None when the value is blank, which means
    no filtering (sync all files).
    """
    if is_blank(value):
        return None

    patterns = []
    for expression in value.split(';'):
        expression = expression.strip()
        if is_blank(expression):
            continue
        try:
            patterns.append(re.compile(expression))
        except re.error:
            logging.error('Skipping invalid SSH_REGEX expression for folder '
                          f'{folder_name}: {expression}')

    return patterns


class SyncMediaFolders(ActionMediaPlugin):
    AI_QUICK_DESCRIPTION = ('One-way outbound SFTP sync of every media folder that has an SSH_PATH '
                            'key value, uploading only the files the remote folder is missing. '
                            'Optionally filter which files are synced with the SSH_REGEX key.')
    AI_LONG_DESCRIPTION = (
        'One-way outbound sync of the media library to a single remote server over SFTP. The '
        'remote connection is configured out-of-band in the server properties: SSH host, user, '
        'password and port (PLUGIN.MEDIA.SYNC.SSH.*), so the action takes no arguments. Each '
        'media folder independently decides where its files land by storing an SSH_PATH key '
        'value (MediaFolderKeyValue, purpose = default) holding the destination path on the '
        'remote server; folders without that key are skipped. For every folder that has an '
        'SSH_PATH, a sync task is created that connects via SFTP, creates the remote folder if '
        'missing, compares file names, and uploads the files present locally but missing on the '
        'remote while skipping files already present. A folder may also store an SSH_REGEX key '
        'value holding semicolon-delimited regular expressions; when present, only files whose '
        'display name matches at least one expression are synced (invalid expressions are '
        'logged and skipped). Media files are named by their display file name; duplicate '
        'names within a folder are disambiguated. Nothing is ever '
        'downloaded, deleted, or renamed on the remote; a cancel request stops the transfer '
        'loop. Success reports upload and skip counts.')

    def __init__(self):
        super().__init__()
        self.username = ''
        self.password = ''
        self.port = 22
        self.host = ''

    def get_sort(self):
        return {'id': 'media_sync_folders', 'sequence': 0}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Sync Media Folders'

    def get_action_id(self):
        return 'action.sync.media.folders'

    def get_action_icon(self):
        return 'sync_alt'

    def get_action_args(self):
        return []

    def process_action_args(self, args):
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def get_category(self):
        return 'media'

    def absorb_config(self, config):
        super().absorb_config(config)

        if PROPERTY_PLUGIN_MEDIA_SYNC_HOST in config and is_not_blank(config[PROPERTY_PLUGIN_MEDIA_SYNC_HOST]):
            self.host = config[PROPERTY_PLUGIN_MEDIA_SYNC_HOST]
        if PROPERTY_PLUGIN_MEDIA_SYNC_USER in config and is_not_blank(config[PROPERTY_PLUGIN_MEDIA_SYNC_USER]):
            self.username = config[PROPERTY_PLUGIN_MEDIA_SYNC_USER]
        if PROPERTY_PLUGIN_MEDIA_SYNC_PASSWORD in config and is_not_blank(config[PROPERTY_PLUGIN_MEDIA_SYNC_PASSWORD]):
            self.password = config[PROPERTY_PLUGIN_MEDIA_SYNC_PASSWORD]
        if PROPERTY_PLUGIN_MEDIA_SYNC_PORT in config and is_not_blank(config[PROPERTY_PLUGIN_MEDIA_SYNC_PORT]):
            try:
                self.port = int(config[PROPERTY_PLUGIN_MEDIA_SYNC_PORT])
            except ValueError:
                self.port = 22

    def get_properties(self) -> list[AppPropertyDefinition]:
        result = super().get_properties()

        result.append(AppPropertyDefinition(PROPERTY_PLUGIN_MEDIA_SYNC_HOST, '',
                                            'Remote host (hostname or IP address) to sync media folders to '
                                            'over SFTP. Restart server if changed.',
                                            [value_is_hostname]))
        result.append(AppPropertyDefinition(PROPERTY_PLUGIN_MEDIA_SYNC_USER, '',
                                            'SSH username used to connect to the remote media sync host. '
                                            'Restart server if changed.',
                                            []))
        result.append(AppPropertyDefinition(PROPERTY_PLUGIN_MEDIA_SYNC_PASSWORD, '',
                                            'SSH password used to connect to the remote media sync host. '
                                            'Restart server if changed.',
                                            []))
        result.append(AppPropertyDefinition(PROPERTY_PLUGIN_MEDIA_SYNC_PORT, '22',
                                            'SSH port used to connect to the remote media sync host. '
                                            'Restart server if changed.',
                                            [value_is_integer, value_is_between_int_x_y(1, 65535)]))

        return result

    def is_ready(self):
        return (is_not_blank(self.username) and is_not_blank(self.password)
                and is_not_blank(self.host) and self.port)

    def create_task(self, db_session: Session, args):
        result = []

        for folder in find_all_folders(db_session):
            # Only folders that have configured a destination path participate in the sync
            keys = folder.get_keys_for_purpose(MEDIA_FOLDER_KEY_PURPOSE_DEFAULT)
            remote_path = keys.get(FOLDER_KEY_SSH_PATH)
            if is_blank(remote_path):
                continue

            files = find_files_in_folder(folder.id, db_session=db_session)

            # Optional per-folder filter: only sync files whose display name matches
            # at least one of the semicolon-delimited SSH_REGEX expressions.
            patterns = compile_ssh_regex_patterns(keys.get(FOLDER_KEY_SSH_REGEX), folder.name)

            # Build the (local_path, remote_name) list, disambiguating duplicate file names
            # so two local files never overwrite the same remote file.
            file_list = []
            used_names = set()
            for f in files:
                local_path = get_data_for_mediafile(f, self.primary_path, self.archive_path)
                name = f.filename if is_not_blank(f.filename) else f.id

                if patterns is not None:
                    if not any(p.search(name) for p in patterns):
                        continue

                if name in used_names:
                    stem, ext = os.path.splitext(name)
                    n = 1
                    while f'{stem}_{n}{ext}' in used_names:
                        n = n + 1
                    name = f'{stem}_{n}{ext}'
                used_names.add(name)

                file_list.append((local_path, name))

            result.append(SyncMediaFolderJob('MediaSync', f'Sync folder: {folder.name}',
                                             self.username, self.password, self.host, self.port,
                                             remote_path, file_list))

        return result


class ProgressTracker:
    def __init__(self, logger: TaskWrapper):
        self.logger = logger

    def update(self, bytes_transferred, total_size):
        progress = (bytes_transferred / total_size) * 100
        self.logger.update_percent(progress)


class SyncMediaFolderJob(TaskWrapper):
    def __init__(self, name: str, description: str, username: str, password: str, host: str, port,
                 remote_path: str, files: list):
        super().__init__(name, description)
        self.username = username
        self.password = password
        self.port = port
        self.host = host
        self.remote_path = remote_path
        self.files = files  # list of (local_path, remote_name)

    def run(self, db_session):
        ssh = None
        sftp = None
        try:

            # Connect to SSH server
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.host, port=self.port, username=self.username, password=self.password)

            # List files in destination folder, creating it if missing
            sftp = ssh.open_sftp()

            try:
                sftp.listdir(self.remote_path)
            except IOError:
                sftp.mkdir(self.remote_path)

            dest_files = set(sftp.listdir(self.remote_path))

            skip_count = 0
            upload_count = 0

            total_files = len(self.files)
            current_index = 0

            for local_path, remote_name in self.files:
                current_index = current_index + 1

                if self.is_cancelled:
                    break

                self.update_progress((current_index / total_files) * 100.0 if total_files > 0 else 100.0)

                if not os.path.isfile(local_path):
                    self.info('Skipping missing local file: ' + remote_name)
                    continue

                # Check if file already exists in destination
                if remote_name not in dest_files:
                    # Transfer file via SFTP
                    self.info('Uploading: ' + remote_name)
                    self.set_worked()
                    upload_count = upload_count + 1
                    sftp.put(local_path, os.path.join(self.remote_path, remote_name),
                             callback=ProgressTracker(self).update)
                else:
                    skip_count = skip_count + 1

            self.debug('Upload Count: ' + str(upload_count))
            self.debug('Skip Count: ' + str(skip_count))
            self.info("Sync Finished")

        except Exception as e:
            self.critical(str(e))
            self.set_failure(True)
        finally:
            if sftp is not None:
                try:
                    sftp.close()
                except Exception:
                    pass
            if ssh is not None:
                try:
                    ssh.close()
                except Exception:
                    pass
