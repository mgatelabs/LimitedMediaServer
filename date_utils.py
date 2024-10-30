import datetime
from datetime import date, datetime


def convert_yyyymmdd_to_date(value: str) -> date:
    """
    Convert a string in 'YYYYMMDD' format to a date object.

    Args:
    value (str): The date string in 'YYYYMMDD' format.

    Returns:
    date: The corresponding date object.
    """
    return datetime.strptime(value, '%Y%m%d').date()


def convert_timestamp_to_datetime(creation_time: float) -> datetime:
    """
    Convert a Unix timestamp to a datetime object.

    Args:
    creation_time (float): The Unix timestamp.

    Returns:
    datetime: The corresponding datetime object.
    """
    return datetime.fromtimestamp(creation_time)


def convert_date_to_yyyymmdd(value: date) -> str:
    """
    Convert a date object to a string in 'YYYYMMDD' format.

    Args:
    value (date): The date object.

    Returns:
    str: The corresponding date string in 'YYYYMMDD' format.
    """
    return value.strftime('%Y%m%d')


def convert_datetime_to_yyyymmdd(value: datetime) -> str:
    """
    Convert a datetime object to a string in 'YYYYMMDD' format.

    Args:
    value (datetime): The datetime object.

    Returns:
    str: The corresponding date string in 'YYYYMMDD' format.
    """
    return value.strftime('%Y%m%d')
