import re
import uuid
from typing import Optional, Tuple, List


def is_blank(s: str) -> bool:
    """
    Check if the given string is blank.

    Args:
    s (str): The string to check.

    Returns:
    bool: True if the string is blank, False otherwise.
    """
    if s is None:
        return True
    # Check if the string contains only whitespace characters
    return not bool(s.strip())


def is_not_blank(s: str) -> bool:
    """
    Check if the given string is not blank.

    Args:
    s (str): The string to check.

    Returns:
    bool: True if the string is not blank, False otherwise.
    """
    if s is None:
        return False
    # Check if the string contains any non-whitespace characters
    return bool(s.strip())


def clean_string(s: str) -> str:
    """
    Clean the given string by removing leading and trailing whitespace.

    Args:
    s (str): The string to clean.

    Returns:
    str: The cleaned string.
    """
    if s is None:
        return ""
    return s.strip()


def is_valid_username(username: str) -> bool:
    # Convert to lowercase
    username = username.lower()

    # Check if the length is at least 5 characters
    if len(username) < 5:
        return False

    # Regular expression to match allowed characters (lowercase letters, digits, periods, and at sign)
    pattern = r'^[a-z0-9.@]+$'

    # Check if the username matches the pattern
    return bool(re.match(pattern, username))


def is_valid_book_id(value: str) -> bool:
    # Convert to lowercase
    value = value.lower()

    # Check if the length is at least 5 characters
    if len(value) < 5 or len(value) > 128:
        return False

    pattern = r'^[a-z0-9_-]+$'

    # Check if the username matches the pattern
    return bool(re.match(pattern, value))


def find_line_with_text(text, input_string):
    # Split the input string into lines
    lines = input_string.split('\n')

    # Iterate over each line
    for line in lines:
        # Check if the text is in the line
        if text in line:
            return line

    # If text is not found in any line
    return None


def extract_text_between_quotes(input_string):
    # Define the regular expression pattern to match text between double quotes
    pattern = r'"([^"]*)"'

    # Use re.findall to find all matches of the pattern in the input string
    matches = re.findall(pattern, input_string)

    # Return the matched text
    return matches


def extract_content_between_tokens(input_string, start_token, end_token):
    start_index = input_string.find(start_token)
    if start_index == -1:
        return None  # Start token not found
    start_index += len(start_token)

    end_index = input_string.find(end_token, start_index)
    if end_index == -1:
        return None  # End token not found

    return input_string[start_index:end_index]


def extract_page_numbers(input_string):
    # Define the regular expression pattern to match "Page":"<number>"
    pattern = r'"Page":"(\d{1,3})"'

    # Use re.findall to find all matches of the pattern in the input string
    matches = re.findall(pattern, input_string)

    # Convert matched strings to integers
    numbers = [int(match) for match in matches]

    return numbers


def extract_directory_folder(input_string):
    # Define the regular expression pattern to match "Page":"<number>"
    pattern = r'"Directory":"([a-zA-Z0-9]{1,10})"'

    # Use re.search to find the first match of the pattern in the input string
    match = re.search(pattern, input_string)

    # If a match is found, return the first captured group; otherwise, return None
    return match.group(1) if match else None


def extract_chapter_numbers(input_string):
    # Define the regular expression pattern to match "Chapter":"<number>"
    pattern = r'"Chapter":"(\d{1,6})"'

    # Use re.findall to find all matches of the pattern in the input string
    matches = re.findall(pattern, input_string)

    # Convert matched strings to integers
    numbers = [int(match) for match in matches]

    return numbers


def clean_and_convert_to_decimal(value):
    # Clean the value by removing any non-numeric characters except the period
    cleaned_value = ''.join(c for c in value if c.isdigit() or c == '.')

    # Convert the cleaned value to a decimal number
    return float(cleaned_value) if cleaned_value else 0.0


def extract_numbers_and_period(source_string):
    # Use regular expression to find numbers and periods in the string
    numbers_and_period = re.findall(r'\d+\.\d+|\d+', source_string)

    # Join the found numbers and periods into a single string
    result = ' '.join(numbers_and_period)

    return result


def extract_strings_between(lst: list[str], start: str, end: str) -> list[str]:
    """
    Extract strings from a list that are between two specified strings.

    Args:
    lst (list[str]): List of strings.
    start (str): Starting string.
    end (str): Ending string.

    Returns:
    list[str]: List of strings between the start and end strings.
    """
    recording = False  # Flag to start recording strings
    result = []  # List to store the result

    for string in lst:
        if string == start:
            recording = True  # Start recording when the start string is found
        elif string == end:
            recording = False  # Stop recording when the end string is found
            result.append(string)  # Include the end string in the result
            break  # Exit the loop after finding the end string

        if recording:
            result.append(string)  # Append the string to the result if recording

    return result


def extract_paths(input_string: str, front: str) -> Optional[list[str]]:
    """
    Extract paths from a string starting with a specified front string.

    Args:
    input_string (str): The input string containing the paths.
    front (str): The front string that the input string should start with.

    Returns:
    Optional[list[str]]: List of paths extracted from the input string, or None if the input string does not start with the front string.
    """
    # Check if the string starts with the specified front string
    if input_string.startswith(front):
        # Remove the front string and split the remaining string by "$"
        paths = input_string[len(front):].split("$")
        # Remove any empty strings resulting from consecutive "$" characters
        paths = [path for path in paths if path]
        return paths
    else:
        return None  # If the string doesn't start with the front string


def extract_chapter_progress(input_string: str) -> Tuple[str, str]:
    """
    Extract the chapter progress from a string.

    Args:
    input_string (str): The input string containing the chapter progress.

    Returns:
    Tuple[str, str]: A tuple containing two parts of the chapter progress.
                     The first part is the numeric portion extracted from the input string.
                     The second part is the remaining portion of the input string after the '^' character.
    """
    # Initialize portion_a and portion_b
    portion_a = ""
    portion_b = ""

    # Check if the input contains the '^' character
    if '^' in input_string:
        parts = input_string.split('^', 1)
        portion_a = parts[0]
        portion_b = parts[1] if len(parts) > 1 else ""
    else:
        portion_a = input_string

    # Strip out all non-decimal characters from portion_a
    portion_a = re.sub(r'[^0-9.]', '', portion_a)

    return portion_a, portion_b


def is_guid(value: str) -> bool:
    """
    Verify if the string is a guid
    :param value:
    :return:
    """
    try:
        uuid_obj = uuid.UUID(value, version=4)
        return str(uuid_obj) == value
    except ValueError:
        return False


def common_prefix_postfix(strings: List[str]):
    """
    Find the common prefix and post for a series of strings
    :param strings: list of strings
    :return: prefix, postfix
    """
    if len(strings) <= 1:
        return "", ""

    prefix = strings[0]
    postfix = strings[0]

    # Find the greatest common prefix
    for s in strings[1:]:
        while not s.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                break

    # Find the greatest common postfix
    for s in strings[1:]:
        while not s.endswith(postfix):
            postfix = postfix[1:]
            if not postfix:
                break

    return prefix, postfix


def extract_yt_code(s) -> Optional[str]:
    # Define the pattern with a capturing group for the desired value
    pattern = r".*\[([a-zA-Z0-9-_]+)\]\.mp3"

    # Search for the pattern in the string
    match = re.search(pattern, s)

    # If a match is found, return the captured group, else return None
    if match:
        return match.group(1)
    return None


def remove_prefix_and_postfix(s: str, prefix: str, postfix: str):
    # Remove the prefix if it exists
    if s.startswith(prefix):
        s = s.removeprefix(prefix)

    # Remove the postfix if it exists
    if s.endswith(postfix):
        s = s.removesuffix(postfix)

    return s


def remove_start_digits_pattern(s):
    # Define the pattern: "- " followed by three digits and a space
    pattern = r"^- \d{3} "

    # Use re.sub to remove the pattern from the start of the string if it exists
    return re.sub(pattern, '', s)


def extract_artist_title_from_audio_filename(filename):
    #filename = 'artist - title[a-zA-Z0-9-_].mp3'
    # Remove the file extension first
    filename_without_extension = filename.rsplit('.', 1)[0]

    # Split the filename at the last hyphen
    artist, _, title_with_brackets = filename_without_extension.rpartition(' - ')

    # Optionally, remove any text in brackets from the title
    title = re.sub(r'\[.*\]', '', title_with_brackets).strip()

    return artist, title