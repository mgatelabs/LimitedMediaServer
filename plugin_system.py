import argparse

from flask_sqlalchemy.session import Session

from app_properties import AppPropertyDefinition
from constants import PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER, PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER, \
    PROPERTY_SERVER_MEDIA_TEMP_FOLDER, PROPERTY_SERVER_VOLUME_FOLDER, PROPERTY_SERVER_VOLUME_FORMAT, APP_KEY_PROCESSORS
from plugin_methods import plugin_media_folder_display_arg, add_logging_arg, plugin_string_arg
from text_utils import is_not_blank


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
        self.prefix_lang_id = ''

    @classmethod
    def next_counter(cls):
        cls.counter += 1
        return cls.counter

    def to_json(self) -> dict:
        return {
            "id": self.get_action_id(),
            "icon": self.get_action_icon(),
            "name": self.get_action_name(),
            "args": add_logging_arg(self.get_action_args()),
            "category": self.get_category(),
            "standalone": self.is_standalone(),
            "prefix_lang_id": self.prefix_lang_id
        }

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
        return []

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
        return [plugin_string_arg("Series ID", "series_id", 'Series ID', 'com')]

    def get_category(self):
        return 'series'

    def is_standalone(self):
        """
        Actions are not Standalone
        :return: False
        """
        return False


# Subclass for book action plugins
class ActionBookGeneralPlugin(ActionPlugin):
    """
    This is a subclass for Non-specific Book based Plugins. These are accessible from the global Book plugins menu.
    """

    def __init__(self):
        super().__init__()
        self.type = 'ACTIONBOOK'
        self.book_storage_folder = ''
        self.book_storage_format = 'PNG'
        self.processors = []

    def get_action_args(self):
        return []

    def absorb_config(self, config):
        """
        Absorb configuration settings.
        """
        super().absorb_config(config)
        self.book_storage_folder = config[PROPERTY_SERVER_VOLUME_FOLDER]
        self.book_storage_format = config[PROPERTY_SERVER_VOLUME_FORMAT]
        self.processors = config[APP_KEY_PROCESSORS]

    def is_ready(self):
        return super().is_ready() and is_not_blank(self.book_storage_folder) and is_not_blank(self.book_storage_format)

    def get_category(self):
        return 'book'

    def is_standalone(self):
        """
        General are Standalone
        :return: True
        """
        return True

# Subclass for book action plugins
class ActionBookSpecificPlugin(ActionPlugin):
    """
    This is a subclass for Context based Plugins. These are accessible from the Book Series page.
    """

    def __init__(self):
        super().__init__()
        self.type = 'ACTIONBOOK'
        self.book_storage_folder = ''
        self.book_storage_format = 'PNG'
        self.processors = []

    def get_action_args(self):
        return [plugin_string_arg("Book ID", "book_id", 'The Book to process', 'com')]

    def absorb_config(self, config):
        """
        Absorb configuration settings.
        """
        self.book_storage_folder = config[PROPERTY_SERVER_VOLUME_FOLDER]
        self.book_storage_format = config[PROPERTY_SERVER_VOLUME_FORMAT]
        self.processors = config[APP_KEY_PROCESSORS]

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
            plugin_media_folder_display_arg('Folder', 'folder_id', 'Referenced folder', 'com')
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
        return [plugin_string_arg("File ID", "file_id", 'The file to process', 'com')]

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

# Subclass for media files action plugins
class ActionMediaFilesPlugin(ActionPlugin):
    """
    This is a subclass for Context based Plugins. These are accessible for a selected MediaFiles.
    """

    def __init__(self):
        super().__init__()
        self.type = 'ACTIONMEDIAFILES'
        self.primary_path = ''
        self.archive_path = ''
        self.temp_path = ''

    def get_action_args(self):
        return [plugin_string_arg("File ID", "file_id", 'The file to process', 'com')]

    def absorb_config(self, config):
        """
        Absorb configuration settings.
        """
        self.primary_path = config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER]
        self.archive_path = config[PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER]
        self.temp_path = config[PROPERTY_SERVER_MEDIA_TEMP_FOLDER]

    def get_category(self):
        return 'media_files'

    def is_standalone(self):
        """
        Actions are not Standalone
        :return: False
        """
        return False
