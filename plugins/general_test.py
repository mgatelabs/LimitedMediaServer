import argparse
import time

from flask_sqlalchemy.session import Session

from app_properties import AppPropertyDefinition
from feature_flags import MANAGE_PROCESSES
from plugin_system import ActionPlugin
from thread_utils import TaskWrapper


class TestTask(ActionPlugin):
    """
    This is a utility task which will try to awake a local networked PC
    """

    def __init__(self):
        self.mac = None
        super().__init__()

    def get_sort(self):
        return {'id': 'test_task', 'sequence': 0}

    def get_action_name(self):
        return 'Test'

    def get_action_id(self):
        return 'action.test'

    def get_action_icon(self):
        return 'bolt'

    def get_action_args(self):
        return []

    def process_action_args(self, args):
        return None

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def absorb_config(self, config):
        pass


    def create_task(self, session: Session, args):
        return Test("Test", 'Test Process')

    def get_feature_flags(self):
        return MANAGE_PROCESSES

    def get_category(self):
        return 'utility'

    def get_properties(self) -> list[AppPropertyDefinition]:
        result = super().get_properties()
        return result

    def is_ready(self):
        return True


class Test(TaskWrapper):
    def __init__(self, name, description):
        super().__init__(name, description)

    def run(self, db_session):

        for i in range(60):

            self.warn(f'Loop Warn {i}')
            self.info(f'Loop Info {i}')
            self.debug(f'Loop Debug {i}')
            self.trace(f'Loop Trace {i}')

            # Perform your action here
            time.sleep(1)  # Wait for 1000 ms (1 second) in each loop

            if self.is_cancelled:
                break
