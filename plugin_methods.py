from typing import List, Dict


def plugin_string_arg(arg_name: str, arg_id: str, arg_description: str = '', prefix_lang_id: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "string",
        "description": arg_description,
        "values": [],
        "prefix_lang_id": prefix_lang_id,
    }


def plugin_filename_arg(arg_name: str, arg_id: str, arg_description: str = '', prefix_lang_id: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "filename",
        "description": arg_description,
        "values": [],
        "prefix_lang_id": prefix_lang_id,
    }


def plugin_long_string_arg(arg_name: str, arg_id: str, arg_description: str = '', prefix_lang_id: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "longstring",
        "description": arg_description,
        "values": [],
        "prefix_lang_id": prefix_lang_id,
    }


def plugin_url_arg(arg_name: str, arg_id: str, arg_description: str = '', prefix_lang_id: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "url",
        "description": arg_description,
        "values": [],
        "prefix_lang_id": prefix_lang_id,
    }


def plugin_select_arg(arg_name: str, arg_id: str, default_value: str, values: List[Dict[str, str]],
                      arg_description: str = '', prefix_lang_id: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "select",
        "default": default_value,
        "description": arg_description,
        "values": values,
        "prefix_lang_id": prefix_lang_id,
    }


def plugin_select_values(*args) -> list:
    # Check if the number of arguments is divisible by 2 and > 0
    if len(args) == 0 or (len(args) % 2) != 0:
        raise ValueError("The number of arguments must be divisible by 2 and greater than 0.")

    # Create a list of dicts, pairing each consecutive argument
    result = [{"name": args[i], "id": args[i + 1]} for i in range(0, len(args), 2)]

    return result


PLUGIN_VALUES_Y_N = plugin_select_values("No", 'n', 'Yes', 'y')


def plugin_media_folder_chooser_move_folder_arg(arg_name: str, arg_id: str, arg_description: str = '',
                                                prefix_lang_id: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "mfcmf",
        "description": arg_description,
        "values": [],
        "prefix_lang_id": prefix_lang_id,
    }


def plugin_media_folder_chooser_folder_arg(arg_name: str, arg_id: str, arg_description: str = '',
                                           prefix_lang_id: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "mfc",
        "description": arg_description,
        "values": [],
        "prefix_lang_id": prefix_lang_id,
    }


def plugin_media_folder_display_arg(arg_name: str, arg_id: str, arg_description: str = '', prefix_lang_id: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "mfd",
        "description": arg_description,
        "values": [],
        "prefix_lang_id": prefix_lang_id,
    }


def add_logging_arg(args: list) -> list:
    """
    Add a logging argument to the list of arguments.

    Args:
        args (list): The original list of arguments.

    Returns:
        list: The updated list of arguments with the logging argument added.
    """
    result = args.copy()  # Copy the original arguments list

    # Append the logging argument to the list
    result.append(plugin_select_arg("Logging Level", "_logging_level", "20", DEFAULT_LOGGING_VALUES, prefix_lang_id='com'))
    result.append(plugin_select_arg("Prevent Duplicate Tasks", "_duplicate_checking", "y", PLUGIN_VALUES_Y_N, prefix_lang_id='com'))

    # Ensure each argument has a description
    for row in result:
        if 'description' not in row:
            row['description'] = ''

    return result


DEFAULT_LOGGING_VALUES = plugin_select_values("Trace", '0', "Debug", '10', "Info", '20', "Warning", '30', "Error", '40', "Critical", '50')
