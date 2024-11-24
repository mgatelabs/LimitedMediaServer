import argparse
from typing import List, Dict

from flask_sqlalchemy.session import Session

from app_properties import AppPropertyDefinition
from constants import PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER, PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER, \
    PROPERTY_SERVER_MEDIA_TEMP_FOLDER


# Function to create a string argument for a plugin
def plugin_string_arg(arg_name: str, arg_id: str, arg_description: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "string",
        "description": arg_description,
        "values": []
    }

# Function to create a filename argument for a plugin
def plugin_filename_arg(arg_name: str, arg_id: str, arg_description: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "filename",
        "description": arg_description,
        "values": []
    }

# Function to create a long string argument for a plugin
def plugin_long_string_arg(arg_name: str, arg_id: str, arg_description: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "longstring",
        "description": arg_description,
        "values": []
    }


# Function to create a URL argument for a plugin
def plugin_url_arg(arg_name: str, arg_id: str, arg_description: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "url",
        "description": arg_description,
        "values": []
    }


# Function to create a select argument for a plugin
def plugin_select_arg(arg_name: str, arg_id: str, default_value: str, values: List[Dict[str, str]],
                      arg_description: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "select",
        "default": default_value,
        "description": arg_description,
        "values": values
    }


# Function to create select values for a plugin argument
def plugin_select_values(*args) -> list:
    # Check if the number of arguments is divisible by 2 and > 0
    if len(args) == 0 or (len(args) % 2) != 0:
        raise ValueError("The number of arguments must be divisible by 2 and greater than 0.")

    # Create a list of dicts, pairing each consecutive argument
    result = [{"name": args[i], "id": args[i + 1]} for i in range(0, len(args), 2)]

    return result


# Predefined select values for Yes/No options
PLUGIN_VALUES_Y_N = plugin_select_values("No", 'n', 'Yes', 'y')


# Function to create a media folder chooser move folder argument for a plugin
def plugin_media_folder_chooser_move_folder_arg(arg_name: str, arg_id: str, arg_description: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "mfcmf",
        "description": arg_description,
        "values": []
    }


# Function to create a media folder chooser move folder argument for a plugin
def plugin_media_folder_chooser_folder_arg(arg_name: str, arg_id: str, arg_description: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "mfc",
        "description": arg_description,
        "values": []
    }


# Function to create a media folder display argument for a plugin
def plugin_media_folder_display_arg(arg_name: str, arg_id: str, arg_description: str = ''):
    return {
        "name": arg_name,
        "id": arg_id,
        "type": "mfd",
        "description": arg_description,
        "values": []
    }


# Base class for all action plugins
class ActionPlugin:
    """
    This is the root class for Plugins. This is a plugin that is in the generic Plugins menu.
    """
    counter = 0  # Initialize the counter to 0 by default

    def __init__(self):
        super().__init__()
        self.type = 'ACTION'
        self.sort_group = self.get_sort()['id']
        self.sort_sequence = self.get_sort()['sequence']

    @classmethod
    def next_counter(cls):
        cls.counter += 1
        return cls.counter

    def get_type(self):
        return self.type

    def get_sort(self):
        return {'id': 'default', 'sequence': ActionPlugin.next_counter()}

    def add_args(self, parser: argparse):
        raise NotImplementedError

    # noinspection PyMethodMayBeStatic
    def get_properties(self) -> list[AppPropertyDefinition]:
        return []

    def use_args(self, args):
        raise NotImplementedError

    def get_action_name(self):
        raise NotImplementedError

    def get_action_id(self):
        raise NotImplementedError

    def get_action_icon(self):
        return 'memory'

    def get_action_args(self):
        raise NotImplementedError

    def process_action_args(self, args):
        raise NotImplementedError

    def create_task(self, db_session: Session, args):
        raise NotImplementedError

    def absorb_config(self, config):
        pass

    def is_ready(self):
        return True

    def is_video(self):
        """
        Is this for Videos?
        :return: True for video support?
        """
        return False

    def is_book(self):
        """
        Is this for Books?
        :return: True for book support?
        """
        return False

    def is_standalone(self):
        """
        Is this a standalone plugin?
        :return: True if standalone, False otherwise
        """
        return True

    def get_category(self):
        """
        The type of plugin?
        :return: "general", "book", "series", "utility"
        """
        return "general"

    def get_feature_flags(self):
        return 0


# Subclass for series action plugins
class ActionSeriesPlugin(ActionPlugin):
    """
    This is a subclass for Context based Plugins. These are accessible from the Book/Video Series page.
    """

    def __init__(self):
        super().__init__()
        self.type = 'ACTIONSERIES'

    def get_action_args(self):
        return [{
            "name": "Series ID",
            "id": "series_id",
            "type": "string",
            "values": []
        }]

    def get_category(self):
        return 'series'

    def is_standalone(self):
        """
        Actions are not Standalone
        :return: False
        """
        return False


# Subclass for book action plugins
class ActionBookPlugin(ActionPlugin):
    """
    This is a subclass for Context based Plugins. These are accessible from the Book/Video Series page.
    """

    def __init__(self):
        super().__init__()
        self.type = 'ACTIONBOOK'

    def get_action_args(self):
        return [{
            "name": "Book ID",
            "id": "series_id",
            "type": "string",
            "values": []
        }]

    def get_category(self):
        return 'book'

    def is_standalone(self):
        """
        Actions are not Standalone
        :return: False
        """
        return False


# Subclass for media folder action plugins
class ActionMediaPlugin(ActionPlugin):
    """
    This is a subclass for Context based Plugins. These are accessible from the MediaFolder page.
    """

    def __init__(self):
        super().__init__()
        self.type = 'MEDIA'
        self.primary_path = ''
        self.archive_path = ''
        self.temp_path = ''

    def get_action_args(self):
        return []

    def absorb_config(self, config):
        """
        Absorb configuration settings.
        """
        self.primary_path = config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER]
        self.archive_path = config[PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER]
        self.temp_path = config[PROPERTY_SERVER_MEDIA_TEMP_FOLDER]

    def get_category(self):
        return 'media'


# Subclass for media folder action plugins
class ActionMediaFolderPlugin(ActionPlugin):
    """
    This is a subclass for Context based Plugins. These are accessible from the MediaFolder page.
    """

    def __init__(self):
        super().__init__()
        self.type = 'ACTIONMEDIAFOLDER'
        self.primary_path = ''
        self.archive_path = ''
        self.temp_path = ''

    def get_action_args(self):
        return [
            plugin_media_folder_display_arg('Folder', 'folder_id', 'Referenced folder')
        ]

    def absorb_config(self, config):
        """
        Absorb configuration settings.
        """
        self.primary_path = config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER]
        self.archive_path = config[PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER]
        self.temp_path = config[PROPERTY_SERVER_MEDIA_TEMP_FOLDER]

    def get_category(self):
        return 'media_folder'

    def is_standalone(self):
        """
        Actions are not Standalone
        :return: False
        """
        return False


# Subclass for media file action plugins
class ActionMediaFilePlugin(ActionPlugin):
    """
    This is a subclass for Context based Plugins. These are accessible for a given MediaFile.
    """

    def __init__(self):
        super().__init__()
        self.type = 'ACTIONMEDIAFILE'
        self.primary_path = ''
        self.archive_path = ''
        self.temp_path = ''

    def get_action_args(self):
        return [{
            "name": "File ID",
            "id": "file_id",
            "type": "string",
            "values": []
        }]

    def absorb_config(self, config):
        """
        Absorb configuration settings.
        """
        self.primary_path = config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER]
        self.archive_path = config[PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER]
        self.temp_path = config[PROPERTY_SERVER_MEDIA_TEMP_FOLDER]

    def get_category(self):
        return 'media_file'

    def is_standalone(self):
        """
        Actions are not Standalone
        :return: False
        """
        return False
