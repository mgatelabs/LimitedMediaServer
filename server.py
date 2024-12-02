import argparse

from flask import Flask

from app_properties import AppPropertyDefinition
from app_queries import get_secret_key, get_server_port, get_server_host, get_auth_timeout, check_and_insert_property, \
    get_media_primary_folder, get_media_alt_folder, get_media_temp_folder, clean_unknown_properties, get_volume_folder, \
    get_plugin_value
from app_routes import admin_blueprint
from app_utils import value_is_folder, value_is_integer, value_is_between_int_x_y, value_is_ipaddress, get_random_hash
from auth_routes import auth_blueprint
from constants import PROPERTY_SERVER_PORT_KEY, PROPERTY_SERVER_SECRET_KEY, PROPERTY_SERVER_HOST_KEY, \
    PROPERTY_SERVER_AUTH_TIMEOUT_KEY, PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER, \
    PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER, PROPERTY_SERVER_MEDIA_TEMP_FOLDER, PROPERTY_SERVER_MEDIA_READY, \
    CONFIG_USE_HTTPS, PROPERTY_DEFINITIONS, PROPERTY_SERVER_VOLUME_READY, \
    PROPERTY_SERVER_VOLUME_FOLDER, APP_KEY_SLC, APP_KEY_AUTHENTICATE, APP_KEY_PLUGINS, APP_KEY_PROCESSORS
from db import init_db, db
from health_routes import health_blueprint
from media_routes import media_blueprint
from network_utils import is_private_ip, get_local_ip
from plugin_routes import plugin_blueprint
from plugin_utils import get_plugins
from process_routes import process_blueprint
from serve_routes import serve_blueprint
from short_lived_cache import ShortLivedCache
from text_utils import is_not_blank
from volume_routes import volume_blueprint
from volume_utils import get_processors

# Initialize Flask app
app = Flask(__name__)


@app.after_request
def add_csp_headers(response):
    # Customize CSP policies to match your app's needs
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "media-src 'self'; "
        "connect-src 'self'; "
        "font-src 'self' https://fonts.gstatic.com; "
        "frame-src 'self'; "
    )
    if not response.headers.get('Content-Security-Policy'):
        response.headers['Content-Security-Policy'] = csp
    return response


app.config.from_object('config.Config')

# Initialize the database
init_db(app)

if __name__ == '__main__':
    # Load plugins and processors
    plugins = get_plugins('plugins')
    processors = get_processors('processors')

    # Set up argument parser
    parser = argparse.ArgumentParser(description="Media Server")

    for plugin in plugins['all']:
        plugin.add_args(parser)

    property_definitions = [
        # Server
        AppPropertyDefinition(PROPERTY_SERVER_PORT_KEY, '80',
                              'Default port number. Restart server if changed.',
                              [value_is_integer, value_is_between_int_x_y(1, 65535)]),
        AppPropertyDefinition(PROPERTY_SERVER_SECRET_KEY, get_random_hash,
                              'Per server secret key, generated on 1st server startup. Used to protect JWT tokens. Restart server if changed.'),

        # Auth
        AppPropertyDefinition(PROPERTY_SERVER_HOST_KEY, '0.0.0.0',
                              'Default host binding address. Restart server if changed.',
                              [value_is_ipaddress]),
        AppPropertyDefinition(PROPERTY_SERVER_AUTH_TIMEOUT_KEY, '600',
                              '600 minute timeout, before login expires. Restart server if changed.',
                              [value_is_integer, value_is_between_int_x_y(5, 43200)]),
        # Media
        AppPropertyDefinition(PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER, '',
                              'Path to a folder where the primary files and previews will be kept.  This should be on a high performance drive.  Restart server if changed.',
                              [value_is_folder]),

        AppPropertyDefinition(PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER, '',
                              'Path to a folder where the archived files will be kept.  This does not need to be on a high performance drive.  Restart server if changed.',
                              [value_is_folder]),

        AppPropertyDefinition(PROPERTY_SERVER_MEDIA_TEMP_FOLDER, '',
                              'Path to a folder where temporary files will be kept.  This should be on a high performance drive.  Restart server if changed.',
                              [value_is_folder]),
        # Volume
        AppPropertyDefinition(PROPERTY_SERVER_VOLUME_FOLDER, '',
                              'Path to a folder where volume files will be kept.  This should be on a high performance drive.  Restart server if changed.',
                              [value_is_folder]),
    ]

    # Ensure any plugin that needs a property, gets it
    for plugin in plugins['all']:
        plugin_properties = plugin.get_properties()
        for plugin_property in plugin_properties:
            # Plugin properties must start with PLUGIN.
            if plugin_property.id.startswith('PLUGIN.'):
                property_definitions.append(plugin_property)

    app.config[PROPERTY_DEFINITIONS] = property_definitions

    with app.app_context():
        for property_definition in property_definitions:
            check_and_insert_property(property_definition, db.session)

    # Common arguments

    args = parser.parse_args()

    app.config[APP_KEY_SLC] = ShortLivedCache()

    # Configure processors
    app.config[APP_KEY_PROCESSORS] = processors

    # Common configurations
    app.config[APP_KEY_AUTHENTICATE] = False
    app.config[APP_KEY_PLUGINS] = plugins

    use_ssl = False

    with app.app_context():

        # Remove any unused properties
        clean_unknown_properties(property_definitions, db.session)

        # Query the AppProperties table for values
        app.config[PROPERTY_SERVER_SECRET_KEY] = get_secret_key()
        app.config[PROPERTY_SERVER_PORT_KEY] = get_server_port()
        app.config[PROPERTY_SERVER_HOST_KEY] = get_server_host()
        app.config[PROPERTY_SERVER_AUTH_TIMEOUT_KEY] = get_auth_timeout()

        # Show Properties
        app.config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER] = get_media_primary_folder()
        app.config[PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER] = get_media_alt_folder()
        app.config[PROPERTY_SERVER_MEDIA_TEMP_FOLDER] = get_media_temp_folder()

        app.config[PROPERTY_SERVER_VOLUME_FOLDER] = get_volume_folder()

        app.config[CONFIG_USE_HTTPS] = use_ssl

        for property_item in property_definitions:
            if property_item.id.startswith('PLUGIN.'):
                app.config[property_item.id] = get_plugin_value(property_item.id)

    # See if media is ready
    app.config[PROPERTY_SERVER_MEDIA_READY] = is_not_blank(
        app.config[PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER]) and is_not_blank(
        app.config[PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER]) and is_not_blank(
        app.config[PROPERTY_SERVER_MEDIA_TEMP_FOLDER])

    # See if media is ready
    app.config[PROPERTY_SERVER_VOLUME_READY] = is_not_blank(app.config[PROPERTY_SERVER_VOLUME_FOLDER])

    for plugin in plugins['all']:
        plugin.use_args(args)
        plugin.absorb_config(app.config)

    # Register blueprints
    app.register_blueprint(auth_blueprint, url_prefix='/api/auth')
    app.register_blueprint(admin_blueprint, url_prefix='/api/admin')
    app.register_blueprint(health_blueprint, url_prefix='/api/health')
    app.register_blueprint(process_blueprint, url_prefix='/api/process')
    app.register_blueprint(plugin_blueprint, url_prefix='/api/plugin')
    app.register_blueprint(volume_blueprint, url_prefix='/api/volume')
    app.register_blueprint(media_blueprint, url_prefix='/api/media')
    # Make sure we can serve files
    app.register_blueprint(serve_blueprint)

    local_ip = app.config[PROPERTY_SERVER_HOST_KEY]

    if local_ip == '0.0.0.0':
        actual_ip = get_local_ip()
        if actual_ip is not None and not is_private_ip(actual_ip):
            print('Error: IP Address is not a local address, do not expose this server to the Internet!!!!')
    else:
        if not is_private_ip(local_ip):
            print('Error: IP Address is not a local address, do not expose this server to the Internet!!!!')

    app.run(host=app.config[PROPERTY_SERVER_HOST_KEY], port=app.config[PROPERTY_SERVER_PORT_KEY], debug=False)
