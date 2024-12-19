import logging
from datetime import datetime, timedelta, timezone

import jwt
from flask import Blueprint, request, current_app, make_response
from sqlalchemy.exc import NoResultFound
from werkzeug.security import check_password_hash, generate_password_hash

from auth_utils import shall_authenticate_user, feature_required, get_uid, generate_secure_token
from common_utils import generate_success_response, generate_failure_response
from constants import PROPERTY_SERVER_SECRET_KEY, PROPERTY_SERVER_AUTH_TIMEOUT_KEY, CONFIG_USE_HTTPS
from db import User, UserHardSession, db
from feature_flags import HARD_SESSIONS
from messages import msg_auth_login_failure, msg_missing_parameter, msg_mismatched_parameters, msg_server_error, \
    msg_operation_complete
from text_utils import clean_string, is_not_blank, is_blank

# Define a Blueprint for authentication routes
auth_blueprint = Blueprint('auth', __name__)


def generate_auth_result(user: User):
    # Generate JWT token
    timeout = current_app.config[PROPERTY_SERVER_AUTH_TIMEOUT_KEY]

    features = user.features

    limits = {}
    for limit in user.limits:
        limits[limit.limit_type] = limit.limit_value

    if 'volume' not in limits:
        limits['volume'] = 0

    if 'media' not in limits:
        limits['media'] = 0

    expiration_time = datetime.now(timezone.utc) + timedelta(minutes=timeout)

    token = jwt.encode({'uid': user.id, 'username': user.username, 'limits': limits, 'features': features,
                        'exp': expiration_time},
                       current_app.config[PROPERTY_SERVER_SECRET_KEY], algorithm='HS256')

    response = make_response(generate_success_response('', {'token': token}))

    # Set the JWT token as a cookie
    response.set_cookie(
        'access_token',  # Name of the cookie
        token,  # JWT token value
        httponly=True,  # Prevents JavaScript access
        secure=current_app.config[CONFIG_USE_HTTPS],  # Ensures the cookie is only sent over HTTPS
        samesite='strict',  # Optional: restricts sharing of cookies across sites
        expires=expiration_time
    )

    return response


def attempt_standard_auth(username: str, password: str):
    username = username.lower().strip()
    password = password.strip()

    try:
        # Query the Users table for a matching user
        user = User.query.filter_by(username=username).one()

        # Check if the password matches
        if check_password_hash(user.password, password):
            return generate_auth_result(user)
        else:
            return generate_failure_response('Invalid credentials', 401, {}, [msg_auth_login_failure()])
    except NoResultFound:
        return generate_failure_response('Invalid credentials', 401, {}, [msg_auth_login_failure()])


def attempt_token_auth(token: str, pin: str):
    """
    Login with a token and pin.  An invalid login will cancel the record.
    :param token:
    :param pin:
    :return:
    """
    try:
        # Query the Users table for a matching user
        hard_session = UserHardSession.query.filter(UserHardSession.token == token).one()

        if hard_session.expired is not None:
            return generate_failure_response('Invalid credentials', 401, {}, [msg_auth_login_failure()])

        # Check if the password matches
        if check_password_hash(hard_session.pin, pin):
            # Get the associated user
            user = hard_session.user

            # Remember the last time "this" device was logged in
            hard_session.last = datetime.now(timezone.utc)
            db.session.commit()

            return generate_auth_result(user)
        else:
            # They failed the pin check, disable the token
            hard_session.expired = datetime.now(timezone.utc)
            db.session.commit()

            return generate_failure_response('Invalid credentials', 401, {}, [msg_auth_login_failure()])
    except NoResultFound:
        return generate_failure_response('Invalid credentials', 401, {}, [msg_auth_login_failure()])


# Route to handle login requests
@auth_blueprint.route('/login', methods=['POST'])
def login_request():
    """
    Route to handle login requests.
    """
    username = clean_string(request.form.get('username'))
    password = clean_string(request.form.get('password'))
    token = clean_string(request.form.get('token'))
    pin = clean_string(request.form.get('pin'))

    if is_not_blank(username) and is_not_blank(password):
        return attempt_standard_auth(username, password)
    elif is_not_blank(token) and is_not_blank(pin):
        return attempt_token_auth(token, pin)

    return generate_failure_response('Invalid credentials', 401, {}, [msg_auth_login_failure()])


# Route to handle login requests
@auth_blueprint.route('/hard', methods=['POST'])
@feature_required(auth_blueprint, HARD_SESSIONS)
def request_hard_session(user_details):
    pin = clean_string(request.form.get('pin'))
    pin2 = clean_string(request.form.get('pin2'))

    if is_blank(pin):
        return generate_failure_response('pin is required', 400, {},[msg_missing_parameter("pin")])

    if is_blank(pin2):
        return generate_failure_response('pin2 is required', 400, {},[msg_missing_parameter("pin2")])

    if pin != pin2:
        return generate_failure_response('pin != pin2', 400, {},[msg_mismatched_parameters("pin", "pin2")])

    # Get the user id
    user_id = get_uid(user_details)

    # Make a new random token
    token = generate_secure_token(200)

    new_session = UserHardSession(user_id=user_id, token=token, pin=generate_password_hash(pin), expired=None,
                                  last=None)

    try:
        db.session.add(new_session)
        db.session.commit()
        return generate_success_response('Token Generated', {'token': token}, [msg_operation_complete()])

    except Exception as ex:
        logging.exception(ex)
        return generate_failure_response('Exception', 401, {},[msg_server_error()])


# Route to handle login requests
@auth_blueprint.route('/renew', methods=['POST'])
@shall_authenticate_user(auth_blueprint)
def renew_request(user_details):
    """
    Route to renew login credentials.
    """

    # Generate JWT token
    timeout = current_app.config[PROPERTY_SERVER_AUTH_TIMEOUT_KEY]

    features = user_details['features']
    limits = user_details['limits']

    expiration_time = datetime.now(timezone.utc) + timedelta(minutes=timeout)

    token = jwt.encode(
        {'uid': user_details['uid'], 'username': user_details['username'], 'limits': limits, 'features': features,
         'exp': expiration_time},
        current_app.config[PROPERTY_SERVER_SECRET_KEY], algorithm='HS256')

    response = make_response(generate_success_response('', {'token': token}, messages=[msg_operation_complete()]))

    # Set the JWT token as a cookie
    response.set_cookie(
        'access_token',  # Name of the cookie
        token,  # JWT token value
        httponly=True,  # Prevents JavaScript access
        secure=current_app.config[CONFIG_USE_HTTPS],  # Ensures the cookie is only sent over HTTPS
        samesite='strict',  # Optional: restricts sharing of cookies across sites
        expires=expiration_time
    )

    return response
