import argparse

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_MEDIA
from media_queries import find_folder_by_id, find_files_in_folder_with_mime, \
    find_files_in_two_folders_with_mime
from media_utils import clean_files_for_mediafile
from plugin_system import ActionMediaFolderPlugin, plugin_select_arg, plugin_select_values, \
    plugin_media_folder_chooser_folder_arg
from text_utils import is_blank, remove_start_digits_pattern, clean_string, is_not_blank
from thread_utils import TaskWrapper


class CleanFolderTask(ActionMediaFolderPlugin):
    """
    Remove files that don't exist
    """
    def __init__(self):
        super().__init__()


    def get_sort(self):
        return {'id': 'media_duplicate_music_folder', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'De-Duplicate Music'

    def get_action_id(self):
        return 'action.deduplicate.music'

    def get_action_icon(self):
        return 'music_note'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(plugin_select_arg('Mode', 'mode', 'dupes', plugin_select_values('De-Duplicate', 'dupes', 'De-Duplicate (Artist - Title)', 'dupes_artist_title', 'Font Numbers', 'front_numbers'), 'Which action to take?'))

        result.append(
            plugin_media_folder_chooser_folder_arg('Other Folder', 'other_folder_id',
                                                        'Another folder to compare to when de-duplicating.'))
        return result

    def process_action_args(self, args):
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        return CleanFolder("De-Dupe", 'De-Duplicate Music Folder ' + args['folder_id'], args['folder_id'], args['other_folder_id'], args['mode'], self.primary_path, self.archive_path)


class CleanFolder(TaskWrapper):
    def __init__(self, name, description, folder_id, other_folder_id, mode, primary_path, archive_path):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.other_folder_id = other_folder_id
        self.mode = mode
        self.primary_path = primary_path
        self.archive_path = archive_path

    def run(self, db_session: Session):

        if is_blank(self.primary_path):
            self.critical('This feature is not ready.  Please configure the app properties and restart the server.')

        existing_folder_row = find_folder_by_id(self.folder_id, db_session)
        if existing_folder_row is None:
            self.critical('Folder not found in DB')
            self.set_failure()
            return



        if is_not_blank(self.other_folder_id):

            existing_folder_row = find_folder_by_id(self.other_folder_id, db_session)
            if existing_folder_row is None:
                self.critical('Folder not found in DB')
                self.set_failure()
                return

            files = find_files_in_two_folders_with_mime(self.folder_id, self.other_folder_id, 'audio/mpeg', db_session)
        else:
            files = find_files_in_folder_with_mime(self.folder_id, 'audio/mpeg', db_session)

        self.info(f'Looking through {len(files)} files')

        if self.mode == 'front_numbers':

            for file in files:
                new_name = remove_start_digits_pattern(file.filename)
                if new_name != file.filename:
                    self.info(f'Removing Prefix from {file.filename}')

        elif self.mode == 'dupes':

            pre_filename = ''
            erased = False
            count = 0

            for file in files:
                act = False
                if pre_filename == file.filename:
                    act = True
                pre_filename = file.filename
                if act:
                    clean_files_for_mediafile(file, self.primary_path, self.archive_path)
                    self.info(f'Erasing : {file.filename}')
                    db_session.delete(file)
                    erased = True
                    count = count + 1

            if erased:
                self.set_worked()
                db_session.commit()

            self.info(f'Erased {count} files')

        elif self.mode == 'dupes_artist_title':

            pre_filename = ''
            erased = False
            count = 0

            for file in files:
                act = False

                index = file.filename.rfind('[')

                if index != -1:
                    result = clean_string(file.filename[:index]).lower()
                else:
                    result = clean_string(file.filename).lower()

                if pre_filename == result:
                    act = True
                pre_filename = result
                if act:
                    clean_files_for_mediafile(file, self.primary_path, self.archive_path)
                    self.info(f'Erasing : {file.filename}')
                    db_session.delete(file)
                    erased = True
                    count = count + 1

            if erased:
                self.set_worked()
                db_session.commit()

            self.info(f'Erased {count} files')
        # for file in files:
        #
        #
        #
        #
        #     if file.archive:
        #         dest_path = os.path.join(self.archive_path, file.id + '.dat')
        #     else:
        #        dest_path = os.path.join(self.primary_path, file.id + '.dat')
        #
        #     if not os.path.exists(dest_path):
        #         self.info(f'Removing file {file.id}')
        #         db_session.delete(file)
        #         db_session.commit()
