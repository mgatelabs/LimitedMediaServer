from typing import Optional

from flask import jsonify


def generate_failure_response(message, status_code=400, extra_data=None, messages: Optional[list[tuple[str, dict[str, str]]]]= None)-> tuple:
    """
    Generate a common failure response.

    :param message: Failure message to be included in the response.
    :param status_code: HTTP status code for the response.
    :param extra_data: Optional dictionary to be merged into the response.
    :param messages: Optional translated messages to display
    :return: JSON response with failure status and message.
    """
    response = {'status': 'FAIL', 'message': messages, 'messages': []}

    if extra_data:
        response.update(extra_data)

    if messages:
        response['messages'] = messages

    return jsonify(response), status_code


def generate_success_response(message, extra_data=None, status_code=200, messages: Optional[list[tuple[str, dict[str, str]]]]= None)-> tuple:
    """
    Generate a common failure response.

    :param message: Failure message to be included in the response.
    :param extra_data: Optional dictionary to be merged into the response.
    :param status_code: HTTP status code for the response.
    :param messages: Optional translated messages to display
    :return: JSON response with failure status and message.
    """
    response = {'status': 'OK', 'message': message}

    if extra_data:
        response.update(extra_data)

    if messages:
        response['messages'] = messages

    return jsonify(response), status_code