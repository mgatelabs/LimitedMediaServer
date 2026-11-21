import argparse

from flask_sqlalchemy.session import Session
from wakeonlan import send_magic_packet

from app_properties import AppPropertyDefinition
from app_utils import value_is_mac_list
from feature_flags import MANAGE_APP
from plugin_methods import plugin_select_arg
from plugin_system import ActionPlugin
from text_utils import is_not_blank, clean_string
from thread_utils import TaskWrapper

PROPERTY_PLUGIN_MAC_ADDRESS = 'PLUGIN.WAKE.MAC.ADDRESS'

class WakeUpPcPlugin(ActionPlugin):
    """
    This is a utility task which will try to awake a local networked PC
    """
    AI_QUICK_DESCRIPTION = ('Sends a Wake-on-LAN magic packet to one configured PC, or to all '
                            'of them at once, over the local network.')
    AI_LONG_DESCRIPTION = (
        'Wakes network hardware using the standard Wake-on-LAN magic packet. The target machines '
        'are configured out-of-band in the server property PLUGIN.WAKE.MAC.ADDRESS as a '
        'semicolon-separated list of NAME@MAC_ADDRESS entries (a bare MAC address is also '
        'accepted), so no configuration is needed through this action. The PC argument selects '
        'which configured machine to wake: one of the configured MAC address values, or * (the '
        'default) to broadcast the packet to every configured machine. The action takes no '
        'other arguments and does not verify the machine actually came up - it only sends the '
        'packet. The action is not ready until at least one MAC address is configured.')

    def __init__(self):
        super().__init__()
        self.pcs = []
        self.prefix_lang_id = 'wakeup'

    def get_sort(self):
        return {'id': 'wake_pc', 'sequence': 0}

    def get_action_name(self):
        return 'Wake Up PC'

    def get_action_id(self):
        return 'action.wake.pc'

    def get_action_icon(self):
        return 'bolt'

    def get_action_args(self):
        values = [{"id": "*", "name": "All PCs"}]
        for name, mac in self.pcs:
            values.append({"id": mac, "name": name})
        return [
            plugin_select_arg('PC', 'wake_pc_id', '*', values,
                              'Select the PC to wake, or * for all PCs.')
        ]

    def process_action_args(self, args):
        if 'wake_pc_id' not in args or not args['wake_pc_id']:
            return ['wake_pc_id is required']
        if args['wake_pc_id'] != '*' and not any(mac == args['wake_pc_id'] for _, mac in self.pcs):
            return ["Invalid wake_pc_id value"]
        return None

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def absorb_config(self, config):
        if PROPERTY_PLUGIN_MAC_ADDRESS in config and is_not_blank(config[PROPERTY_PLUGIN_MAC_ADDRESS]):
            for entry in config[PROPERTY_PLUGIN_MAC_ADDRESS].split(';'):
                entry = entry.strip()
                if not entry:
                    continue
                if '@' in entry:
                    name, mac = entry.rsplit('@', 1)
                    name = clean_string(name)
                    mac = clean_string(mac)
                    if not name:
                        name = mac
                else:
                    mac = clean_string(entry)
                    name = mac
                self.pcs.append((name, mac))


    def create_task(self, db_session: Session, args):
        macs = [mac for _, mac in self.pcs]
        if args.get('wake_pc_id') != '*':
            macs = [args['wake_pc_id']]
        return WakePcJob("WakePC", f'Wake up PC(s) [{", ".join(macs)}]', macs)

    def get_feature_flags(self):
        return MANAGE_APP

    def get_category(self):
        return 'utility'

    def get_properties(self) -> list[AppPropertyDefinition]:
        result = super().get_properties()

        result.append(AppPropertyDefinition(PROPERTY_PLUGIN_MAC_ADDRESS, '',
                               'The machines you wish to be able to turn on, as a list of NAME@MAC_ADDRESS entries '
                               'separated by semicolons (e.g. "Office@AA:BB:CC:DD:EE:FF;Guest@11:22:33:44:55:66"). '
                               'A bare MAC address can also be used. Restart server if changed.',
                                             [value_is_mac_list]))

        return result

    def is_ready(self):
        return len(self.pcs) > 0


class WakePcJob(TaskWrapper):
    def __init__(self, name, description, macs: list):
        super().__init__(name, description)
        self.macs = macs

    def run(self, db_session):
        if self.macs:
            for mac in self.macs:
                send_magic_packet(mac)
            self.info(f'Sent Magic Packet to {len(self.macs)} PC(s)')
        else:
            self.critical(f'{PROPERTY_PLUGIN_MAC_ADDRESS} property was not setup')
            self.set_failure()
