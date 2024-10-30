import io
import os

import eyed3
from PIL import Image
from moviepy.editor import VideoFileClip

from hash_utils import generate_unique_string
from thread_utils import TaskWrapper


def generate_thumbnail(input_file, output_file, logger: TaskWrapper = None):
    """
    Make a thumbnail
    :param input_file: The input file
    :param output_file: Where to trite the thumbnail
    :param logger: the logger, required
    :return: Nothing
    """
    _, ext = os.path.splitext(input_file)

    if ext.lower() in ['.mp4', '.m4v', '.mpg', '.avi', '.mkv', '.webm']:  # Video file
        clip = VideoFileClip(input_file)
        duration = clip.duration
        thumbnail_time = duration * 0.1  # 10% playback position
        frame = clip.get_frame(thumbnail_time)
        resized_frame = Image.fromarray(frame)
        resized_frame.thumbnail((256, 256))
        resized_frame.save(output_file)
        clip.close()

    elif ext.lower() == '.mp3':  # MP3 file
        audiofile = eyed3.load(input_file)

        for image in audiofile.tag.images:
            try:
                cover_art = Image.open(io.BytesIO(image.image_data))
                cover_art.thumbnail((256, 256))
                cover_art.save(output_file)
                return
            except Exception as inst:
                logger.error(str(inst))


class CreatePreviewTask(TaskWrapper):
    def __init__(self, name, description, source_folder, preview_folder):
        super().__init__(name, description)
        self.source_folder = source_folder
        self.preview_folder = preview_folder

    def run(self, db_session):

        for root, dirs, files in os.walk(self.source_folder):
            for file_name in files:
                # Construct the full path to the file
                file_path = os.path.join(root, file_name)

                if self.is_cancelled:
                    self.critical('Cancelled')
                    return

                if os.path.isfile(file_path):
                    hash_name = generate_unique_string(file_path)

                    hash_file = os.path.join(self.preview_folder, hash_name + '.png')
                    if not os.path.exists(hash_file):
                        generate_thumbnail(file_path, hash_file, self)
