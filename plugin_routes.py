from flask import Blueprint, request, current_app, jsonify

from auth_utils import shall_authenticate_user
from common_utils import generate_success_response, generate_failure_response
from plugin_system import ai_args_for_plugin, ai_usage_notes

# Create a Blueprint for plugin routes
plugin_blueprint = Blueprint('plugin', __name__)


def _ai_visible_plugin(plugin, user_details: dict) -> bool:
    return (plugin.is_ready() and plugin.is_available_to_menu()
            and (plugin.get_feature_flags() & user_details['features']) == plugin.get_feature_flags())


# Default logging values for plugins


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
        if plugin.is_ready() and plugin.is_available_to_menu() and (plugin.get_feature_flags() & user_details['features']) == plugin.get_feature_flags():

            j = plugin.to_json()

            for arg in j['args']:
                if arg['type'] == 'select':
                    temp_key = 'PLUGIN.DEFAULT.' + j['id'] + '_' + arg['id']

                    if temp_key in current_app.config and not current_app.config[temp_key] == '':
                        arg['default'] = current_app.config[temp_key]

            results.append(j)

    # Generate and return a success response with the list of plugins
    return generate_success_response('', {"plugins": results})


# AI-facing plugin discovery
@plugin_blueprint.route('/list/ai', methods=['POST'])
@shall_authenticate_user(plugin_blueprint)
def list_ai_book_actions(user_details: dict) -> tuple:
    """
    List all available actions in a format optimised for AI consumption.

    Args:
        user_details (dict): The details of the authenticated user.

    Returns:
        tuple: A JSON response containing the list of available actions.
    """
    config = current_app.config
    plugins = config['PLUGINS']['all']

    results = []
    for plugin in plugins:
        if _ai_visible_plugin(plugin, user_details):
            results.append({
                'id': plugin.get_action_id(),
                'name': plugin.get_action_name(),
                'category': plugin.get_category(),
                'standalone': plugin.is_standalone(),
                'description': plugin.get_ai_quick_description(),
                'args': ai_args_for_plugin(plugin, config),
            })

    return generate_success_response('', {"plugins": results})


# AI-facing single plugin description
@plugin_blueprint.route('/describe', methods=['POST'])
@shall_authenticate_user(plugin_blueprint)
def describe_ai_book_action(user_details: dict) -> tuple:
    """
    Return the full AI description for a single action plugin by id.

    Args:
        user_details (dict): The details of the authenticated user.

    Returns:
        tuple: A JSON response containing the plugin description.
    """
    config = current_app.config
    plugin_id = request.form.get('plugin_id', '')
    plugins = config['PLUGINS']['all']

    target = None
    for plugin in plugins:
        if plugin.get_action_id() == plugin_id:
            target = plugin
            break

    if target is None:
        return generate_failure_response('Plugin not found: ' + plugin_id)

    if not _ai_visible_plugin(target, user_details):
        return generate_failure_response('Plugin not available: ' + plugin_id)

    return generate_success_response('', {"plugin": {
        'id': target.get_action_id(),
        'name': target.get_action_name(),
        'category': target.get_category(),
        'standalone': target.is_standalone(),
        'description': target.get_ai_quick_description(),
        'usage_notes': ai_usage_notes(target, config),
        'args': ai_args_for_plugin(target, config),
    }})
