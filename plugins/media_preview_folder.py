import argparse
import io
import logging
import os
import os.path
from logging import exception

import eyed3
from PIL import Image
from flask_sqlalchemy.session import Session
from moviepy.video.io.VideoFileClip import VideoFileClip

from feature_flags import MANAGE_MEDIA
from image_utils import resize_image
from media_queries import find_folder_by_id, find_missing_file_previews_in_folder, find_missing_file_previews, \
    find_files_in_folder
from number_utils import parse_boolean
from plugin_system import ActionMediaFolderPlugin, ActionMediaPlugin, plugin_select_values, plugin_select_arg
from text_utils import is_blank
from thread_utils import TaskWrapper


class MakePreviewsTask(ActionMediaFolderPlugin):
    """
    Task to update the previews for a specific folder.
    """

    def __init__(self):
        super().__init__()

    def get_sort(self):
        """
        Define the sort order for this task.
        """
        return {'id': 'media_preview_folder', 'sequence': 1}

    def add_args(self, parser: argparse):
        """
        Add command-line arguments for this task.
        """
        pass

    def use_args(self, args):
        """
        Use the provided command-line arguments.
        """
        pass

    def get_action_name(self):
        """
        Get the name of the action.
        """
        return 'Generate Previews'

    def get_action_id(self):
        """
        Get the unique ID of the action.
        """
        return 'action.generate.previews.folder'

    def get_action_icon(self):
        """
        Get the icon for the action.
        """
        return 'image'

    def get_action_args(self):
        """
        Get the arguments for the action.
        """
        result = super().get_action_args()

        result.append(
            plugin_select_arg('Force', 'force', 'false',
                              plugin_select_values("No", 'false', 'Yes', 'true'),
                              'Force it to overwrite?')
        )

        return result

    def process_action_args(self, args):
        """
        Process the action arguments.
        """
        results = []

        if 'force' not in args or is_blank(args['force']):
            results.append('force is required')
        elif not (args['force'] == 'false' or args['force'] == 'true'):
            results.append('force incorrect value')

        if len(results) > 0:
            return results

        return None

    def get_feature_flags(self):
        """
        Get the feature flags required for this task.
        """
        return MANAGE_MEDIA

    def create_task(self, session: Session, args):
        """
        Create the task to generate previews for a folder.
        """
        folder_id = args['folder_id']
        return PreviewFolder("Gen-Prev", f'Generate previews for: {folder_id}', folder_id, self.primary_path,
                             self.archive_path, False, parse_boolean(args['force']))


class MakeAllPreviewsTask(ActionMediaPlugin):
    """
    Task to update previews system-wide.
    """

    def __init__(self):
        super().__init__()

    def get_sort(self):
        """
        Define the sort order for this task.
        """
        return {'id': 'media_preview_all', 'sequence': 1}

    def add_args(self, parser: argparse):
        """
        Add command-line arguments for this task.
        """
        pass

    def use_args(self, args):
        """
        Use the provided command-line arguments.
        """
        pass

    def get_action_name(self):
        """
        Get the name of the action.
        """
        return 'Generate Previews'

    def get_action_id(self):
        """
        Get the unique ID of the action.
        """
        return 'action.generate.previews.all'

    def get_action_icon(self):
        """
        Get the icon for the action.
        """
        return 'image'

    def get_action_args(self):
        """
        Get the arguments for the action.
        """
        result = super().get_action_args()
        return result

    def process_action_args(self, args):
        """
        Process the action arguments.
        """
        return None

    def get_feature_flags(self):
        """
        Get the feature flags required for this task.
        """
        return MANAGE_MEDIA

    def create_task(self, session: Session, args):
        """
        Create the task to generate previews for all folders.
        """
        return PreviewFolder("Gen-Prev", 'All Folders', '*', self.primary_path, self.archive_path, True)


class PreviewFolder(TaskWrapper):
    """
    Task to generate previews for files in a folder.
    """

    def __init__(self, name, description, folder_id, primary_path, archived_path, all_folders=False, force=False,
                 media_position=45):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.primary_path = primary_path
        self.archived_path = archived_path
        self.all_folders = all_folders
        self.force = force
        self.media_position = media_position

    def run(self, db_session: Session):
        """
        Run the task to generate previews.
        """

        if is_blank(self.primary_path) or is_blank(self.archived_path):
            self.critical('This feature is not ready. Please configure the app properties and restart the server.')

        if self.all_folders:
            files = find_missing_file_previews(db_session)
        else:
            existing_row = find_folder_by_id(self.folder_id, db_session)

            if existing_row is None:
                self.critical('Folder not found in DB')
                self.set_failure()
                return

            if self.force:
                files = find_files_in_folder(self.folder_id, db_session=db_session)
            else:
                files = find_missing_file_previews_in_folder(self.folder_id, db_session)

        total = len(files)
        count = 1

        for file in files:

            if self.is_cancelled:
                break

            self.update_progress((count / total) * 100.0)
            count = count + 1

            if file.archive:
                source_path = os.path.join(self.archived_path, file.id + '.dat')
            else:
                source_path = os.path.join(self.primary_path, file.id + '.dat')

            preview_path = os.path.join(self.primary_path, file.id + '_prev.png')

            if not self.all_folders:
                # For all folders, we don't need to log this, since the user may not have access to a folder
                self.info(f'Making thumbnail for {file.filename}')

                if self.can_trace():
                    self.trace(f'{source_path} > {preview_path}')

            try:
                if generate_thumbnail(file.mime_type, str(source_path), str(preview_path), self, self.media_position):
                    file.preview = True
                    if count % 100 == 0:
                        self.set_worked()
                        db_session.commit()
                else:
                    self.warn(f'Could not generate thumbnail for {file.filename}')
            except Exception as e:
                logging.exception(e)
                self.set_failure()


        if len(files) > 0:
            self.set_worked()
            db_session.commit()


def generate_thumbnail(mime_type: str, input_file, output_file, tw: TaskWrapper = None, percent: int = 10) -> bool:
    """
    Generate a thumbnail for a media file.

    Args:
        mime_type (str): The MIME type of the file.
        input_file (str): The path to the input file.
        output_file (str): The path to the output file.
        tw (TaskWrapper, optional): The logger to use. Defaults to None.
        percent (int, optional): The position in the media file to capture the thumbnail. Defaults to 10.
    """

    if is_blank(mime_type):
        if tw is not None:
            tw.warn('Unknown Mime Type')
        return False

    if tw is not None:
        tw.trace('generate_thumbnail')

    mime_type = mime_type.lower()

    if tw is not None:
        tw.trace(f'Mime {mime_type}')

    if mime_type == 'video/mp4':  # Video file
        if tw is not None:
            tw.trace('Starting MP4')

        temp_file = input_file.replace(".dat", ".mp4")
        try:
            if os.path.exists(temp_file) and os.path.isfile(temp_file):
                if tw is not None:
                    tw.warn(f'Found file that had been messed up {temp_file}')
                pass
            else:
                # Rename file to .mp4
                os.rename(input_file, temp_file)

            clip = VideoFileClip(temp_file)
            duration = clip.duration
            thumbnail_time = duration * (percent / 100.0)  # 10% playback position
            frame = clip.get_frame(thumbnail_time)
            resized_frame = Image.fromarray(frame)
            resized_frame.thumbnail((256, 256))
            resized_frame.save(output_file)
            clip.close()

        finally:
            os.rename(temp_file, input_file)

        if tw is not None:
            tw.set_worked()



        return True

    elif mime_type == 'audio/mp3' or mime_type == 'audio/mpeg':  # MP3 file
        try:
            if tw is not None:
                tw.trace('Starting MP3')

            audiofile = eyed3.load(input_file)

            if tw is not None:
                tw.trace('Loaded MP3')

            for image in audiofile.tag.images:
                try:
                    cover_art = Image.open(io.BytesIO(image.image_data))
                    cover_art.thumbnail((256, 256))
                    cover_art.save(output_file)

                    if tw is not None:
                        tw.set_worked()

                    return True
                except Exception as inst:
                    logging.exception(inst)
                    if tw is not None:
                        tw.critical(str(inst))
                    return False
        except Exception as inst2:
            logging.exception(inst2)
    elif mime_type == 'image/png' or mime_type == 'image/jpg' or mime_type == 'image/jpeg' or mime_type == 'image/gif':  # MP3 file
        resize_image(input_file, output_file, 128)
        return True
    else:
        if tw is not None:
            tw.warn(f'Unknown File {mime_type}')
        return False
