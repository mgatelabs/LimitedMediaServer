import psutil
from flask import Blueprint

from auth_utils import feature_required_silent
from common_utils import generate_success_response
from feature_flags import VIEW_PROCESSES

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


@health_blueprint.route('/status', methods=['POST'])
@feature_required_silent(health_blueprint, VIEW_PROCESSES)
def status_info():
    """
    Health check to get some server stats.

    Returns:
        JSON response indicating the server's status.
    """
    cpu_usage = psutil.cpu_percent(interval=1)

    memory = psutil.virtual_memory()

    net_io = psutil.net_io_counters()

    return generate_success_response('', {
        "info": {"cpu": cpu_usage, "memory": {"available": memory.available, "total": memory.total, "free": memory.free,
                                              "used": memory.used, "percent": memory.percent},
                 "netout": net_io.bytes_sent, "netin": net_io.bytes_recv}})
