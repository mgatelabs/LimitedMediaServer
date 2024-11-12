import argparse

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_MEDIA
from media_queries import find_folder_by_id
from plugin_system import ActionMediaFolderPlugin, plugin_media_folder_chooser_move_folder_arg
from text_utils import is_not_blank
from thread_utils import TaskWrapper


class MoveFolderTask(ActionMediaFolderPlugin):
    """
    Move a folder to another folder
    """

    def __init__(self):
        super().__init__()

    def get_sort(self):
        return {'id': 'media_move_folder', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Move Folder'

    def get_action_id(self):
        return 'action.move.folder'

    def get_action_icon(self):
        return 'trending_up'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(
            plugin_media_folder_chooser_move_folder_arg('Destination', 'dest_id', 'The folder to move this folder under.'))

        return result

    def process_action_args(self, args):
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def create_task(self, session: Session, args):
        return MoveFolder("Move", 'Move Folder', args['folder_id'], args['dest_id'])


class MoveFolder(TaskWrapper):
    def __init__(self, name, description, folder_id, dest_id):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.dest_id = dest_id

    def run(self, db_session: Session):

        source_row = find_folder_by_id(self.folder_id, db_session)
        if source_row is None:
            self.critical('Source Folder not found')
            self.set_failure()
            return

        if is_not_blank(self.dest_id):
            dest_row = find_folder_by_id(self.dest_id, db_session)
            if dest_row is None:
                self.critical('Dest Folder not found')
                self.set_failure()
                return

            if source_row.rating < dest_row.rating:
                self.critical('New parent folder has a higher rating, will not move')
                self.set_failure()
                return

            if dest_row.owning_group_id is not None and source_row.owning_group_id is not None and dest_row.owning_group_id != source_row.owning_group_id:
                self.critical('New parent folder has has a different owning security group, will not move')
                self.set_failure()
                return

            if dest_row.owning_group_id is not None and source_row.owning_group_id is None:
                self.critical('Source folder does not have a group, when target does, stopping!')
                self.set_failure()
                return

            source_row.parent_id = dest_row.id
            db_session.commit()

            self.info('Folder moved to sub-folder')
            self.set_worked()

        else:
            source_row.parent_id = None
            db_session.commit()

            self.info('Folder moved to root-folder')
            self.set_worked()
        pass
