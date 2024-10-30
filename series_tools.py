import json
import os
import re

from library_utils import write_library_config
from thread_utils import TaskWrapper


def get_library_items(config_path, is_authenticated, sync_only: bool = False, filtered_name: str = None,
                      rating_limit=200):
    work_data = []

    if os.path.exists(config_path) and os.path.isdir(config_path):
        items = os.listdir(config_path) if filtered_name is None else [filtered_name + '.json']

        for filename in items:
            if filename.endswith('.json'):
                file_path = os.path.join(config_path, filename)
                with open(file_path, 'r') as f:
                    data = json.load(f)

                    result = parse_series_definition(data)

                    if result is None:
                        continue

                    if result['rating'] > rating_limit:
                        continue

                    if sync_only and not result['sync']:
                        continue

                    work_data.append(result)

    return work_data


def parse_series_definition(data):
    series_id = data.get('id')
    series_name = data.get('name')
    if series_id and series_name:

        result = {'id': series_id, 'name': series_name}

        if 'sync' in data:
            result['sync'] = data.get('sync')
        else:
            result['sync'] = False

        if 'offline' in data:
            result['offline'] = data.get('offline')
        else:
            result['offline'] = False

        if 'visibility' in data:
            result['visibility'] = data.get('visibility')
        else:
            result['visibility'] = 'restricted'

        if 'rating' in data:
            result['rating'] = data.get('rating')
        else:
            result['rating'] = 200

        if 'lstdate' in data:
            result['lstdate'] = data.get('lstdate')
        else:
            result['lstdate'] = 20010101

        return result

    return None


def validate_series_definition(data):
    if not isinstance(data, dict):
        return False, "JSON data is not a dictionary"

    # Define constraints for keys and values
    constraints = {
        "id": {"type": str, "regex": r"^[A-Za-z0-9-_]+$"},
        "name": {"type": str, "regex": r"^.+$"},
        "visibility": {"type": str, "allowed_values": ["restricted", "public"]},
        "sync": {"type": bool},
        "rating": {"type": int},
        "lstdate": {"type": int, "required": False},
        "offline": {"type": bool},
    }

    for key, constraint in constraints.items():
        if key not in data:
            if 'required' in constraint and constraint['required'] == False:
                continue
            return False, f"Key '{key}' is missing"

        value = data[key]
        value_type = type(value)

        if "type" in constraint and value_type != constraint["type"]:
            return False, f"Value of '{key}' should be of type {constraint['type'].__name__}"

        if "allowed_values" in constraint and value not in constraint["allowed_values"]:
            return False, f"Value of '{key}' is not allowed"

        if "regex" in constraint and not re.match(constraint["regex"], value):
            return False, f"Value of '{key}' does not match the required pattern"

    # Check for extra keys
    extra_keys = set(data.keys()) - set(constraints.keys())
    if extra_keys:
        return False, f"JSON contains extra keys: {', '.join(extra_keys)}"

    return True, "JSON data is valid"


class CreateSeriesTask(TaskWrapper):
    def __init__(self, name, description, data, video_out):
        super().__init__(name, description)
        self.data = data
        self.video_out = video_out

    def run(self, db_session):

        valid, message = validate_series_definition(self.data)

        if not valid:
            self.error(message)
            self.set_failure(True)
        else:
            write_library_config(self.data, os.path.join(self.video_out, self.data['id'] + '.json'))
            os.makedirs(os.path.join(self.video_out, self.data['id']), exist_ok=True)
