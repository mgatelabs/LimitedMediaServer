import argparse
import os
import os.path
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask_sqlalchemy.session import Session

from db import MediaFolder
from feature_flags import MANAGE_MEDIA
from media_probe import get_file_formats
from media_queries import find_folder_by_id, find_files_in_folder, find_all_folders, find_file_by_id, insert_file
from media_utils import get_data_for_mediafile, get_preview_for_mediafile
from plugin_methods import plugin_select_arg, PLUGIN_VALUES_Y_N, plugin_media_folder_chooser_folder_arg
from plugin_system import ActionMediaFolderPlugin, ActionMediaPlugin
from text_utils import is_blank
from thread_utils import TaskWrapper


class CheckFolderIntegrityTask(ActionMediaFolderPlugin):
    """
    Check the integrify of a single folder
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'mediafix'

    def get_sort(self):
        return {'id': 'media_integrity_folder', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Check Integrity'

    def get_action_id(self):
        return 'action.integrity.folder'

    def get_action_icon(self):
        return 'verified'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(plugin_select_arg('Fix Issues', 'fix', 'n', PLUGIN_VALUES_Y_N, 'Correct issues?'))

        return result

    def process_action_args(self, args):
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        folder_id = args['folder_id']
        return CheckFolderIntegrity("Check Integrity", f'Check integrity of folder: {folder_id}', folder_id,
                                    args['fix'] == 'y', self.primary_path, self.archive_path)


class CheckAllFolderIntegrityTask(ActionMediaPlugin):
    """
    Check the integrify of every folder
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'mediafix'

    def get_sort(self):
        return {'id': 'media_integrity_all', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Check Integrity'

    def get_action_id(self):
        return 'action.integrity.all'

    def get_action_icon(self):
        return 'verified'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(plugin_select_arg('Fix Issues', 'fix', 'n', PLUGIN_VALUES_Y_N, 'Correct issues?'))

        result.append(plugin_select_arg('Check files', 'chkfiles', 'n', PLUGIN_VALUES_Y_N,
                                        'Verify files are attached to a record.'))

        result.append(plugin_media_folder_chooser_folder_arg("Restore Folder", 'restore_folder',
                                                             'Optional Folder to restore files to'))

        return result

    def process_action_args(self, args):
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        return CheckFolderIntegrity("Check Integrity", 'Check integrity for all folders', None, args['fix'] == 'y',
                                    self.primary_path, self.archive_path, args['chkfiles'] == 'y',
                                    args['restore_folder'])


class CheckFolderIntegrity(TaskWrapper):
    def __init__(self, name, description, folder_id: Optional[str], fix: bool, primary_path: str, archive_path: str,
                 check_folders: bool = False, restore_folder: str = ''):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.fix = fix
        self.primary_path = primary_path
        self.archive_path = archive_path
        self.check_folders = check_folders
        self.restore_folder = restore_folder

    def check_folder(self, folder: MediaFolder, db_session: Session):

        files = find_files_in_folder(folder.id, db_session=db_session)

        changed = False

        for file in files:

            expected_data_file = get_data_for_mediafile(file, self.primary_path, self.archive_path)
            expected_preview_file = get_preview_for_mediafile(file, self.primary_path)
            preview_exists = os.path.exists(expected_preview_file) and os.path.isfile(expected_preview_file)

            if os.path.exists(expected_data_file) and os.path.isfile(expected_data_file):
                # Date File exists, good
                pass
            else:
                # the file is missing,
                unexpected_data_file = get_data_for_mediafile(file, self.archive_path, self.primary_path)
                if os.path.exists(unexpected_data_file) and os.path.isfile(unexpected_data_file):
                    self.error(f'File {file.id} is on the wrong drive')
                    if self.fix:
                        changed = True
                        self.always(f'Flipping archive option for {file.id}')
                        file.archive = not file.archive
                else:
                    self.error(f'File {file.id} does not exist ({folder.name}:{file.filename})')
                    if self.fix:
                        changed = True
                        db_session.delete(file)
                        if preview_exists:
                            self.always(f'Erasing preview for {file.id}')
                            os.unlink(expected_preview_file)

            if preview_exists and file.preview:
                pass
            elif preview_exists and not file.preview:
                self.error(f'File {file.id} has a unlinked preview')
                if self.fix:
                    changed = True
                    self.always(f'Relinking preview for {file.id}')
                    file.preview = True
            elif not preview_exists and file.preview:
                self.error(f'File {file.id} is missing a preview ({folder.name}:{file.filename})')
                if self.fix:
                    changed = True
                    self.always(f'Removing preview for {file.id}')
                    file.preview = False

        if changed:
            self.set_worked()
            db_session.commit()

    def check_file_in_folder(self, folder_path: str, db_session: Session, is_archive: bool = False, percent: float = 0):
        self.percent = percent

        restore_folder_item = None
        if len(self.restore_folder) > 0:
            restore_folder_item = find_folder_by_id(self.restore_folder, db_session)

        with os.scandir(folder_path) as entries:
            for entry in entries:
                if entry.is_file():  # check if it's a file
                    self.trace(f"File: {entry.name}")
                    if entry.name.endswith(".dat"):
                        filename_without_ext = os.path.splitext(entry.name)[0]
                        found_file = find_file_by_id(filename_without_ext, db_session)
                        if found_file is None:
                            src_path = Path(folder_path) / entry.name
                            file_size = src_path.stat().st_size
                            created_time = datetime.fromtimestamp(src_path.stat().st_ctime)

                            format = get_file_formats(os.path.join(folder_path, entry.name), self)

                            self.warn(
                                f'Found unreferenced file: {filename_without_ext}, Size: {file_size}, Format: {format}')

                            if self.fix and format is not None and restore_folder_item is not None:

                                mime = 'text/plain'
                                if format == 'mp4':
                                    mime = 'video/mp4'

                                new_file = insert_file(restore_folder_item.id, filename_without_ext, mime, is_archive,
                                                       False,
                                                       file_size, created_time,
                                                       db_session, filename_without_ext)

                                if is_blank(new_file.id):
                                    self.critical('file does not have an ID')
                                    self.set_failure()
                                    return

                    if entry.name.endswith(".png"):
                        self.warn(f'Found leftover PNG preview {entry.name}')

    def run(self, db_session: Session):

        if is_blank(self.primary_path) or is_blank(self.archive_path):
            self.critical('This feature is not ready.  Please configure the app properties and restart the server.')

        if self.check_folders:
            self.check_file_in_folder(self.primary_path, db_session, False, 0)
            self.check_file_in_folder(self.archive_path, db_session, True, 50)
        elif is_blank(self.folder_id):
            all_folders = find_all_folders(db_session)

            total = len(all_folders)
            count = 0

            self.debug(f'Folder Count: {total}')

            for folder in all_folders:
                self.trace(f'Checking Folder: {folder.id}')

                count = count + 1
                self.update_progress((count / total) * 100.0)
                self.check_folder(folder, db_session)

        else:
            existing_row = find_folder_by_id(self.folder_id, db_session)
            if existing_row is None:
                self.critical('Folder not found in DB')
                self.set_failure()
                return

            self.check_folder(existing_row, db_session)
