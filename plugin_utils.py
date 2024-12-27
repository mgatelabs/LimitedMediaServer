import importlib
import pkgutil

from plugin_system import ActionSeriesPlugin, ActionBookSpecificPlugin, ActionPlugin, ActionMediaFolderPlugin, \
    ActionMediaFilePlugin, ActionMediaPlugin, ActionBookGeneralPlugin


# Define a sorting key function for plugins
def custom_plugin_sort_key(obj):
    return obj.sort_group, obj.sort_sequence


def get_plugins(plugin_dir):
    """
    Load and return all plugins from the specified directory/package.
    """
    all_plugins = []
    package = importlib.import_module(plugin_dir)

    # Use pkgutil to find modules in the package
    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if not is_pkg:  # Skip sub-packages
            module = importlib.import_module(f'{plugin_dir}.{module_name}')
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type) and
                    issubclass(obj, ActionPlugin) and
                    obj not in {ActionSeriesPlugin, ActionBookGeneralPlugin, ActionBookSpecificPlugin, ActionMediaFolderPlugin, ActionMediaFilePlugin, ActionMediaPlugin, ActionPlugin}
                ):
                    plugin_instance = obj()
                    all_plugins.append(plugin_instance)

    return {'all': sorted(all_plugins, key=custom_plugin_sort_key)}


