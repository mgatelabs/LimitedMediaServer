import argparse

from flask_sqlalchemy.session import Session
from wakeonlan import send_magic_packet

from app_properties import AppPropertyDefinition
from app_utils import value_is_mac_address
from feature_flags import MANAGE_APP
from plugin_system import ActionPlugin
from text_utils import is_not_blank, clean_string
from thread_utils import TaskWrapper

PROPERTY_PLUGIN_MAC_ADDRESS = 'PLUGIN.WAKE.MAC.ADDRESS'

class WakeUpPcTask(ActionPlugin):
    """
    This is a utility task which will try to awake a local networked PC
    """

    def __init__(self):
        self.mac = None
        super().__init__()

    def get_sort(self):
        return {'id': 'wake_pc', 'sequence': 0}

    def get_action_name(self):
        return 'Wake Up PC'

    def get_action_id(self):
        return 'action.wake.pc'

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
        if PROPERTY_PLUGIN_MAC_ADDRESS in config and is_not_blank(config[PROPERTY_PLUGIN_MAC_ADDRESS]):
            self.mac = config[PROPERTY_PLUGIN_MAC_ADDRESS]


    def create_task(self, session: Session, args):
        return WakePc("WakePC", f'Wake up PC w/ MAC address {self.mac}', self.mac)

    def get_feature_flags(self):
        return MANAGE_APP

    def get_category(self):
        return 'utility'

    def get_properties(self) -> list[AppPropertyDefinition]:
        result = super().get_properties()

        result.append(AppPropertyDefinition(PROPERTY_PLUGIN_MAC_ADDRESS, '',
                              'The MAC address of the machine you wish to turn on.  Restart server if changed.',
                                            [value_is_mac_address]))

        return result

    def is_ready(self):
        return self.mac is not None


class WakePc(TaskWrapper):
    def __init__(self, name, description, mac):
        super().__init__(name, description)
        self.mac = mac

    def run(self, db_session):
        if self.mac is not None:
            send_magic_packet(self.mac)
            self.info('Sent Magic Packet')
        else:
            self.critical(f'{PROPERTY_PLUGIN_MAC_ADDRESS} property was not setup')
            self.set_failure()
