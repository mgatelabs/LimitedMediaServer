import argparse
import json
import re

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_APP
from plugin_system import ActionPlugin, plugin_long_string_arg
from thread_utils import TaskWrapper


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

    def create_task(self, session: Session, args):
        return CreateUpdateHeader("Update", 'Headers', args['headers'])


def parse_curl_headers(curl_command):
    headers = {}
    # Replace newline characters with a space

    list_of_strings = [line.strip().rstrip('\\') for line in curl_command.split('\n')]

    header_pattern = r'^-H [\'"](.*?)[\'"]$'

    for line in list_of_strings:
        line = line.strip()

        # Extract headers using regular expression
        matches = re.findall(header_pattern, line)
        for match in matches:
            key_value = match.split(':', 1)  # Split at the first colon to handle multiple colons in header value
            if len(key_value) == 2:
                key, value = key_value
                key = key.strip()
                if 'authority' != key:  # This is specific to the site, so skip it
                    value = value.strip()
                    headers[key] = value

    return headers


def save_headers_to_json(headers, filename='headers.json'):
    with open(filename, 'w') as json_file:
        json.dump(headers, json_file, indent=4)


class CreateUpdateHeader(TaskWrapper):
    def __init__(self, name, description, headers):
        super().__init__(name, description)
        self.headers = headers

    def run(self, db_session):
        self.add_log('Writing headers.json file')
        self.set_worked()

        if self.can_trace():
            for key in self.headers.keys():
                self.trace(f'{key} - {self.headers[key]}')

        save_headers_to_json(self.headers, 'headers.json')
