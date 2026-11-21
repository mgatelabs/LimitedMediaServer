import argparse

import requests
from flask_sqlalchemy.session import Session

from constants import PROPERTY_LIMITED_SCRAPER_HOST, PROPERTY_LIMITED_SCRAPER_PORT
from feature_flags import MANAGE_APP
from plugin_system import ActionPlugin
from text_utils import is_not_blank
from thread_utils import TaskWrapper


class RestartScraperPlugin(ActionPlugin):
    """
    This is a utility task which will send a restart command to the limited media scraper.
    Because the scraper restarts immediately upon receiving the command, no reliable
    response is expected and the result is intentionally ignored.
    """
    AI_QUICK_DESCRIPTION = ('Sends a fire-and-forget restart command to the configured '
                            'limited media scraper service; the scraper restarts itself.')
    AI_LONG_DESCRIPTION = (
        'Posts a restart request to the limited media scraper service configured in the '
        'server settings (host and port). The scraper restarts itself on receiving the '
        'command, so it drops the connection before replying; a successful response or a '
        'connection error are both logged as expected. Takes no arguments and does not '
        'touch any book, media file, or server data. Only available when a scraper host is '
        'configured.')

    def __init__(self):
        super().__init__()
        self.scraper_host = ''
        self.scraper_port = 8080
        self.prefix_lang_id = 'restart_scraper'

    def get_sort(self):
        return {'id': 'restart_scraper', 'sequence': 0}

    def get_action_name(self):
        return 'Restart Scraper'

    def get_action_id(self):
        return 'action.restart.scraper'

    def get_action_icon(self):
        return 'refresh'

    def get_action_args(self):
        return []

    def process_action_args(self, args):
        return None

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def absorb_config(self, config):
        self.scraper_host = config[PROPERTY_LIMITED_SCRAPER_HOST]
        self.scraper_port = config[PROPERTY_LIMITED_SCRAPER_PORT]

    def create_task(self, db_session: Session, args):
        return RestartScraperJob("RestartScraper", f'Restart the limited media scraper at {self.scraper_host}:{self.scraper_port}',
                                 self.scraper_host, self.scraper_port)

    def get_feature_flags(self):
        return MANAGE_APP

    def get_category(self):
        return 'utility'

    def is_ready(self):
        return is_not_blank(self.scraper_host)


class RestartScraperJob(TaskWrapper):
    def __init__(self, name, description, host, port):
        super().__init__(name, description)
        self.host = host
        self.port = port

    def run(self, db_session):
        if is_not_blank(self.host):
            server_url = f'http://{self.host}:{self.port}'
            self.info(f'Sending restart command to {server_url}')
            try:
                requests.post(f'{server_url}/restart', timeout=30)
                self.info('Restart command returned a response. Ignoring result')
            except requests.exceptions.RequestException:
                self.info('Restart command sent. No usable response received, which is expected during a restart')
        else:
            self.critical('Limited scraper host is not configured')
            self.set_failure()
