import argparse
import os
import os.path
import eyed3

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_MEDIA
from media_queries import find_folder_by_id, find_files_in_folder, find_files_in_folder_with_mime
from media_utils import get_data_for_mediafile
from plugin_system import ActionMediaFolderPlugin, plugin_string_arg
from text_utils import is_blank, extract_artist_title_from_audio_filename, is_not_blank, extract_yt_code
from thread_utils import TaskWrapper


class Mp3TagFolderTask(ActionMediaFolderPlugin):
    """
    Remove files that don't exist
    """
    def __init__(self):
        super().__init__()


    def get_sort(self):
        return {'id': 'media_update_music_attributes_folder', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Update Mp3 Tags'

    def get_action_id(self):
        return 'action.update.mp3.tags.folder'

    def get_action_icon(self):
        return 'music_note'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(plugin_string_arg('Genre', 'genre', 'Genre value'))
        result.append(plugin_string_arg('Album', 'album', 'Album value'))
        result.append(plugin_string_arg('Year', 'year', 'Year value'))

        return result

    def process_action_args(self, args):
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, session: Session, args):
        return Mp3TagFolder("Update Mp3 Tags", '', args['folder_id'], args['genre'], args['album'], args['year'], self.primary_path, self.archive_path)

def update_mp3_metadata(title, artist, album, year, genre, file_location):
    # FFmpeg command to update metadata and cover art

    audiofile = eyed3.load(file_location)

    if is_not_blank(artist):
        audiofile.tag.artist = artist
    audiofile.tag.album = album
    audiofile.tag.genre = genre
    audiofile.tag.recording_date = year
    if is_not_blank(title):
        audiofile.tag.title = title

    audiofile.tag.save()

class Mp3TagFolder(TaskWrapper):
    def __init__(self, name, description, folder_id, genre: str, album: str, year: str, primary_path, archive_path):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.genre = genre
        self.year = year
        self.album = album
        self.primary_path = primary_path
        self.archive_path = archive_path

    def run(self, db_session: Session):

        if is_blank(self.primary_path):
            self.critical('This feature is not ready.  Please configure the app properties and restart the server.')

        existing_row = find_folder_by_id(self.folder_id, db_session)
        if existing_row is None:
            self.critical('Folder not found in DB')
            self.set_failure()
            return

        files = find_files_in_folder_with_mime(self.folder_id, 'audio/mpeg', db_session)

        for file in files:

            yt_code = extract_yt_code(file.filename)

            artist, title = extract_artist_title_from_audio_filename(file.filename)

            if is_blank(artist):
                artist = None

            if is_blank(title):
                title = None

            file_path = get_data_for_mediafile(file, self.primary_path, self.archive_path)

            album = self.album
            if is_not_blank(yt_code):
                album = album + ' [' + yt_code + ']'

            self.info(f'{artist} - {title}')

            update_mp3_metadata(title, artist, album, self.year, self.genre, file_path)
