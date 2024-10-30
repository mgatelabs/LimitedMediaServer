import json
import os

from thread_utils import TaskWrapper
from typing import Dict, Any, Optional


def read_library_folder(directory: str, target_name: str = None) -> dict:
    """
    Reads all JSON files in the specified directory and combines the data into a single dictionary.

    Args:
    directory (str): Path to the directory containing the JSON files.
    target_name (str): Name of the specific JSON file to read. Default is None.

    Returns:
    dict: Dictionary containing the combined data from the JSON files.
    """
    combined_data: dict = {'books': []}

    files: list[str] = []
    if target_name:
        files.append(target_name + '.json')
    else:
        # List all files in the directory
        files = [file for file in os.listdir(directory) if file.endswith('.json')]

    # Iterate over each JSON file
    for filename in files:
        filepath: str = os.path.join(directory, filename)
        with open(filepath, 'r') as file:
            # Load JSON data from the file
            json_data: dict = json.load(file)

            # Assume each JSON file contains a list of book data
            if isinstance(json_data, dict):
                combined_data['books'].append(json_data)
            else:
                print(f"Invalid data format in file: {filename}")

    return combined_data


def write_library_config(library_config: Dict[str, any], file_path: str = "library.json", logger: TaskWrapper = None):
    """
    Writes the library configuration to the specified JSON file.

    Args:
    library_config (dict): Library configuration to write.
    file_path (str): Path to the JSON file. Default is "library.json".
    """
    try:
        with open(file_path, 'w') as file:
            json.dump(library_config, file, indent=4)
        if logger is not None and logger.can_trace():
            logger.trace(f"Library configuration has been successfully written to {file_path}")
    except Exception as e:
        if logger is not None:
            logger.error("Error writing library configuration:", e)


def get_book_from_library(library: Dict[str, Any], book_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the book from the library with the specified ID.

    Args:
    library (dict): Library dictionary containing a list of books.
    book_id (str): ID of the book to retrieve.

    Returns:
    dict: Book dictionary with the specified ID, or None if not found.
    """
    # Check if 'book-by-id' exists in the library
    if 'book-by-id' not in library:
        # Create the 'book-by-id' dictionary
        library['book-by-id'] = {book['id']: book for book in library['books'] if isinstance(book, dict)}

    # Use the 'book-by-id' dictionary for quick lookup
    return library['book-by-id'].get(book_id)
