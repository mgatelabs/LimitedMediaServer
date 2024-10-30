from flask import Blueprint

from common_utils import generate_success_response

# Create a Blueprint for the health check routes
health_blueprint = Blueprint('health', __name__)

@health_blueprint.route('/alive', methods=['POST'])
def is_alive():
    """
    Health check endpoint to verify if the server is running.

    Returns:
        JSON response indicating the server is alive.
    """
    return generate_success_response('', {"alive": True})