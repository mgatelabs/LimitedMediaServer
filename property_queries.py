from typing import Optional, Type

from flask_sqlalchemy.session import Session

from db import db, AppProperties


def get_all_properties(session: Session = db.session) -> list[Type[AppProperties]]:
    """
    List all users.
    """
    return session.query(AppProperties).order_by(AppProperties.id).all()


def get_property(property_id: str, session: Session = db.session) -> Optional[Type[AppProperties]]:
    """
    List all users.
    """
    return session.query(AppProperties).get(property_id)
