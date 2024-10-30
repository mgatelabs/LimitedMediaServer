import importlib
import os

from plugin_system import ActionSeriesPlugin, ActionBookPlugin, ActionPlugin, ActionMediaFolderPlugin, \
    ActionMediaFilePlugin, ActionMediaPlugin


# Define a sorting key function for plugins
def custom_plugin_sort_key(obj):
    return obj.sort_group, obj.sort_sequence


def get_plugins(plugin_dir):
    """
    Load and return all plugins from the specified directory.
    """
    all_plugins = []
    for filename in os.listdir(plugin_dir):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]  # Remove .py extension
            module = importlib.import_module(f'{plugin_dir}.{module_name}')
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, type) and obj != ActionSeriesPlugin and obj != ActionBookPlugin and obj != ActionMediaFolderPlugin and obj != ActionMediaFilePlugin and obj != ActionMediaPlugin and obj != ActionPlugin:

                    if issubclass(obj, ActionPlugin):
                        plugin_instance = obj()
                        all_plugins.append(plugin_instance)
    return {'all': sorted(all_plugins, key=custom_plugin_sort_key)}
