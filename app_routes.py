import logging
from typing import Optional

from flask import Blueprint, request, current_app
from sqlalchemy.exc import IntegrityError
from sqlalchemy.testing.plugin.plugin_base import logging
from werkzeug.security import generate_password_hash, check_password_hash

from app_queries import update_user_features, update_user_limit, update_user_group, find_all_hard_sessions, \
    find_my_hard_sessions
from auth_utils import feature_required, feature_required_silent, shall_authenticate_user, get_uid
from common_utils import generate_failure_response, generate_success_response
from constants import PROPERTY_DEFINITIONS
from db import db, User, AppProperties, UserLimit, UserGroup, UserHardSession
from feature_flags import MANAGE_APP, SUPER_ADMIN, HARD_SESSIONS
from number_utils import is_integer
from property_queries import get_all_properties, get_property
from text_utils import is_valid_username, clean_string, is_blank, is_not_blank, format_datatime
from user_queries import get_all_users, get_user_by_id, get_all_groups, get_group_by_id, count_folders_for_group

# Blueprint for admin routes
admin_blueprint = Blueprint('admin', __name__)


@admin_blueprint.route('/list/users', methods=['POST'])
@feature_required_silent(admin_blueprint, MANAGE_APP)
def list_users():
    """
    List all users in the system.
    """
    users = get_all_users()

    users_list = []

    for user in users:
        row = {'id': user.id, 'username': user.username, 'features': user.features, 'volume_limit': 0, 'media_limit': 0,
               'group_id': user.user_group_id}
        for limit in user.limits:
            row[limit.limit_type + '_limit'] = limit.limit_value
        users_list.append(row)

    return generate_success_response('', {"users": users_list})


@admin_blueprint.route('/list/groups', methods=['POST'])
@feature_required_silent(admin_blueprint, MANAGE_APP)
def list_groups():
    """
    List all groups in the system.
    """
    groups = get_all_groups()

    group_list = []

    for group in groups:
        row = {'id': group.id, 'name': group.name, 'description': group.description}
        group_list.append(row)

    return generate_success_response('', {"groups": group_list})


@admin_blueprint.route('/get/user', methods=['POST'])
@feature_required_silent(admin_blueprint, MANAGE_APP)
def get_user_details():
    """
    Get details of a specific user by uid.
    """
    user_id = clean_string(request.form.get('user_id'))
    if not is_integer(user_id):
        return generate_failure_response('user_id parameter is not an integer', 400)
    user_id = int(user_id)

    user = get_user_by_id(user_id)

    limits = {'volume_limit': 0, 'media_limit': 0}

    for limit in user.limits:
        new_key = limit.limit_type + '_limit'
        limits[new_key] = limit.limit_value

    if not user:
        return generate_failure_response('User not found', 404)

    user_details = {'id': user.id, 'username': user.username, 'features': user.features, 'group_id': user.user_group_id,
                    'volume_limit': limits['volume_limit'],
                    'media_limit': limits['media_limit']}

    return generate_success_response('', {"user": user_details})


@admin_blueprint.route('/get/group', methods=['POST'])
@feature_required_silent(admin_blueprint, MANAGE_APP)
def get_group_details():
    """
    Get details of a specific group by uid.
    """
    group_id = clean_string(request.form.get('group_id'))
    if not is_integer(group_id):
        return generate_failure_response('group_id parameter is not an integer', 400)
    group_id = int(group_id)

    group = get_group_by_id(group_id)

    if not group:
        return generate_failure_response('Group not found', 404)

    group_details = {'id': group.id, 'name': group.name, 'description': group.description}

    return generate_success_response('', {"group": group_details})


@admin_blueprint.route('/new/user', methods=['POST'])
@feature_required_silent(admin_blueprint, MANAGE_APP)
def create_user():
    """
    Create a new user with the provided details.
    """
    username = clean_string(request.form.get('username'))
    password = clean_string(request.form.get('password'))
    features = clean_string(request.form.get('features'))
    volume_limit = clean_string(request.form.get('volume_limit'))
    media_limit = clean_string(request.form.get('media_limit'))
    group_id = clean_string(request.form.get('group_id'))

    # Validate input parameters
    if is_blank(username):
        return generate_failure_response('username parameter required', 400)
    if is_blank(password):
        return generate_failure_response('password parameter required', 400)

    username = username.strip().lower()
    password = password.strip()

    if not is_valid_username(username):
        return generate_failure_response('Username is not in the proper format (A-Z0-9@.)', 400)

    if is_not_blank(group_id) and is_integer(group_id):
        group_id = int(group_id)
        group = get_group_by_id(group_id)
        if group is None:
            return generate_failure_response('Unknown group', 400)
    else:
        group_id = None

    validator_result = limit_validator(features, volume_limit, media_limit)

    if validator_result is not None:
        return validator_result

    features = int(features)
    volume_limit = int(volume_limit)
    media_limit = int(media_limit)

    hashed_password = generate_password_hash(password)
    new_user = User(username=username, password=hashed_password, features=features, user_group_id=group_id)

    try:
        db.session.add(new_user)
        db.session.commit()

        volume_limit_row = UserLimit(user_id=new_user.id, limit_type='volume', limit_value=volume_limit)
        db.session.add(volume_limit_row)

        media_limit_row = UserLimit(user_id=new_user.id, limit_type='media', limit_value=media_limit)
        db.session.add(media_limit_row)

        db.session.commit()
    except IntegrityError as e:
        logging.exception(e)
        db.session.rollback()
        return generate_failure_response(f'User {username} already exists or other exception, please see log', 400)

    return generate_success_response(f'User {username} created')


@admin_blueprint.route('/new/group', methods=['POST'])
@feature_required_silent(admin_blueprint, MANAGE_APP)
def create_group():
    """
    Create a new group with the provided details.
    """
    name = clean_string(request.form.get('name'))
    description = clean_string(request.form.get('description'))

    # Validate input parameters
    if is_blank(name):
        return generate_failure_response('name parameter required', 400)
    if is_blank(description):
        return generate_failure_response('description parameter required', 400)

    new_group = UserGroup(name=name, description=description)

    try:
        db.session.add(new_group)
        db.session.commit()

    except IntegrityError as e:
        logging.exception(e)
        db.session.rollback()
        return generate_failure_response(f'Group {name} already exists or other exception, please see log', 400)

    return generate_success_response(f'Group {name} created')


@admin_blueprint.route('/remove/user', methods=['POST'])
@feature_required(admin_blueprint, MANAGE_APP)
def delete_user(user_details):
    """
    Delete a user by user_id. The current user cannot delete themselves.
    """
    user_id = clean_string(request.form.get('user_id'))
    if not is_integer(user_id):
        return generate_failure_response('user_id parameter is not an integer', 400)
    user_id = int(user_id)

    current_user_id = user_details['uid']

    if int(current_user_id) == user_id:
        return generate_failure_response('You cannot delete you own account', 400)

    user = User.query.get(user_id)
    if not user:
        return generate_failure_response('User not found', 404)

    db.session.delete(user)
    db.session.commit()

    return generate_success_response('User deleted')


@admin_blueprint.route('/remove/group', methods=['POST'])
@feature_required_silent(admin_blueprint, MANAGE_APP)
def delete_group():
    """
    Delete a group by group_id. The current user cannot delete themselves.
    """
    group_id = clean_string(request.form.get('group_id'))
    if not is_integer(group_id):
        return generate_failure_response('group_id parameter is not an integer', 400)
    group_id = int(group_id)

    group = UserGroup.query.get(group_id)
    if not group:
        return generate_failure_response('Group not found', 404)

    if count_folders_for_group(group.id) > 0:
        return generate_failure_response('Group is still tied to a folder, stopping!', 404)

    db.session.delete(group)
    db.session.commit()

    return generate_success_response('Group deleted')


@admin_blueprint.route('/update/user/limits', methods=['POST'])
@feature_required_silent(admin_blueprint, MANAGE_APP)
def update_user_limits():
    """
    Update the limits for a user.
    """
    user_id = clean_string(request.form.get('user_id'))
    if not is_integer(user_id):
        return generate_failure_response('user_id parameter is not an integer', 400)
    user_id = int(user_id)

    features = clean_string(request.form.get('features'))
    volume_limit = clean_string(request.form.get('volume_limit'))
    media_limit = clean_string(request.form.get('media_limit'))
    group_id = clean_string(request.form.get('group_id'))

    if is_not_blank(group_id) and is_integer(group_id):
        group_id = int(group_id)
        group = get_group_by_id(group_id)
        if group is None:
            return generate_failure_response('Unknown group', 400)
    else:
        group_id = None

    validator_result = limit_validator(features, volume_limit, media_limit)

    if validator_result is not None:
        return validator_result

    user = User.query.get(user_id)
    if not user:
        return generate_failure_response('User not found', 404)

    update_needed = False

    update_needed |= update_user_features(user, int(features))
    update_needed |= update_user_group(user, group_id)
    limits = user.limits
    update_needed |= update_user_limit(user, limits, 'volume', int(volume_limit), db.session)
    update_needed |= update_user_limit(user, limits, 'media', int(media_limit), db.session)

    if update_needed:
        db.session.commit()
        return generate_success_response('User limits updated')
    else:
        db.session.rollback()

    return generate_success_response('No Change in Limits')


@admin_blueprint.route('/update/user/password', methods=['POST'])
@feature_required_silent(admin_blueprint, MANAGE_APP)
def change_password():
    """
    Change the password for a user.
    """
    user_id = clean_string(request.form.get('user_id'))
    if not is_integer(user_id):
        return generate_failure_response('user_id parameter is not an integer', 400)
    user_id = int(user_id)

    new_password = clean_string(request.form.get('new_password'))

    if is_blank(new_password):
        return generate_failure_response('new_password parameter is required', 400)

    user = get_user_by_id(user_id)
    if not user:
        return generate_failure_response(f'User {user_id} not found', 404)

    user.password = generate_password_hash(new_password)
    db.session.commit()

    return generate_success_response(f'Password for {user.username} has been changed')


@admin_blueprint.route('/update/my/password', methods=['POST'])
@shall_authenticate_user(admin_blueprint)
def change_my_password(user_details):
    """
    Change my own password.
    """
    user_id = user_details['uid']
    old_password = clean_string(request.form.get('old_password'))
    new_password = clean_string(request.form.get('new_password'))

    if is_blank(old_password):
        return generate_failure_response('old_password parameter is required', 400)

    if is_blank(new_password):
        return generate_failure_response('new_password parameter is required', 400)

    if is_blank(new_password):
        return generate_failure_response('new_password can not match old_password parameter', 400)

    user = get_user_by_id(user_id)
    if not user:
        return generate_failure_response('User record found', 404)

    if not check_password_hash(user.password, old_password):
        return generate_failure_response('old_password does not match current password', 400)

    user.password = generate_password_hash(new_password)
    db.session.commit()

    return generate_success_response('Your password has been changed')


@admin_blueprint.route('/list/properties', methods=['POST'])
@feature_required_silent(admin_blueprint, MANAGE_APP)
def list_properties():
    """
    List all application properties.
    """
    props = get_all_properties()
    properties_list = [{'id': prop.id, 'value': '', 'comment': prop.comment} for prop in props]
    return generate_success_response('', {'properties': properties_list})


@admin_blueprint.route('/get/property', methods=['POST'])
@feature_required_silent(admin_blueprint, MANAGE_APP)
def get_property_details():
    """
    Get details of a property.
    """
    prop_id = clean_string(request.form.get('property_id'))

    if is_blank(prop_id):
        return generate_failure_response('property_id parameter is required', 400)

    prop = get_property(prop_id)
    if not prop:
        return generate_failure_response(f'Property {prop_id} not found', 404)

    property_details = {'id': prop.id, 'value': prop.value, 'comment': prop.comment}

    return generate_success_response('', {'property': property_details})


@admin_blueprint.route('/update/property', methods=['POST'])
@feature_required_silent(admin_blueprint, MANAGE_APP)
def update_property():
    """
    Update the value of a property.
    """
    prop_id = clean_string(request.form.get('property_id'))
    value = clean_string(request.form.get('value'))

    if is_blank(prop_id):
        return generate_failure_response('property_id parameter is required', 400)

    if is_blank(value):
        return generate_failure_response('value parameter is required', 400)

    prop = AppProperties.query.get(prop_id)
    if not prop:
        return generate_failure_response(f'Property {prop} not found', 404)

    # Verify the value against the property definition
    for definition in current_app.config[PROPERTY_DEFINITIONS]:
        if definition.id == prop.id:
            result = definition.is_valid(value)
            if result:
                return generate_failure_response(f'Invalid value {value} for {prop.id}, {result}', 400)

            prop.value = value
            db.session.commit()

            return generate_success_response(f'Property {prop} value updated')

    return generate_failure_response('Property definition not found', 400)


# Common Validators
def limit_validator(features: str, book_limit: str, media_limit: str) -> Optional[tuple]:
    """
    Check if the limits are valid.
    """
    if is_blank(features):
        return generate_failure_response('features parameter required', 400)
    if is_blank(book_limit):
        return generate_failure_response('book_limit parameter required', 400)
    if is_blank(media_limit):
        return generate_failure_response('media_limit parameter required', 400)

    if not is_integer(features):
        return generate_failure_response(f'features parameter ({features}) is not an integer', 400)
    if not is_integer(book_limit):
        return generate_failure_response(f'book_limit parameter ({book_limit}) is not an integer', 400)
    if not is_integer(media_limit):
        return generate_failure_response(f'media_limit parameter ({media_limit}) is not an integer', 400)

    features = int(features)
    book_limit = int(book_limit)
    media_limit = int(media_limit)

    if not (0 <= features <= SUPER_ADMIN):
        return generate_failure_response('invalid features parameter value', 400)

    if not (0 <= book_limit <= 200):
        return generate_failure_response('invalid book_limit parameter value', 400)

    if not (0 <= media_limit <= 200):
        return generate_failure_response('invalid media_limit parameter value', 400)

    return None


@admin_blueprint.route('/list/hard_sessions', methods=['POST'])
@feature_required_silent(admin_blueprint, MANAGE_APP)
def list_hard_sessions():
    """
    List all application properties.
    """
    sessions = find_all_hard_sessions()
    session_list = [
        {'id': ses.id, 'uid': ses.user_id, 'created': format_datatime(ses.created), 'last': format_datatime(ses.last),
         'expired': format_datatime(ses.expired)} for ses in sessions]
    return generate_success_response('', {'hard_sessions': session_list})


@admin_blueprint.route('/remove/hard_session', methods=['POST'])
@feature_required_silent(admin_blueprint, MANAGE_APP)
def delete_hard_session():
    """
    Delete a Hard Session by session_id.
    """
    session_id = clean_string(request.form.get('session_id'))
    if not is_integer(session_id):
        return generate_failure_response('session_id parameter is not an integer', 400)
    session_id = int(session_id)

    hard_session = UserHardSession.query.get(session_id)
    if not hard_session:
        return generate_failure_response('Hard Session not found', 404)

    db.session.delete(hard_session)
    db.session.commit()

    return generate_success_response('Hard Session deleted')


@admin_blueprint.route('/list/my/hard_sessions', methods=['POST'])
@feature_required(admin_blueprint, HARD_SESSIONS)
def list_my_hard_sessions(user_details):
    """
    List all application properties.
    """
    sessions = find_my_hard_sessions(get_uid(user_details))
    session_list = [
        {'id': ses.id, 'uid': ses.user_id, 'created': format_datatime(ses.created), 'last': format_datatime(ses.last),
         'expired': format_datatime(ses.expired)} for ses in sessions]
    return generate_success_response('', {'hard_sessions': session_list})


@admin_blueprint.route('/remove/my/hard_session', methods=['POST'])
@feature_required(admin_blueprint, HARD_SESSIONS)
def delete_my_hard_session(user_details):
    """
    Delete a Hard Session by session_id for a specific user.
    """
    session_id = clean_string(request.form.get('session_id'))
    if not is_integer(session_id):
        return generate_failure_response('session_id parameter is not an integer', 400)
    session_id = int(session_id)

    hard_session = UserHardSession.query.get(session_id)
    if not hard_session:
        return generate_failure_response('Hard Session not found', 404)

    if hard_session.useid != get_uid(user_details):
        return generate_failure_response('Hard Session is not owned by you', 401)

    db.session.delete(hard_session)
    db.session.commit()

    return generate_success_response('Hard Session deleted')
