import importlib
import os

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
    Load and return all processors from the specified directory.
    """
    all_processors = []
    for filename in os.listdir(plugin_dir):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]  # Remove .py extension
            module = importlib.import_module(f'{plugin_dir}.{module_name}')
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, type) and obj != CustomDownloadInterface:
                    if issubclass(obj, CustomDownloadInterface):
                        # noinspection PyArgumentList
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