import argparse
import mimetypes
import os.path
import shutil
import subprocess
from datetime import datetime
import eyed3

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_MEDIA
from file_utils import create_random_folder
from image_utils import crop_and_resize
from media_queries import find_folder_by_id, insert_file
from number_utils import parse_boolean
from plugin_system import ActionMediaFolderPlugin, plugin_string_arg, plugin_select_arg, plugin_select_values
from text_utils import is_not_blank, is_blank, common_prefix_postfix, extract_yt_code, remove_prefix_and_postfix, \
    remove_start_digits_pattern
from thread_utils import TaskWrapper


class DownloadMusicFromYtTask(ActionMediaFolderPlugin):
    """
    Download from YTube
    """

    def __init__(self):
        super().__init__()

    def get_sort(self):
        return {'id': 'media_dl.yt', 'sequence': 2}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Save Music from YT'

    def get_action_id(self):
        return 'action.download.yt.music'

    def get_action_icon(self):
        return 'download'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(
            plugin_string_arg('URL', 'url', 'The youtube link to a video.  It should have ?v= in the string.')
        )

        result.append(
            plugin_select_arg('Output', 'split_chapters', 'false',
                              plugin_select_values("Single File", 'false', 'Split', 'true'),
                              'How should the video be treated?')
        )

        result.append({
            "name": "Destination?",
            "id": "dest",
            "description": "Where should these files be stored?",
            "type": "select",
            "default": "primary",
            "values": [{"id": 'primary', "name": 'Primary Disk'}, {"id": 'archive', "name": 'Archive Disk'}]
        })

        return result

    def process_action_args(self, args):
        results = []

        if 'url' not in args or args['url'] is None or args['url'] == '':
            results.append('url is required')

        if 'dest' not in args or is_blank(args['dest']):
            results.append('dest is required')
        elif not (args['dest'] == 'primary' or args['dest'] == 'archive'):
            results.append('Invalid dest value')

        if 'split_chapters' not in args or is_blank(args['split_chapters']):
            results.append('split_chapters is required')
        elif not (args['split_chapters'] == 'false' or args['split_chapters'] == 'true'):
            results.append('split_chapters dest value')

        if len(results) > 0:
            return results
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, session: Session, args):
        return DownloadYtMusic("DL YT Music", 'Downloading music from YT', args['folder_id'], args['url'], parse_boolean(args['split_chapters']),
                               args['dest'],
                               self.primary_path,
                               self.archive_path, self.temp_path)

def extract_album_art(folder, mp3_file, overwite = False):
    cover_file = os.path.join(folder, 'cover.jpg')

    if not os.path.exists(cover_file) or overwite:
        audiofile = eyed3.load(mp3_file)

        for image in audiofile.tag.images:
            image_file = open(cover_file, "wb")
            image_file.write(image.image_data)
            image_file.close()

    return cover_file

def replace_album_art_d3(mp3_file_path, new_album_art_path, new_icon_art_path, log: TaskWrapper):
    audiofile = eyed3.load(mp3_file_path)

    audiofile.initTag(version=(2, 3, 0))

    with open(new_album_art_path, "rb") as cover_art:
        audiofile.tag.images.set(3, cover_art.read(), "image/jpg", '"Album Cover"')

    # Save changes
    audiofile.tag.save()

    log.debug(f"Album art replaced in '{mp3_file_path}'")

class DownloadYtMusic(TaskWrapper):
    def __init__(self, name, description, folder_id, video, split_chapters: bool, dest, primary_path, archive_path,
                 temp_path):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.video = video
        self.split_chapters = split_chapters
        self.dest = dest
        self.primary_path = primary_path
        self.archive_path = archive_path
        self.temp_path = temp_path

    def run(self, db_session: Session):

        if is_blank(self.primary_path) or is_blank(self.archive_path) or is_blank(self.temp_path):
            self.critical('This feature is not ready.  Please configure the app properties and restart the server.')

        source_row = find_folder_by_id(self.folder_id, db_session)
        if source_row is None:
            self.critical('Source Folder not found')
            self.set_failure()
            return

        is_archive = self.dest == 'archive'

        temp_folder = ''
        try:
            temp_folder = create_random_folder(self.temp_path)

            self.info(f'Temp Folder: {temp_folder}')

            arguments = []
            if self.split_chapters:
                arguments.append('--split-chapters')
            arguments.append('-x')
            arguments.append('--embed-thumbnail')
            arguments.append('--audio-format')
            arguments.append('mp3')
            arguments.append(self.video)

            # Run the program with the provided arguments
            process = subprocess.Popen(['yt-dlp'] + arguments, cwd=temp_folder)

            # Wait for the process to finish
            process.wait()

            return_code = str(process.returncode)

            if return_code == '0':
                self.set_worked()

                possible_filenames = os.listdir(temp_folder)

                front_prefix = None
                end_postfix = None

                by_video_lookup = {}

                if self.split_chapters:

                    for possible_filename in possible_filenames:
                        self.info('T:' + possible_filename)
                        video_value = extract_yt_code(possible_filename)
                        if video_value not in by_video_lookup:
                            by_video_lookup[video_value] = []
                        by_video_lookup[video_value].append(possible_filename)

                else:
                    by_video_lookup['*'] = possible_filenames

                for video_key, sample_list in by_video_lookup.items():

                    if self.split_chapters:
                        self.info('Find Prefix')
                        front_prefix, end_postfix = common_prefix_postfix(sample_list)
                        self.info(f'{front_prefix} {end_postfix}')

                    has_cover = False
                    album_file = ''
                    icon_file = ''

                    for item in sample_list:

                        self.info('SL:' + item)

                        # Get the full path
                        item_full_path = os.path.join(temp_folder, item)

                        # Check if it is a file (not a directory)
                        if os.path.isfile(item_full_path):
                            # Get file size
                            file_size = os.path.getsize(item_full_path)

                            # Get created time and convert to readable format
                            created_time = os.path.getctime(item_full_path)
                            created_datetime = datetime.fromtimestamp(created_time)

                            mime_type, _ = mimetypes.guess_type(item_full_path)  # MIME type

                            if mime_type is not None:

                                if not has_cover:
                                    cover_file = extract_album_art(temp_folder, item_full_path, True)

                                    icon_file = os.path.join(temp_folder, 'icon.jpg')
                                    album_file = os.path.join(temp_folder, 'album.jpg')
                                    crop_and_resize(cover_file, album_file, 720, False)
                                    crop_and_resize(album_file, icon_file, 256, False)

                                    has_cover = True

                                modified_name = str(item)

                                if self.split_chapters and front_prefix is not None and end_postfix is not None:
                                    self.info('BE')
                                    video_value = extract_yt_code(modified_name)
                                    self.info('A:' + modified_name)
                                    modified_name = remove_prefix_and_postfix(modified_name, front_prefix,
                                                                              end_postfix)
                                    self.info('B:' + modified_name)
                                    # Skip the non-chapter files
                                    if modified_name == '[' + video_value + '].mp3':
                                        continue
                                    modified_name = remove_start_digits_pattern(modified_name + '[' + video_value + '].mp3')

                                replace_album_art_d3(item_full_path, album_file, icon_file, self)

                                new_file = insert_file(source_row.id, modified_name, mime_type, is_archive, False,
                                                       file_size, created_datetime, db_session)

                                if is_archive:
                                    dest_path = os.path.join(self.archive_path, new_file.id + '.dat')
                                else:
                                    dest_path = os.path.join(self.primary_path, new_file.id + '.dat')

                                shutil.move(str(item_full_path), str(dest_path))

                            else:
                                self.warn(f'Ignoring file {item}, unknown MIME TYPE')
            else:
                self.error(f'Return Code {return_code}')
                self.set_failure()

        finally:
            if is_not_blank(temp_folder) and os.path.exists(temp_folder):
                shutil.rmtree(temp_folder)
