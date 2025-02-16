import re


def pad_decimal_string(input_string: str):
    """
    Ensure the number in-front of a decimal is padded by 4
    :param input_string:
    :return: "####.#" or "####"
    """
    # Check if the input string contains a decimal point
    if '.' in input_string:
        # Split the string into integer and decimal parts
        integer_part, decimal_part = input_string.split('.')

        # Pad the integer part
        padded_integer = integer_part.zfill(4)

        # Join the padded integer part with the decimal part
        padded_string = padded_integer + '.' + decimal_part
    else:
        # If no decimal point, simply left pad the input string
        padded_string = input_string.zfill(4)

    return padded_string


def pad_integer_number(number: int, length: int = 3):
    """
    Ensure a number is 3/4 digits by padding with leading zeros.

    Args:
    number (int): The number to pad.
    length (int): The number digits to pad to.

    Returns:
    str: The padded number as a string.
    :param number:
    :param length:
    """
    if length == 3:
        return '{:03d}'.format(number)
    elif length == 4:
        return '{:04d}'.format(number)
    else:
        return str(number)


def extract_decimal_from_string(input_str: str) -> float:
    """
    Extract a decimal number from a string.

    Args:
    input_str (str): The input string containing the decimal number.

    Returns:
    float: The extracted decimal number. Returns 0.0 if no valid number is found.
    """
    # Remove all characters except digits and period
    cleaned_string = re.sub(r'[^\d.]', '', input_str)

    # Parse the cleaned string as a decimal number
    try:
        decimal_number = float(cleaned_string)
    except ValueError:
        # If the parsed number is NaN or any other error occurs, return 0
        return 0.0

    return decimal_number


def is_integer(input_string: str) -> bool:
    """
    Check if the input string contains only integer characters.

    Args:
    input_string (str): The input string to check.

    Returns:
    bool: True if the string contains only integer characters, False otherwise.
    """
    return input_string.isdigit()

def is_integer_with_sign(input_string: str) -> bool:
    """
    Check if the input string contains only integer characters.

    Args:
    input_string (str): The input string to check.

    Returns:
    bool: True if the string contains only integer characters, False otherwise.
    """
    return input_string.lstrip('-').isdigit() and input_string != "-"

def is_boolean(input_string: str) -> bool:
    """
    Check if the input string contains only integer characters.

    Args:
    input_string (str): The input string to check.

    Returns:
    bool: True if the string contains only integer characters, False otherwise.
    """
    input_string = input_string.lower().strip()
    return input_string == 'true' or input_string == 'false'

def parse_boolean(input_string: str) -> bool:
    """
    Parse a string into a boolean
    :param input_string: String to convert
    :return: True or False
    """
    return input_string.lower().strip() == 'true'