from datetime import datetime, timedelta, timezone

import jwt
from flask import Blueprint, request, current_app, make_response
from sqlalchemy.exc import NoResultFound
import logging
from werkzeug.security import check_password_hash

from auth_utils import shall_authenticate_user
from common_utils import generate_success_response
from constants import PROPERTY_SERVER_SECRET_KEY, PROPERTY_SERVER_AUTH_TIMEOUT_KEY, CONFIG_USE_HTTPS
from db import User

# Define a Blueprint for authentication routes
auth_blueprint = Blueprint('auth', __name__)


# Route to handle login requests
@auth_blueprint.route('/login', methods=['POST'])
def login_request():
    """
    Route to handle login requests.
    """
    username = request.form.get('username')
    password = request.form.get('password')

    if username is None or password is None:
        return {'status': 'FAIL', 'message': 'Invalid credentials'}, 401

    username = username.lower().strip()
    password = password.strip()

    try:
        # Query the Users table for a matching user
        user = User.query.filter_by(username=username).one()

        # Check if the password matches
        if check_password_hash(user.password, password):
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

            token = jwt.encode({'uid': user.id, 'username': username, 'limits': limits, 'features': features,
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
        else:
            return {'status': 'FAIL', 'message': 'Invalid credentials'}, 401
    except NoResultFound:
        return {'status': 'FAIL', 'message': 'Invalid credentials'}, 401


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
