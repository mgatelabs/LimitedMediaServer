from typing import Optional, Type

from flask_sqlalchemy.session import Session

from db import db, User, UserGroup, MediaFolder


def get_all_users(db_session: Session = db.session) -> list[Type[User]]:
    """
    List all users.
    """
    return db_session.query(User).order_by(User.username).all()


def get_all_groups(db_session: Session = db.session) -> list[Type[UserGroup]]:
    """
    List all groups.
    """
    return db_session.query(UserGroup).order_by(UserGroup.name).all()


def get_user_by_id(uid: int, db_session: Session = db.session) -> Optional[User]:
    """
    Get a specific user by ID.
    """
    return db_session.query(User).get(uid)


def get_group_by_id(gid: int, db_session: Session = db.session) -> Optional[UserGroup]:
    """
    Get a specific group by ID.
    """
    return db_session.query(UserGroup).get(gid)


def count_folders_for_group(gid: int, db_session: Session = db.session) -> int:
    """
    Count the number of folders owned by a group.
    Args:
        gid: The Group ID
        db_session: Optional database session.

    Returns: The count of folders owned by the group.
    """
    query = db_session.query(MediaFolder)

    query = query.filter(MediaFolder.owning_group_id == gid)

    return query.count()
