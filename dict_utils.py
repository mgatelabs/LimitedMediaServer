def merge_dict_with_defaults(dest_dict: dict, source_dict: dict, default_dict: dict) -> dict:
    """
    Merge a destination dictionary with source and default dictionaries.

    Args:
    dest_dict (dict): The destination dictionary to update.
    source_dict (dict): The source dictionary containing values to merge.
    default_dict (dict): The dictionary containing default values.

    Returns:
    dict: The updated destination dictionary with merged values.
    """
    # Create a new dictionary to hold the merged values
    result_dict = {}

    # Iterate over the default dictionary and use values from the source dictionary if available
    for key, default_value in default_dict.items():
        result_dict[key] = source_dict.get(key, default_value)

    # Update the destination dictionary with the merged values
    dest_dict.update(result_dict)

    return dest_dict


def update_dict_with_defaults(source_dict: dict, default_dict: dict) -> dict:
    """
    Update a dictionary with default values from another dictionary.

    Args:
    source_dict (dict): The source dictionary to update.
    default_dict (dict): The dictionary containing default values.

    Returns:
    dict: The updated dictionary with default values applied.
    """
    # Create a new dictionary to hold the merged values
    result_dict = {}

    # Copy over everything
    result_dict.update(source_dict)

    # Iterate over the default dictionary and use values from the JSON object if available
    for key, default_value in default_dict.items():
        result_dict[key] = source_dict.get(key, default_value)

    return result_dict
