import argparse

from flask_sqlalchemy.session import Session

from app_properties import AppPropertyDefinition
from app_utils import value_is_folder
from feature_flags import MANAGE_APP
from file_utils import create_timestamped_folder
from inout import perform_backup
from plugin_system import ActionPlugin
from text_utils import is_not_blank
from thread_utils import TaskWrapper

PROPERTY_PLUGIN_BACKUP_PATH = 'PLUGIN.BACKUP.PATH'


class TestTask(ActionPlugin):
    """
    This is a utility task which will try to awake a local networked PC
    """

    def __init__(self):
        super().__init__()
        self.backup_path = None

    def get_sort(self):
        return {'id': 'backup', 'sequence': 0}

    def get_action_name(self):
        return 'Backup'

    def get_action_id(self):
        return 'action.backup'

    def get_action_icon(self):
        return 'backup'

    def get_action_args(self):
        return []

    def process_action_args(self, args):
        return None

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def absorb_config(self, config):
        if PROPERTY_PLUGIN_BACKUP_PATH in config and is_not_blank(config[PROPERTY_PLUGIN_BACKUP_PATH]):
            self.backup_path = config[PROPERTY_PLUGIN_BACKUP_PATH]

    def create_task(self, db_session: Session, args):
        return BackupTask("Backup", 'Backup Request', self.backup_path)

    def get_feature_flags(self):
        return MANAGE_APP

    def get_category(self):
        return 'utility'

    def get_properties(self) -> list[AppPropertyDefinition]:
        result = super().get_properties()

        result.append(AppPropertyDefinition(PROPERTY_PLUGIN_BACKUP_PATH, '',
                                            'The local folder to save backup requests to.  This should be a folder with read/write access.',
                                            [value_is_folder]))

        return result

    def is_ready(self):
        return self.backup_path is not None


class BackupTask(TaskWrapper):
    def __init__(self, name, description, backup_folder: str):
        super().__init__(name, description)
        self.backup_folder = backup_folder
        self.weight = 100
        self.priority = 0

    def run(self, db_session):
        new_backup_path = create_timestamped_folder(self.backup_folder)
        perform_backup(new_backup_path, db_session, self)
