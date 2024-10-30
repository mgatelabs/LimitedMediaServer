# serve_routes.py

from flask import Blueprint, send_from_directory

serve_blueprint = Blueprint('serve', __name__)

"""
This is the fallback way to server web content via the flask server
"""

@serve_blueprint.route('/')
def serve_index():
    """
    Serve the default webpage
    """
    return send_from_directory('static/browser', 'index.html')


# Serve static files from the 'static' directory
@serve_blueprint.route('/<path:filename>')
def serve_static(filename):
    """
    Serve the specified file from /static/browser or the default html page
    """
    if filename.startswith("a-"):
        """
        If it starts with a-, its actually an angular route, send it the default page.
        """
        return send_from_directory('static/browser', 'index.html')

    # Send a file
    return send_from_directory('static/browser', filename)
