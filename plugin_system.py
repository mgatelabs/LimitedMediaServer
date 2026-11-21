import argparse

from flask_sqlalchemy.session import Session

from app_properties import AppPropertyDefinition
from app_utils import value_is_in_list
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

    # AI-facing metadata. Override per plugin class.
    AI_QUICK_DESCRIPTION = ''
    AI_LONG_DESCRIPTION = ''

    def __init__(self):
        super().__init__()
        self.type = 'ACTION'
        self.sort_group = self.get_sort()['id']
        self.sort_sequence = self.get_sort()['sequence']
        self.prefix_lang_id = ''
        self.available_to_menu = True

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

    def get_ai_quick_description(self):
        if is_not_blank(type(self).AI_QUICK_DESCRIPTION):
            return type(self).AI_QUICK_DESCRIPTION
        return self.get_action_name()

    def get_ai_long_description(self):
        if is_not_blank(type(self).AI_LONG_DESCRIPTION):
            return type(self).AI_LONG_DESCRIPTION
        return self.get_action_name() + ' action on the media server.'

    def get_type(self):
        return self.type

    def get_sort(self):
        return {'id': 'default', 'sequence': ActionPlugin.next_counter()}

    def is_available_to_menu(self):
        return self.available_to_menu

    def add_args(self, parser: argparse):
        raise NotImplementedError

    # noinspection PyMethodMayBeStatic
    def get_properties(self) -> list[AppPropertyDefinition]:
        return self.generate_properties()

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

    def generate_properties(self):
        args = self.get_action_args()
        result = []
        for arg in args:
            if 'type' in arg and arg['type'] == 'select':
                possible_values = ['']
                possible_description = []
                for value in arg['values']:
                    possible_values.append(value['id'])
                    possible_description.append('"' + value['id'] + '" : "' + value['name']+'"')

                result.append(AppPropertyDefinition('PLUGIN.DEFAULT.' + self.get_action_id() + '_' + arg['id'], '',
                                      'Default value for the argument ' + arg['name'] + '.  Value List: ' + '; '.join(possible_description),
                                      [value_is_in_list(possible_values)]))

        return result


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
        self.book_storage_format = 'WEBP'
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
        self.book_storage_format = 'WEBP'
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


def effective_arg_default(plugin_id: str, arg: dict, config: dict) -> str:
    if arg.get('type') == 'select':
        key = 'PLUGIN.DEFAULT.' + plugin_id + '_' + arg['id']
        if key in config and config[key] != '':
            return config[key]
    return arg.get('default', '')


def build_ai_arg(plugin_id: str, arg: dict, config: dict) -> dict:
    default_value = effective_arg_default(plugin_id, arg, config)
    item = {
        'id': arg['id'],
        'name': arg['name'],
        'type': arg['type'],
        'description': arg.get('description', ''),
    }
    if arg.get('type') == 'select':
        item['values'] = [{'id': v['id'], 'name': v['name']} for v in arg.get('values', [])]
    if default_value != '':
        item['default'] = default_value
    item['required'] = default_value == ''
    return item


def ai_args_for_plugin(plugin: ActionPlugin, config: dict) -> list:
    plugin_id = plugin.get_action_id()
    args = add_logging_arg(plugin.get_action_args())
    return [build_ai_arg(plugin_id, arg, config) for arg in args]


def _ai_arg_detail_line(arg: dict, default_value: str) -> str:
    if default_value == '':
        line = '- ' + arg['id'] + ' (' + arg['type'] + ', required) '
    else:
        line = '- ' + arg['id'] + ' (' + arg['type'] + ', default=' + default_value + ') '
    line += arg['name'] + ' - ' + arg.get('description', '')
    if arg.get('type') == 'select':
        values_text = ', '.join('"' + v['id'] + '"=' + v['name'] for v in arg.get('values', []))
        line += ' values: ' + values_text
    return line


def ai_usage_notes(plugin: ActionPlugin, config: dict) -> str:
    plugin_id = plugin.get_action_id()
    args = add_logging_arg(plugin.get_action_args())
    lines = [plugin.get_ai_long_description()]
    for arg in args:
        lines.append(_ai_arg_detail_line(arg, effective_arg_default(plugin_id, arg, config)))

    overrides = []
    for arg in args:
        if arg.get('type') != 'select':
            continue
        effective = effective_arg_default(plugin_id, arg, config)
        if effective != '' and effective != arg.get('default', ''):
            overrides.append('PLUGIN.DEFAULT.' + plugin_id + '_' + arg['id'] + '=' + effective)

    if overrides:
        lines.append('System override defaults in effect: ' + ', '.join(overrides) + '.')
    else:
        lines.append('System override defaults in effect: none.')

    return '\n'.join(lines)
