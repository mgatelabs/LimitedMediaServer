from bs4 import BeautifulSoup, Tag


def get_first_valid_attribute(tag: Tag, *attributes: str):
    """
    Returns the first attribute that exists and has a non-empty value.

    Args:
        tag (Tag): A BeautifulSoup tag object.
        *attributes (str): A series of attribute names to check.

    Returns:
        str | None: The value of the first valid attribute, or None if none are valid.
    """
    if not tag or not isinstance(tag, Tag):
        return None  # Invalid input

    for attr in attributes:
        value = tag.get(attr)
        if value:  # Checks if the value exists and is not empty or None
            return value.strip()
    return None
