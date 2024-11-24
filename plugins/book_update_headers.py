import argparse

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_APP
from plugin_system import ActionPlugin, plugin_long_string_arg
from thread_utils import TaskWrapper
from volume_utils import parse_curl_headers, save_headers_to_json


class UpdateHeaders(ActionPlugin):
    """
    We use headers from Chrome to access protected webpages.  This updates the local header definition file.
    """

    def __init__(self):
        super().__init__()

    def get_sort(self):
        return {'id': 'book_workers', 'sequence': 99}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Update Header'

    def get_action_id(self):
        return 'action.book.set.header'

    def get_action_icon(self):
        return 'title'

    def get_feature_flags(self):
        return MANAGE_APP

    def get_action_args(self):
        return [plugin_long_string_arg('Headers', 'headers',
                                       'Open Chrome and access any site that is protected by a service you want to get around.  Open chrome dev tools (F12).  Refresh the page.  In the Developer tools network tab, click the page, the 1st item, right click, copy, Copy as cURL (Bash).  Paste that here.')]

    def process_action_args(self, args):
        results = []

        if 'headers' not in args or args['headers'] is None or args['headers'] == '':
            results.append('headers is required')

        if not args['headers'].startswith('curl'):
            results.append('headers must be a curl bash command')
        else:
            header_dict = parse_curl_headers(args['headers'])
            args['headers'] = header_dict

        if len(results) > 0:
            return results
        return None

    def get_category(self):
        return 'book'

    def create_task(self, db_session: Session, args):
        return UpdateVolumeHeader(args['headers'])


class UpdateVolumeHeader(TaskWrapper):
    def __init__(self, headers):
        super().__init__('Headers', 'Update headers.json file')
        self.headers = headers

    def run(self, db_session):
        self.info('Writing headers.json file')
        self.set_worked()

        if self.can_debug():
            for key in self.headers.keys():
                self.debug(f'{key} - {self.headers[key]}')

        save_headers_to_json(self.headers, 'headers.json')
