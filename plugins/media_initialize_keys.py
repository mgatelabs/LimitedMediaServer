import argparse

from flask_sqlalchemy.session import Session

from constants import MEDIA_FOLDER_KEY_PURPOSE_DEFAULT
from feature_flags import MANAGE_MEDIA
from media_queries import add_media_folder_key_value, find_folder_by_id
from plugin_methods import plugin_select_arg, plugin_select_values
from plugin_system import ActionMediaFolderPlugin
from text_utils import is_blank
from thread_utils import TaskWrapper

# Intentionally hacky bootstrap: this hardcodes, per plugin, which folder keys that plugin
# needs. There is no generic "a plugin declares its keys" system yet. When that system is
# built, the registry below should be replaced by it.
INIT_KEYS_PLUGIN_SSH = 'ssh'
INIT_KEYS_PLUGINS = {
    INIT_KEYS_PLUGIN_SSH: {
        'name': 'SSH (Media Folder Sync)',
        # Keys read by plugins/media_sync_folders.py
        'keys': ['SSH_PATH', 'SSH_REGEX'],
    },
}


def init_keys_keys_for(plugin_type):
    """Return the list of keys the given plugin type needs, or None when unknown."""
    entry = INIT_KEYS_PLUGINS.get(plugin_type)
    if entry is None:
        return None
    return entry['keys']


class InitializeKeysFolderPlugin(ActionMediaFolderPlugin):
    """
    Insert the MediaFolderKeyValue rows a plugin needs into a single media folder.
    Existing keys are never overwritten.
    """
    AI_QUICK_DESCRIPTION = ('Initializes the folder key/value rows required by a selected '
                            'plugin (currently SSH sync): inserts SSH_PATH and SSH_REGEX into '
                            'the folder when missing, never overwriting existing keys.')
    AI_LONG_DESCRIPTION = (
        'Bootstraps the MediaFolderKeyValue rows that other plugins read from a single media '
        'folder. The caller selects which plugin to set up (currently only "SSH (Media Folder '
        'Sync)", which needs SSH_PATH - the remote destination path - and SSH_REGEX - the '
        'semicolon-delimited file-name filter). For each required key that does not already '
        'exist for the folder (default purpose), a new row is inserted with a blank value; '
        'existing keys are skipped and never overwritten. Keys are inserted one row at a time '
        'so an individual failure does not roll back the others. The task reports how many '
        'keys were inserted and how many already existed.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'medinitkey'

    def get_sort(self):
        return {'id': 'media_initialize_keys', 'sequence': 0}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Initialize Keys'

    def get_action_id(self):
        return 'action.folder.initialize.keys'

    def get_action_icon(self):
        return 'key'

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def get_action_args(self):
        result = super().get_action_args()
        result.append(plugin_select_arg('Plugin', 'plugin_type', INIT_KEYS_PLUGIN_SSH,
                                        plugin_select_values(
                                            INIT_KEYS_PLUGINS[INIT_KEYS_PLUGIN_SSH]['name'], INIT_KEYS_PLUGIN_SSH),
                                        'The plugin to initialize folder keys for.',
                                        prefix_lang_id='medinitkey'))
        return result

    def process_action_args(self, args):
        results = []
        if 'folder_id' not in args or not args['folder_id']:
            results.append('folder_id is required')
        if 'plugin_type' not in args or is_blank(args['plugin_type']):
            results.append('plugin_type is required')
        elif init_keys_keys_for(args['plugin_type']) is None:
            results.append('plugin_type is not a supported plugin')
        return results if results else None

    def create_task(self, db_session: Session, args):
        return InitializeKeysFolderTask(
            "InitializeKeys",
            f'Initialize keys: {args.get("folder_name", args["folder_id"])}',
            args['folder_id'],
            args['plugin_type'],
        )


class InitializeKeysFolderTask(TaskWrapper):
    def __init__(self, name, description, folder_id: str, plugin_type: str):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.plugin_type = plugin_type

    def run(self, db_session: Session):
        keys = init_keys_keys_for(self.plugin_type)
        if keys is None:
            self.critical(f'Unsupported plugin type: {self.plugin_type}')
            self.set_failure()
            return

        folder = find_folder_by_id(self.folder_id, db_session)
        if folder is None:
            self.critical('Folder not found in database.')
            self.set_failure()
            return

        existing = folder.get_keys_for_purpose(MEDIA_FOLDER_KEY_PURPOSE_DEFAULT)

        inserted = 0
        skipped = 0
        for key in keys:
            if self.is_cancelled:
                self.info('Leaving early')
                break

            if key in existing:
                self.info(f'Key already exists, skipping: {key}')
                skipped = skipped + 1
                continue

            # add_media_folder_key_value commits on its own, so one bad row does not roll
            # back the others.
            row = add_media_folder_key_value(db_session, self.folder_id, key, None,
                                             MEDIA_FOLDER_KEY_PURPOSE_DEFAULT)
            if row is None:
                self.error(f'Could not insert key: {key}')
                continue

            inserted = inserted + 1
            self.info(f'Inserted key: {key}')

        # inserted==0 and skipped==0 can only mean we were cancelled before any key was
        # handled, which is not a failure.
        self.info(f'Inserted {inserted} of {len(keys)} key(s); {skipped} already existed.')
        self.set_worked()
