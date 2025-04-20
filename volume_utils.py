import importlib
import json
import os
import re
import pkgutil

from processors.GenericBasicProcessor import GenericBasicProcessor
from processors.processor_core import CustomDownloadInterface


def check_and_insert(data_list, new_entry):
    exists = any(entry for entry in data_list if entry == new_entry)

    if not exists:
        data_list.append(new_entry)
        data_list.sort(key=lambda x: (x["book"], x["chapter"], x["page"]))

    return data_list


def remove_entry_from_list(data_list, remove_entry):
    # Create a new list excluding the entry to be removed
    data_list = [entry for entry in data_list if not (
            entry["book"] == remove_entry["book"] and entry["chapter"] == remove_entry["chapter"] and entry[
        "page"] == remove_entry["page"])]
    return data_list


def get_processors(plugin_dir):
    """
    Load and return all processors from the specified directory/package.
    """
    all_processors = []
    package = importlib.import_module(plugin_dir)

    # Use pkgutil to find modules in the package
    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if not is_pkg:  # Skip sub-packages
            module = importlib.import_module(f'{plugin_dir}.{module_name}')
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type) and
                    issubclass(obj, CustomDownloadInterface) and
                    obj not in {GenericBasicProcessor} and
                    obj != CustomDownloadInterface
                ):
                    # Instantiate and append to the list
                    all_processors.append(obj())

    return sorted(all_processors, key=custom_processor_sort_key)


# Define a sorting key function for processors
def custom_processor_sort_key(obj):
    return obj.processor_name

def get_volume_max_rating(user_details):
    max_rating = 0
    if 'limits' in user_details and 'volume' in user_details['limits']:
        max_rating = user_details['limits']['volume']
    return max_rating


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
