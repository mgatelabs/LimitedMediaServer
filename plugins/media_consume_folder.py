import argparse
import os.path
from datetime import datetime

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_MEDIA
from media_queries import find_folder_by_id, insert_file
from media_utils import get_data_for_mediafile
from plugin_methods import plugin_select_arg, plugin_select_values
from plugin_system import ActionMediaFolderPlugin
from text_utils import is_blank, clean_string
from thread_utils import TaskWrapper

import os
import shutil
import mimetypes
from pathlib import Path


class ConsumeForFolderPlugin(ActionMediaFolderPlugin):
    """
    Import files from a folder into the media server.
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'medimport'

    def get_sort(self):
        return {'id': 'media_consume_folder', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Import Folder'

    def get_action_id(self):
        return 'action.consume.folder'

    def get_action_icon(self):
        return 'publish'

    def get_action_args(self):
        result = super().get_action_args()
        result.append({
            "name": "Folder",
            "id": "folder",
            "type": "string",
            "description": "The local folder to import into this folder.",
            "values": []
        })
        result.append(plugin_select_arg('Location', 'dest', 'primary',
                              plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'), '', 'media'))
        return result

    def process_action_args(self, args):
        results = []

        if 'folder' not in args or is_blank(args['folder']):
            results.append('folder is required')
        else:
            args['folder'] = clean_string(args['folder'])

            if not os.path.exists(args['folder']):
                results.append('folder path does not exist')
            elif not os.path.isdir(args['folder']):
                results.append('folder path is not a folder')

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
        folder = args['folder']
        return ConsumeJob("Import Folder", f'Import content from: {folder}', args['folder_id'], args['folder'], args['dest'],
                          self.primary_path, self.archive_path)


class ConsumeJob(TaskWrapper):
    def __init__(self, name: str, description: str, folder_id: str, folder_path: str, dest: str, primary_path: str, archive_path: str):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.folder_path = folder_path
        self.dest = dest
        self.primary_path = primary_path
        self.archive_path = archive_path

    def run(self, db_session):

        if is_blank(self.primary_path) or is_blank(self.archive_path):
            self.critical('This feature is not ready.  Please configure the app properties and restart the server.')

        existing_row = find_folder_by_id(self.folder_id, db_session)
        if existing_row is None:
            self.critical('Folder not found in DB')
            self.set_failure()
            return

        for item in os.listdir(self.folder_path):
            src_path = Path(self.folder_path) / item

            if self.can_trace():
                self.trace(f'Source File: {src_path}')

            # Only proceed if it's a file and has an extension
            if src_path.is_file() and src_path.suffix:
                # Get the file details
                file_name = src_path.name
                file_size = src_path.stat().st_size
                created_time = datetime.fromtimestamp(src_path.stat().st_ctime)
                mime_type, _ = mimetypes.guess_type(src_path)  # MIME type

                # If MIME type couldn't be guessed, skip the file
                if mime_type is None:
                    self.info(f"Skipping {file_name}: MIME type couldn't be determined")
                    continue

                is_archive = self.dest == 'archive'

                # Try to insert the object
                new_file = insert_file(self.folder_id, file_name, mime_type, is_archive, False, file_size, created_time,
                                       db_session)

                if is_blank(new_file.id):
                    self.critical('file does not have an ID')
                    self.set_failure()
                    return

                dest_path = get_data_for_mediafile(new_file, self.primary_path, self.archive_path)

                if self.can_trace():
                    self.trace(f'Dest File: {dest_path}')

                shutil.move(str(src_path), str(dest_path))

                self.set_worked()
