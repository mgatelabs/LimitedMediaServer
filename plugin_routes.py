from flask import Blueprint, current_app, jsonify
from auth_utils import shall_authenticate_user
from common_utils import generate_success_response
from plugin_system import plugin_select_values, plugin_select_arg, PLUGIN_VALUES_Y_N

# Create a Blueprint for plugin routes
plugin_blueprint = Blueprint('plugin', __name__)

# Default logging values for plugins
DEFAULT_LOGGING_VALUES = plugin_select_values("Trace", '0', "Debug", '10', "Info", '20', "Warning", '30', "Error", '40', "Critical", '50')

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
    result.append(plugin_select_arg("Logging Level", "_logging_level", "20", DEFAULT_LOGGING_VALUES))
    result.append(plugin_select_arg("Prevent Duplicate Tasks", "_duplicate_checking", "y", PLUGIN_VALUES_Y_N))

    # Ensure each argument has a description
    for row in result:
        if 'description' not in row:
            row['description'] = ''

    return result

@plugin_blueprint.route('/list', methods=['POST'])
@shall_authenticate_user(plugin_blueprint)
def list_book_actions(user_details: dict) -> jsonify:
    """
    List all available actions for books.

    Args:
        user_details (dict): The details of the authenticated user.

    Returns:
        jsonify: A JSON response containing the list of available actions.
    """
    plugins = current_app.config['PLUGINS']['all']  # Retrieve all plugins from the app config

    results = []

    # Iterate through each plugin and check if it is ready and matches the user's feature flags
    for plugin in plugins:
        if plugin.is_ready() and (plugin.get_feature_flags() & user_details['features']) == plugin.get_feature_flags():
            # Create a wrapper dictionary for the plugin's details
            wrapper = {
                "id": plugin.get_action_id(),
                "icon": plugin.get_action_icon(),
                "name": plugin.get_action_name(),
                "args": add_logging_arg(plugin.get_action_args()),
                "category": plugin.get_category(),
                "standalone": plugin.is_standalone()
            }

            results.append(wrapper)  # Add the wrapper to the results list

    # Generate and return a success response with the list of plugins
    return generate_success_response('', {"plugins": results})