import argparse
import time

import requests
from flask_sqlalchemy.session import Session

from constants import PROPERTY_LIMITED_SCRAPER_HOST, PROPERTY_LIMITED_SCRAPER_PORT
from feature_flags import MANAGE_APP
from plugin_system import ActionPlugin
from text_utils import is_not_blank
from thread_utils import TaskWrapper


class RefreshScraperCookiesPlugin(ActionPlugin):
    """
    This is a utility task which submits a "refresh_cookies" job to the limited
    media scraper and waits for it to finish.  The scraper opens a headful
    browser over its refresh URL and re-extracts cookies to cookies.json, which
    takes roughly 10-30+ seconds.  The     browser window is intentionally visible
    on the machine running the scraper service.
    """
    AI_QUICK_DESCRIPTION = ('Submits a cookie-refresh job to the limited media scraper, which '
                            'opens a visible browser over its refresh URL and re-extracts '
                            'cookies to cookies.json; blocks and polls until the remote job '
                            'finishes.')
    AI_LONG_DESCRIPTION = (
        'Submits a "refresh_cookies" job to the limited media scraper service configured in '
        'the server settings (host and port) and polls its status (about every 3 seconds) '
        'until the remote job reports finished or failure, mirroring the remote progress into '
        'this task. The scraper opens a headful browser window on its own machine, visits its '
        'refresh URL, and re-extracts its cookies into cookies.json; this typically takes '
        '10-30+ seconds and the browser window is intentionally visible on the scraper '
        'machine. The local server changes no data; the only side effect is that the '
        'scraper\'s stored cookies are renewed. Takes no arguments. Only available when a '
        'scraper host is configured.')

    def __init__(self):
        super().__init__()
        self.scraper_host = ''
        self.scraper_port = 8080
        self.prefix_lang_id = 'refresh_scraper_cookies'

    def get_sort(self):
        return {'id': 'refresh_scraper_cookies', 'sequence': 0}

    def get_action_name(self):
        return 'Refresh Scraper Cookies'

    def get_action_id(self):
        return 'action.refresh.scraper.cookies'

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
        return RefreshScraperCookiesJob("RefreshScraperCookies",
                                        f'Refresh the limited media scraper cookies at {self.scraper_host}:{self.scraper_port}',
                                        self.scraper_host, self.scraper_port)

    def get_feature_flags(self):
        return MANAGE_APP

    def get_category(self):
        return 'utility'

    def is_ready(self):
        return is_not_blank(self.scraper_host)


class RefreshScraperCookiesJob(TaskWrapper):
    POLL_INTERVAL = 3.0
    MAX_CONSECUTIVE_POLL_ERRORS = 10

    def __init__(self, name, description, host, port):
        super().__init__(name, description)
        self.host = host
        self.port = port

    def run(self, db_session):
        if is_not_blank(self.host):
            server_url = f'http://{self.host}:{self.port}'
            ticket_id = self._submit_job(server_url)
            if ticket_id is not None:
                self._poll_job(server_url, ticket_id)
        else:
            self.critical('Limited scraper host is not configured')
            self.set_failure()

    def _submit_job(self, server_url):
        self.info(f'Submitting cookie refresh job to {server_url}')

        try:
            submit_resp = requests.post(f'{server_url}/jobs', json={'task_type': 'refresh_cookies'}, timeout=30)
        except Exception as e:
            self.critical(f'Failed to submit remote job: {e}')
            self.set_failure()
            return None

        if submit_resp.status_code != 202:
            self.critical(f'Remote submission returned {submit_resp.status_code}: {submit_resp.text}')
            self.set_failure()
            return None

        try:
            ticket_id = submit_resp.json().get('ticket_id')
        except Exception:
            ticket_id = None

        if not ticket_id:
            self.critical('No ticket_id in remote submission response')
            self.set_failure()
            return None

        self.info(f'Remote job queued with ticket: {ticket_id}')
        return ticket_id

    def _poll_job(self, server_url, ticket_id):
        consecutive_errors = 0

        while True:
            time.sleep(self.POLL_INTERVAL)

            if self.is_cancelled:
                self.critical('Task cancelled, stopping')
                return

            try:
                status_resp = requests.get(f'{server_url}/jobs/{ticket_id}', timeout=30)
                if status_resp.status_code != 200:
                    raise RuntimeError(f'status returned {status_resp.status_code}')
                data = status_resp.json()
            except Exception as e:
                consecutive_errors += 1
                self.warn(f'Remote status poll failed ({consecutive_errors}/{self.MAX_CONSECUTIVE_POLL_ERRORS}): {e}')
                if consecutive_errors >= self.MAX_CONSECUTIVE_POLL_ERRORS:
                    self.critical('Too many consecutive remote poll failures, stopping')
                    self.set_failure()
                    return
                continue

            consecutive_errors = 0

            progress = data.get('progress')
            subprogress = data.get('subprogress')

            if progress is not None:
                self.update_progress(float(progress))
            if subprogress is not None:
                self.update_percent(float(subprogress))

            status = data.get('status')

            if self.can_trace():
                self.trace(f'Remote status: {status}')

            if status == 'finished':
                self.info('Scraper cookies are fresh')
                self.update_progress(100)
                self.set_worked()
                return
            elif status == 'failure':
                self.critical(f"Remote job failed: {data.get('error', 'unknown error')}")
                self.set_failure()
                return
