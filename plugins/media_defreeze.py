import argparse
import logging
import os
import os.path
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
import mimetypes

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_MEDIA
from ffmpeg_utils import get_ffmpeg_f_argument_from_mimetype
from file_utils import temporary_folder
from media_queries import insert_file
from media_utils import get_data_for_mediafile, get_file_by_user, describe_file_size_change
from plugin_system import ActionMediaFilePlugin, ActionMediaFilesPlugin
from text_utils import is_blank
from thread_utils import TaskWrapper


def detect_freezes(file_path, import_format:str = 'null'):

    cmd = [
        "ffmpeg", "-i", file_path,
        "-vf", "freezedetect=n=-60dB:d=0.5",
        "-map", "0:v:0", "-f", import_format, "-"
    ]

    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    timestamps = re.findall(r"freeze_start: (\d+\.\d+)|freeze_end: (\d+\.\d+)", result.stderr)
    freeze_ranges = []
    start = None
    for start_time, end_time in timestamps:
        if start_time:
            start = float(start_time)
        if end_time and start is not None:
            freeze_ranges.append((start, float(end_time)))
            start = None
    return freeze_ranges


def detect_silences(file_path, import_format:str = 'null'):
    cmd = [
        "ffmpeg", "-i", file_path,
        "-af", "silencedetect=noise=-30dB:d=0.5",
        "-f", import_format, "-"
    ]

    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    timestamps = re.findall(r"silence_start: (\d+\.\d+)|silence_end: (\d+\.\d+)", result.stderr)
    silence_ranges = []
    start = None

    for start_time, end_time in timestamps:
        if start_time:
            start = float(start_time)
        if end_time and start is not None:
            silence_ranges.append((start, float(end_time)))
            start = None
    return silence_ranges


def merge_intervals(video_gaps, audio_gaps, min_duration=3.0):
    merged = []

    # Find overlapping intervals between video and audio gaps
    i, j = 0, 0
    while i < len(video_gaps) and j < len(audio_gaps):
        v_start, v_end = video_gaps[i]
        a_start, a_end = audio_gaps[j]

        # Find the overlapping region
        overlap_start = max(v_start, a_start)
        overlap_end = min(v_end, a_end)

        # If overlap duration is at least min_duration, keep it
        if overlap_end > overlap_start and (overlap_end - overlap_start) >= min_duration:
            merged.append((overlap_start, overlap_end))

        # Move to the next interval in whichever list finishes first
        if v_end < a_end:
            i += 1
        else:
            j += 1

    return merged


def cut_gaps(file_path, output_file, import_format, task_wrapper: TaskWrapper):
    task_wrapper.update_percent(30)
    freezes = detect_freezes(file_path)
    task_wrapper.update_percent(60)
    silences = detect_silences(file_path)

    # Merge only overlapping video & audio gaps of at least 3 seconds
    gaps = merge_intervals(freezes, silences, min_duration=1.5)

    if not gaps:
        task_wrapper.info(f"No significant gaps detected in {file_path}. Copying the original file.")
        # subprocess.run(["copy", file_path, output_file])  # Use shutil.copy for cross-platform
        shutil.copy(file_path, output_file)
        return

    inputs = []
    filter_inputs = []
    last_end = 0
    segment_index = 0

    task_wrapper.update_percent(75)

    for start, end in gaps:
        if last_end > 0 and abs(last_end - start) <= 0.001:
            continue
        # Add segment from last_end to start of gap
        inputs.extend(["-ss", str(last_end), "-to", str(start), "-i", file_path])
        filter_inputs.append(f"[{segment_index}:v:0][{segment_index}:a:0]")
        last_end = end
        segment_index += 1

    # Add final segment after last gap
    inputs.extend(["-ss", str(last_end), "-i", file_path])
    filter_inputs.append(f"[{segment_index}:v:0][{segment_index}:a:0]")

    # Construct the concat filter
    filter_complex = f"{''.join(filter_inputs)}concat=n={segment_index + 1}:v=1:a=1[outv][outa]"

    task_wrapper.update_percent(80)

    cmd = [
        "ffmpeg", *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]", "-profile:v", "high","-level", "4.2", "-crf", "28", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k", "-preset", 'slower', output_file
    ]
    if task_wrapper.can_debug():
        task_wrapper.debug(f"Running FFmpeg command: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


class DeFreezeForFilePlugin(ActionMediaFilePlugin):
    """
    Task to update the previews for a specific file.
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'defreeze'

    def get_sort(self):
        """
        Define the sort order for this task.
        """
        return {'id': 'media_defreeze_file', 'sequence': 1}

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
        return 'De-Freeze'

    def get_action_id(self):
        """
        Get the unique ID of the action.
        """
        return 'action.defreeze.file'

    def get_action_icon(self):
        """
        Get the icon for the action.
        """
        return 'kitchen'

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
        results = []

        if len(results) > 0:
            return results

        return None

    def get_feature_flags(self):
        """
        Get the feature flags required for this task.
        """
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        """
        Create the task to generate previews for a folder.
        """
        file_id = args['file_id']
        return DeFreezeJob("DeFreeze", f'DeFreeze for File: {file_id}', '', file_id, self.primary_path,
                           self.archive_path, self.temp_path)


class DeFreezeForFilesPlugin(ActionMediaFilesPlugin):
    """
    Task to update the previews for a specific file.
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'defreeze'

    def get_sort(self):
        """
        Define the sort order for this task.
        """
        return {'id': 'media_defreeze_files', 'sequence': 1}

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
        return 'De-Freeze'

    def get_action_id(self):
        """
        Get the unique ID of the action.
        """
        return 'action.defreeze.files'

    def get_action_icon(self):
        """
        Get the icon for the action.
        """
        return 'kitchen'

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
        results = []

        if len(results) > 0:
            return results

        return None

    def get_feature_flags(self):
        """
        Get the feature flags required for this task.
        """
        return MANAGE_MEDIA

    def create_task(self, db_session: Session, args):
        """
        Create the task to generate previews for a folder.
        """
        file_id = args['file_id']
        return DeFreezeJob("DeFreeze", f'DeFreeze for Files: {file_id}', '', file_id, self.primary_path,
                           self.archive_path, self.temp_path, True)


class DeFreezeJob(TaskWrapper):
    """
    Task to generate previews for files in a folder.
    """

    def __init__(self, name, description, folder_id, file_id, primary_path, archived_path, temp_folder,
                 multiple_file: bool = False):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.file_id = file_id
        self.multiple_file = multiple_file
        self.primary_path = primary_path
        self.archived_path = archived_path
        self.temp_folder = temp_folder
        self.weight = 70
        if folder_id != '*':
            self.ref_folder_id = folder_id

    def run(self, db_session: Session):
        """
        Run the task to generate previews.
        """

        if is_blank(self.primary_path) or is_blank(self.archived_path):
            self.critical('This feature is not ready. Please configure the app properties and restart the server.')

        try:
            if self.multiple_file:
                file_list = self.file_id.split(",")
                for file in file_list:
                    get_file_by_user(file, self.user, db_session)
            else:
                get_file_by_user(self.file_id, self.user, db_session)
        except ValueError as ve:
            logging.exception(ve)
            self.error(str(ve))
            self.set_failure()
            return

        self.trace('Start Finding Files')
        folder_row = None

        if self.multiple_file:
            files = []
            file_list = self.file_id.split(",")
            for file in file_list:
                fi, folder_row = get_file_by_user(file, self.user, db_session)
                files.append(fi)
        else:
            files = []
            fi, folder_row = get_file_by_user(self.file_id, self.user, db_session)
            files.append(fi)

        self.trace('End Finding Files')

        if folder_row is None:
            self.set_failure()
            self.error('No folder')
            return

        total_files = len(files)
        index = 0

        try:
            with temporary_folder(self.temp_folder, self) as temp_folder:
                for file in files:

                    if self.is_cancelled:
                        self.info('Leaving Early')
                        return
                    index = index + 1
                    self.update_progress((index / total_files) * 100.0)

                    source_file = get_data_for_mediafile(file, self.primary_path, self.archived_path)
                    desired_format = get_ffmpeg_f_argument_from_mimetype(file.mime_type)

                    dest_file = os.path.join(temp_folder, 'temp.mp4')

                    if os.path.exists(dest_file):
                        os.remove(dest_file)

                    self.info(f'Working on {file.filename}')

                    cut_gaps(source_file, dest_file, desired_format, self)

                    src_path = Path(temp_folder) / 'temp.mp4'

                    if os.path.exists(src_path):
                        file_name = file.filename + '_defr'
                        file_size = src_path.stat().st_size

                        created_time = datetime.fromtimestamp(src_path.stat().st_ctime)
                        mime_type, _ = mimetypes.guess_type(src_path)

                        is_archive = False

                        # Try to insert the object
                        new_file = insert_file(folder_row.id, file_name, mime_type, is_archive, False, file_size,
                                               created_time,
                                               db_session)

                        if is_blank(new_file.id):
                            self.critical('file does not have an ID')
                            self.set_failure()
                            return

                        # Move file to destination folder

                        dest_path = get_data_for_mediafile(new_file, self.primary_path, self.archived_path)

                        if self.can_trace():
                            self.trace(f'Dest MediaFile: {new_file.id}')

                        self.info(describe_file_size_change(file.filesize, new_file.filesize))

                        shutil.move(str(src_path), str(dest_path))

                        self.set_worked()
        finally:
            pass

        if len(files) > 0:
            self.set_worked()
            db_session.commit()
