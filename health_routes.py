import logging

import psutil
from flask import Blueprint

from auth_utils import feature_required_silent
from common_utils import generate_success_response
from feature_flags import VIEW_PROCESSES, MANAGE_APP

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


@health_blueprint.route('/drives', methods=['POST'])
@feature_required_silent(health_blueprint, MANAGE_APP)
def drive_info():
    """
    See the status of the hard drives.

    Returns:
        JSON response indicating the server's status.
    """

    partitions = psutil.disk_partitions()
    disk_usage_info = []
    for partition in partitions:
        try:
            partition_info = {'device': partition.device,
                              'mountpoint': partition.mountpoint,
                              'fstype': partition.fstype,
                              'total': psutil.disk_usage(partition.mountpoint).total,
                              'used': psutil.disk_usage(partition.mountpoint).used,
                              'free': psutil.disk_usage(partition.mountpoint).free,
                              'percent': psutil.disk_usage(partition.mountpoint).percent}
            if partition_info['mountpoint'].startswith('/boot'):
                continue

            disk_usage_info.append(partition_info)
        except Exception as ex:
            logging.exception(ex)

    return generate_success_response('', {"info": disk_usage_info})
