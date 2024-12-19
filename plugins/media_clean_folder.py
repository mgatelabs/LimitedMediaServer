import argparse
import os
import os.path
from typing import Optional

from flask_sqlalchemy.session import Session

from db import MediaFolder
from feature_flags import MANAGE_MEDIA
from media_queries import find_folder_by_id, find_files_in_folder, find_all_folders
from media_utils import get_data_for_mediafile, get_preview_for_mediafile
from plugin_system import ActionMediaFolderPlugin, ActionMediaPlugin
from plugin_methods import plugin_select_arg, PLUGIN_VALUES_Y_N
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
        return CheckFolderIntegrity("Check Integrity", f'Check integrity of folder: {folder_id}', folder_id, args['fix'] == 'y',
                                    self.primary_path,
                                    self.archive_path)


class CheckAllFolderIntegrityTask(ActionMediaPlugin):
    """
    Check the integrify of every folder
    """

    def __init__(self):
        super().__init__()

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

        return result

    def process_action_args(self, args):
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        return CheckFolderIntegrity("Check Integrity", 'Check integrity for all folders', None, args['fix'] == 'y',
                                    self.primary_path,
                                    self.archive_path)


class CheckFolderIntegrity(TaskWrapper):
    def __init__(self, name, description, folder_id: Optional[str], fix: bool, primary_path: str, archive_path: str):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.fix = fix
        self.primary_path = primary_path
        self.archive_path = archive_path

    def check_folder(self, folder: MediaFolder, db_session: Session):

        files = find_files_in_folder(self.folder_id, db_session=db_session)

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
                    self.error(f'File {file.id} does not exist')
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
                self.error(f'File {file.id} is missing a preview')
                if self.fix:
                    changed = True
                    self.always(f'Removing preview for {file.id}')
                    file.preview = False

        if changed:
            self.set_worked()
            db_session.commit()

    def run(self, db_session: Session):

        if is_blank(self.primary_path) or is_blank(self.archive_path):
            self.critical('This feature is not ready.  Please configure the app properties and restart the server.')

        if is_blank(self.folder_id):
            all_folders = find_all_folders(db_session)

            total = len(all_folders)
            count = 0

            for folder in all_folders:
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
