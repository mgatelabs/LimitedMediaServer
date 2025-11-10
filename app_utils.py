import hashlib
import os
import re
import ipaddress

def value_is_mac_address(value: str) -> str | None:
    """
    Validate if the given value is MAC like
    """
    pattern = r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$'
    if not bool(re.match(pattern, value)):
        return "Value is not a valid MAC address"
    return None


def value_is_folder(value: str) -> str | None:
    """
    Validate if the given value is a folder path.

    :param value: The path to validate.
    :return: None if valid, otherwise an error message.
    """
    if not os.path.isdir(value):
        return "Value must be a valid folder path."

    if not (os.access(value, os.R_OK) and os.access(value, os.W_OK)):
        return "Program does not have read/write access to the folder."

    return None

def value_is_hostname(value: str) -> str | None:
    """
    Validate if the given value is a valid hostname or IP address.

    :param value: The hostname or IP address to validate.
    :return: None if valid, otherwise an error message.
    """
    if not value or not isinstance(value, str):
        return "Value must be a non-empty string."

    # Check if it's a valid IPv4 or IPv6 address
    try:
        ipaddress.ip_address(value)
        return None
    except ValueError:
        pass  # Not an IP address, check hostname next

    # Hostname rules per RFC 1123:
    # - Each label may contain letters, digits, and hyphens
    # - Must not start or end with a hyphen
    # - Max length 255 characters
    # - Labels separated by dots
    if len(value) > 255:
        return "Hostname is too long (maximum 255 characters)."

    hostname_regex = re.compile(
        r"^(?=.{1,255}$)(?!-)[A-Z\d-]{1,63}(?<!-)(\.(?!-)[A-Z\d-]{1,63}(?<!-))*\.?$",
        re.IGNORECASE,
    )

    if not hostname_regex.match(value):
        return "Value must be a valid hostname or IP address."

    return None


def value_is_integer(value: str) -> str | None:
    """
    Validate if the given value is an integer.

    :param value: The value to validate.
    :return: None if valid, otherwise an error message.
    """
    try:
        int(value)
        return None
    except ValueError:
        return "Value must be an integer."


def value_is_between_int_x_y(x: int, y: int):
    """
    Validate if the given value is an integer between x and y.

    :param x: The lower bound.
    :param y: The upper bound.
    :return: A validator function that checks if the value is between x and y.
    """
    def validator(value: str) -> str | None:
        try:
            int_value = int(value)
            if x <= int_value <= y:
                return None
            else:
                return f"Value must be between {x} and {y}."
        except ValueError:
            return "Value must be an integer."

    return validator


def value_is_in_list(values:list[str]):
    """
    Validate if the given value is in a list of values

    :param values: string list
    :return: A validator function that checks if the value is in the list.
    """
    def validator(value: str) -> str | None:
        if value in values:
            return None
        else:
            return 'Invalid Value'

    return validator


def value_is_ipaddress(value: str) -> str | None:
    """
    Validate if the given value is a valid IP address.

    :param value: The value to validate.
    :return: None if valid, otherwise an error message.
    """
    ip_pattern = re.compile(
        r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$'
    )
    if ip_pattern.match(value):
        return None
    else:
        return "Value must be a valid IP address."


def get_random_hash():
    """
    Generate a random SHA-256 hash.

    :return: A random SHA-256 hash string.
    """
    return hashlib.sha256(os.urandom(64)).hexdigest()
