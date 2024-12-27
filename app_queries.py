from flask_sqlalchemy.session import Session

import platform
from typing import Optional
from app_properties import AppPropertyDefinition
from constants import PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER, PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER, \
    PROPERTY_SERVER_MEDIA_TEMP_FOLDER, PROPERTY_SERVER_SECRET_KEY, PROPERTY_SERVER_HOST_KEY, \
    PROPERTY_SERVER_AUTH_TIMEOUT_KEY, PROPERTY_SERVER_PORT_KEY, PROPERTY_SERVER_VOLUME_FOLDER, \
    PROPERTY_SERVER_VOLUME_FORMAT
from db import AppProperties, User, UserLimit, db, UserHardSession
from text_utils import is_not_blank


def _get_attr_value(attr_id: str) -> str:
    """
    Get the value of the attribute with the given ID.
    """
    try:
        result = AppProperties.query.filter_by(id=attr_id).first()
        if result is not None and is_not_blank(result.value):
            return result.value.strip()
    except Exception:
        pass
    return ''


def get_secret_key() -> str:
    """
    Get the secret key from the database.
    """
    value = _get_attr_value(PROPERTY_SERVER_SECRET_KEY)
    if is_not_blank(value):
        return value
    return "1234567890DEMO"


def get_server_port(override_value: int = 0) -> int:
    """
    Get the server port number from the database.
    """
    try:
        # See if a valid override was passed in
        if 0 < override_value < 65535:
            return override_value

        value = _get_attr_value(PROPERTY_SERVER_PORT_KEY)
        if is_not_blank(value):
            v = int(value)
            if 0 < v < 65535:
                return v
    except ValueError:
        pass
    # Fallback to default

    # For linux systems, port 80 is special, so need to switch to 5000
    if platform.system() == 'Linux':
        return 5000
    else:
        return 80


def get_server_host() -> str:
    """
    Get the server binding address from the database.
    """
    value = _get_attr_value(PROPERTY_SERVER_HOST_KEY)
    if is_not_blank(value):
        return value
    # Fallback to default
    return '0.0.0.0'


def get_auth_timeout() -> int:
    """
    Get the authentication timeout in minutes from the database.
    """
    try:
        value = _get_attr_value(PROPERTY_SERVER_AUTH_TIMEOUT_KEY)
        if is_not_blank(value):
            v = int(value)
            if 0 <= v <= 43200:
                return v
    except ValueError:
        pass
    # Fallback to default
    return 600


def get_media_primary_folder() -> str:
    """
    Get the path for the primary show folder
    """
    value = _get_attr_value(PROPERTY_SERVER_MEDIA_PRIMARY_FOLDER)
    if is_not_blank(value):
        return value
    return ""


def get_media_alt_folder() -> str:
    """
    Get the path for the alt show folder
    """
    value = _get_attr_value(PROPERTY_SERVER_MEDIA_ARCHIVE_FOLDER)
    if is_not_blank(value):
        return value
    return ""


def get_media_temp_folder() -> str:
    """
    Get the path for the temp show folder
    """
    value = _get_attr_value(PROPERTY_SERVER_MEDIA_TEMP_FOLDER)
    if is_not_blank(value):
        return value
    return ""


def get_volume_folder() -> str:
    """
    Get the path for the temp show folder
    """
    value = _get_attr_value(PROPERTY_SERVER_VOLUME_FOLDER)
    if is_not_blank(value):
        return value
    return ""


def get_volume_format() -> str:
    """
    Get the path for the temp show folder
    """
    value = _get_attr_value(PROPERTY_SERVER_VOLUME_FORMAT)
    if is_not_blank(value):
        return value
    return "PNG"


def get_plugin_value(property_id: str) -> str:
    """
    Get the path for the temp show folder
    """
    value = _get_attr_value(property_id)
    if is_not_blank(value):
        return value
    return ""


# Helper function to check and insert default AppProperties
def check_and_insert_property(property_definition: AppPropertyDefinition, session: Session):
    property_entry = AppProperties.query.filter_by(id=property_definition.id).first()
    if not property_entry:
        property_entry = AppProperties(id=property_definition.id, value=property_definition.get_default_value(),
                                       comment=property_definition.comment)
        session.add(property_entry)
        session.commit()


def clean_unknown_properties(property_definitions: list[AppPropertyDefinition], session: Session = db.session) -> bool:
    """
    Remove any unknown properties from the database.
    """
    known_properties = [property_definition.id for property_definition in property_definitions]
    unknown_properties = AppProperties.query.filter(AppProperties.id.notin_(known_properties)).all()
    was_changed = False
    for unknown_property in unknown_properties:
        was_changed = True
        session.delete(unknown_property)
    if was_changed:
        session.commit()
    return was_changed


def update_user_features(user: User, features: int) -> bool:
    if user.features != features:
        user.features = features
        return True
    return False


def update_user_group(user: User, group: Optional[int]) -> bool:
    if group is None and user.user_group_id is not None:
        user.user_group_id = None
        return True
    if group is not None and user.user_group_id is None:
        user.user_group_id = group
        return True
    if group is not None and user.user_group_id is not None:
        if user.user_group_id != group:
            user.user_group_id = group
            return True
    return False


def update_user_limit(user: User, limits: list[type[UserLimit]], limit_id: str, limit_value: int, db_session: Session = db.session) -> bool:
    for limit in limits:
        if limit.limit_type == limit_id:
            if limit.limit_value != limit_value:
                limit.limit_value = limit_value
                return True
            return False

    new_limit = UserLimit(
        user_id=user.id,
        limit_type=limit_id,
        limit_value=limit_value
    )

    # Add and commit the new book
    db_session.add(new_limit)
    return True

def find_all_hard_sessions(db_session: Session = db.session):
    return db_session.query(UserHardSession).order_by(UserHardSession.user_id, UserHardSession.id).all()

def find_my_hard_sessions(user_id: int, db_session: Session = db.session):
    return db_session.query(UserHardSession).filter(UserHardSession.user_id == user_id).order_by(UserHardSession.user_id, UserHardSession.id).all()