import logging
import secrets
import string
from functools import wraps
from typing import Optional

import jwt
from flask import current_app, request

from common_utils import generate_failure_response
from constants import PROPERTY_SERVER_SECRET_KEY
from messages import msg_auth_issue_reason, msg_auth_feature_required


class AuthResult:
    def __init__(self, valid, message=None, data=None, msg:Optional[tuple[str, dict[str, str]]] = None):
        self.valid = valid  # Boolean indicating if the authentication is valid
        self.message = message  # Message describing the result
        self.msg = msg
        self.data = data  # Additional data related to the authentication

    def getMsgs(self):
        if self.msg:
            return [self.msg]
        return None

    def __repr__(self):
        return f"AuthResult(valid={self.valid}, message={self.message}, data={self.data})"


def _get_auth_status(required_features: int = 0, use_cookie: bool = False) -> AuthResult:
    """
    Check the authentication status of the user based on the JWT token.

    :param required_features: Features required to access the resource.
    :return: AuthResult object indicating the authentication status.
    """
    skey = current_app.config[PROPERTY_SERVER_SECRET_KEY]  # Get the secret key from the app config

    if skey is None:
        return AuthResult(False, 'System isn\'t configured correctly', {})

    if use_cookie:
        token = request.cookies.get('access_token')
        if token is None and 'Authorization' in request.headers:
            token = request.headers['Authorization'].split()[1]
    else:
        # Get the JWT token from the Authorization header
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split()[1]
        else:
            token = None

    if not token:
        return AuthResult(False, 'Token is missing', {}, msg_auth_issue_reason('TOKEN Missing'))

    try:
        # Decode the JWT token
        data = jwt.decode(token, skey, algorithms=['HS256'])

        if 'username' not in data:
            return AuthResult(False, 'Token is invalid, missing username', {}, msg_auth_issue_reason('Corrupt TOKEN'))

        if 'uid' not in data:
            return AuthResult(False, 'Token is invalid, missing uid', {}, msg_auth_issue_reason('Corrupt TOKEN'))

        # Set default values if not present in the token
        if 'features' not in data:
            data['features'] = 0

        if 'limits' not in data:
            data['limits'] = {}

        if 'volume' not in data['limits']:
            data['limits']['volume'] = 0

        if 'media' not in data['limits']:
            data['limits']['media'] = 0

        # Check if the user has the required features
        if required_features != 0 and (data['features'] & required_features) != required_features:
            return AuthResult(False, 'User is not allowed to access this resource', {}, msg_auth_feature_required())

        return AuthResult(True, 'OK', data)

    except jwt.ExpiredSignatureError:
        return AuthResult(False, 'Token has expired', {}, msg_auth_issue_reason('Expired TOKEN'))
    except jwt.InvalidTokenError:
        return AuthResult(False, 'Token is invalid', {}, msg_auth_issue_reason('Invalid TOKEN'))
    except Exception as e:
        logging.exception(e)
        return AuthResult(False, 'Token is invalid', {}, msg_auth_issue_reason('Invalid TOKEN'))


def may_authenticate_user(blueprint):
    """
    Decorator to optionally authenticate a user. If authentication fails, the decorated function is called with None.

    :param blueprint: Flask blueprint.
    :return: Decorated function.
    """

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            result = _get_auth_status()

            if not result.valid:
                return f(None, *args, **kwargs)

            return f(result.data, *args, **kwargs)

        return decorated

    return decorator


def shall_authenticate_user(blueprint):
    """
    Decorator to enforce user authentication. If authentication fails, a failure response is returned.

    :param blueprint: Flask blueprint.
    :return: Decorated function.
    """

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            result = _get_auth_status()

            if not result.valid:
                return generate_failure_response(result.message, 401, result.getMsgs())

            return f(result.data, *args, **kwargs)

        return decorated

    return decorator


def shall_authenticate_user_with_cookie(blueprint):
    """
    Decorator to enforce user authentication. If authentication fails, a failure response is returned.

    :param blueprint: Flask blueprint.
    :return: Decorated function.
    """

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            result = _get_auth_status(0, True)

            if not result.valid:
                return generate_failure_response(result.message, 401, result.getMsgs())

            return f(result.data, *args, **kwargs)

        return decorated

    return decorator


def feature_required(blueprint, required_features: int):
    """
    Decorator to enforce user authentication and check for required features. If authentication or feature check fails, a failure response is returned.

    :param blueprint: Flask blueprint.
    :param required_features: Features required to access the resource.
    :return: Decorated function.
    """

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            result = _get_auth_status(required_features)

            if not result.valid:
                return generate_failure_response(result.message, 401, result.getMsgs())

            return f(result.data, *args, **kwargs)

        return decorated

    return decorator


def feature_required_with_cookie(blueprint, required_features: int):
    """
    Decorator to enforce user authentication and check for required features. If authentication or feature check fails, a failure response is returned.

    :param blueprint: Flask blueprint.
    :param required_features: Features required to access the resource.
    :return: Decorated function.
    """

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            result = _get_auth_status(required_features, True)

            if not result.valid:
                return generate_failure_response(result.message, 401, result.getMsgs())

            return f(result.data, *args, **kwargs)

        return decorated

    return decorator


def feature_required_silent(blueprint, required_features: int):
    """
    Decorator to enforce user authentication and check for required features. If authentication or feature check fails, a failure response is returned.

    :param blueprint: Flask blueprint.
    :param required_features: Features required to access the resource.
    :return: Decorated function.
    """

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            result = _get_auth_status(required_features)

            if not result.valid:
                return generate_failure_response(result.message, 401, result.getMsgs())

            return f(*args, **kwargs)

        return decorated

    return decorator


def get_user_features(user_details) -> int:
    """
    Extract the features value from user_details.

    :param user_details: Dictionary containing user details.
    :return: Integer value of features or 0 if not present.
    """
    if user_details is None:
        return 0
    return user_details.get('features', 0)


def get_user_group_id(user_details) -> Optional[int]:
    """
    Extract the group_id value from user_details.

    :param user_details: Dictionary containing user details.
    :return: Integer value of features or 0 if not present.
    """
    if user_details is None:
        return None
    return user_details.get('gid', None)


def get_user_media_limit(user_details) -> Optional[int]:
    """
    Extract the media limit value from user_details.

    :param user_details: Dictionary containing user details.
    :return: Integer value of media limit or 0 if not present.
    """
    if user_details is None:
        return None

    if 'limits' not in user_details:
        return 0

    return user_details.get('limits').get('media', 0)


def get_user_volume_limit(user_details) -> Optional[int]:
    """
    Extract the volume limit value from user_details.

    :param user_details: Dictionary containing user details.
    :return: Integer value of volume limit or 0 if not present.
    """
    if user_details is None:
        return None

    if 'limits' not in user_details:
        return 0

    return user_details.get('limits').get('volume', 0)


def get_uid(user_details) -> Optional[int]:
    """
    Extract the USER UID user_details.
    :param user_details: Dictionary containing user details.
    :return: Integer value of the user or None.
    """
    if user_details is None:
        return None

    if 'uid' not in user_details:
        return None

    return user_details.get('uid')


def get_username(user_details) -> Optional[str]:
    """
    Extract the USERNAME from user_details.
    :param user_details: Dictionary containing user details.
    :return: Integer value of the user or None.
    """
    if user_details is None:
        return None

    if 'username' not in user_details:
        return None

    return user_details.get('username')

def generate_secure_token(length=200):
    characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
    return ''.join(secrets.choice(characters) for _ in range(length))
