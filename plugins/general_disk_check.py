import argparse
import logging
import os
from collections import defaultdict

import psutil
from flask_sqlalchemy.session import Session

from constants import PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER, PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER, \
    PROPERTY_SERVER_VOLUME_FOLDER
from feature_flags import MANAGE_APP
from plugin_system import ActionPlugin
from text_utils import is_not_blank
from thread_utils import TaskWrapper


def calculate_folder_size(folder_path: str) -> tuple:
    """
    Calculate the size of items in a folder, separating .previews folder items.

    Args:
        folder_path (str): Path to the folder.

    Returns:
        tuple: (number_of_bytes, number_preview_bytes)
    """
    number_of_bytes = 0
    number_preview_bytes = 0

    for root, dirs, files in os.walk(folder_path):
        # Check if we're in a .previews folder
        is_preview = '.previews' in root.split(os.sep)

        for file in files:
            file_path = os.path.join(root, file)
            try:
                file_size = os.path.getsize(file_path)
                if is_preview:
                    number_preview_bytes += file_size
                else:
                    number_of_bytes += file_size
            except (OSError, FileNotFoundError):
                # Skip files that can't be accessed
                pass

    return number_of_bytes, number_preview_bytes


def calculate_folder_size2(folder_path: str) -> tuple:
    """
    Calculate the size of items in a folder, separating .previews folder items,
    and return the top 25 largest immediate subfolders by size.

    Args:
        folder_path (str): Path to the folder.

    Returns:
        tuple: (number_of_bytes, number_preview_bytes, top_10_subfolders)
    """
    number_of_bytes = 0
    number_preview_bytes = 0
    subfolder_sizes = defaultdict(int)

    for root, dirs, files in os.walk(folder_path):
        # Get the immediate subfolder if not the root folder
        relative_path = os.path.relpath(root, folder_path)
        first_level_subfolder = relative_path.split(os.sep)[0] if os.sep in relative_path else relative_path

        # Check if we're in a .previews folder
        is_preview = '.previews' in root.split(os.sep)

        for file in files:
            file_path = os.path.join(root, file)
            try:
                file_size = os.path.getsize(file_path)

                if is_preview:
                    number_preview_bytes += file_size
                else:
                    number_of_bytes += file_size

                # Accumulate size per first-level subfolder
                if first_level_subfolder and first_level_subfolder != '.':
                    subfolder_sizes[first_level_subfolder] += file_size

            except (OSError, FileNotFoundError):
                # Skip files that can't be accessed
                pass

    # Get the top 10 largest subfolders by size
    top_10_subfolders = sorted(subfolder_sizes.items(), key=lambda x: x[1], reverse=True)[:25]

    return number_of_bytes, number_preview_bytes, top_10_subfolders


class CheckDiskStatusPlugin(ActionPlugin):
    """
    This is a way to check how much disk space is left on this server.
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'diskchk'
        self.primary_path = ''
        self.archive_path = ''
        self.book_folder = ''

    def get_sort(self):
        return {'id': 'disk', 'sequence': 0}

    def absorb_config(self, config):
        """
        Absorb configuration settings.
        """
        self.primary_path = config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER]
        self.archive_path = config[PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER]
        self.book_folder = config[PROPERTY_SERVER_VOLUME_FOLDER]

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Check Space'

    def get_action_id(self):
        return 'action.disk.check'

    def get_action_icon(self):
        return 'album'

    def get_action_args(self):
        return []

    def process_action_args(self, args):
        results = []
        return None

    def get_feature_flags(self):
        return MANAGE_APP

    def get_category(self):
        return 'utility'

    def create_task(self, db_session: Session, args):
        return DiskCheckJob("Disk", 'Check Disk Space', self.primary_path, self.archive_path, self.book_folder)


def get_disk_usage():
    partitions = psutil.disk_partitions()
    disk_usage_info = []
    for partition in partitions:
        try:
            partition_info = {'device': partition.device,
                              'mountpoint': partition.mountpoint,
                              'fstype': partition.fstype,
                              'total': psutil.disk_usage(partition.mountpoint).total,
                              'used': psutil.disk_usage(partition.mountpoint).used,
                              'free': psutil.disk_usage(partition.mountpoint).free,
                              'percent': psutil.disk_usage(partition.mountpoint).percent}
            if partition_info['mountpoint'].startswith('/boot'):
                continue

            disk_usage_info.append(partition_info)
        except Exception as ex:
            logging.exception(ex)
    return disk_usage_info


def format_bytes(size):
    power = 2 ** 10
    n = 0
    units = {
        0: 'bytes',
        1: 'KB',
        2: 'MB',
        3: 'GB',
        4: 'TB'
    }
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"


class DiskCheckJob(TaskWrapper):
    def __init__(self, name, description, primary_path: str, archive_path: str, book_folder: str):
        super().__init__(name, description)
        self.primary_path = primary_path
        self.archive_path = archive_path
        self.book_folder = book_folder

    def run(self, db_session):
        disk_info = get_disk_usage()
        for info in disk_info:
            self.always("Device:", info['device'])
            self.info("Mount Point:", info['mountpoint'], "File System Type:", info['fstype'])
            self.info("Total Space:", format_bytes(info['total']))
            self.info("Used Space:", format_bytes(info['used']))
            self.info("Free Space:", format_bytes(info['free']))
            self.info("Percentage Used:", str(info['percent']) + "%")

        self.always("Additional Details")

        if is_not_blank(self.primary_path):
            item_size, preview_size = calculate_folder_size(self.primary_path)
            self.info("Primary Storage:", format_bytes(item_size))

        if is_not_blank(self.archive_path):
            item_size, preview_size = calculate_folder_size(self.archive_path)
            self.info("Archive Storage:", format_bytes(item_size))

        if is_not_blank(self.book_folder):
            item_size, preview_size, top_folders = calculate_folder_size2(self.book_folder)
            self.info("Book Storage:", format_bytes(item_size))

            for folder, size in top_folders:
                self.info(f" - {folder}: {format_bytes(size)} bytes")
            self.info("Book Preview Storage:", format_bytes(preview_size))
