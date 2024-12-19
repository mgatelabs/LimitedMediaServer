import argparse
import logging

import psutil
from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_APP
from plugin_system import ActionPlugin
from thread_utils import TaskWrapper


class CheckDiskStatus(ActionPlugin):
    """
    This is a way to check how much disk space is left on this server.
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'diskchk'

    def get_sort(self):
        return {'id': 'disk', 'sequence': 0}

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
        return CreateDiskCheck("Disk", 'Check Disk Space')


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


class CreateDiskCheck(TaskWrapper):
    def __init__(self, name, description):
        super().__init__(name, description)

    def run(self, db_session):
        disk_info = get_disk_usage()
        for info in disk_info:
            self.always("Device:", info['device'])
            self.info("Mount Point:", info['mountpoint'], "File System Type:", info['fstype'])
            self.info("Total Space:", format_bytes(info['total']))
            self.info("Used Space:", format_bytes(info['used']))
            self.info("Free Space:", format_bytes(info['free']))
            self.info("Percentage Used:", str(info['percent']) + "%")
