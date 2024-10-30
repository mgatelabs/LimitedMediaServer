import os
from pathlib import Path

from PIL import Image

from thread_utils import TaskWrapper, NoOpTaskWrapper


def resize_image(input_path, output_path, target_width):
    """
    Resize an image to a target width while maintaining aspect ratio.
    If the image is tall (height > 2 * width), it will be cropped to a square.

    Args:
        input_path (str): Path to the input image file.
        output_path (str): Path to save the resized image.
        target_width (int): The target width for the resized image.

    Returns:
        None
    """
    # Open the image
    image = Image.open(input_path)

    # Convert image to RGB mode if it is in CMYK mode
    if image.mode == 'CMYK':
        image = image.convert('RGB')

    # Calculate the scaling factor to maintain aspect ratio
    width, height = image.size

    # Check if the image is tall (height > 2 x width)
    if height > 2 * width:
        # Set target height to match the width for a 1:1 aspect ratio
        target_height = target_width

        # Resize image to the target width, preserving aspect ratio
        width_percent = (target_width / float(width))
        new_height = int(height * width_percent)
        resized_image = image.resize((target_width, new_height), Image.LANCZOS)

        # Calculate the starting point for the crop (halfway down the image)
        crop_top = max(0, new_height // 2 - target_height // 2)
        crop_bottom = crop_top + target_height

        # Crop the image to a square starting from halfway down
        resized_image = resized_image.crop((0, crop_top, target_width, crop_bottom))
    else:
        # Resize the image normally
        width_percent = (target_width / float(width))
        height_size = int((float(height) * float(width_percent)))
        resized_image = image.resize((target_width, height_size), Image.LANCZOS)

    # Save the resized image as PNG
    resized_image.save(output_path, format='PNG')


def crop_and_resize(input_path, output_path, size, side=False):
    # Open the image
    original_image = Image.open(input_path)

    # Get the original image dimensions
    original_width, original_height = original_image.size

    # Calculate the crop area
    if original_width > original_height:

        if side:
            # Landscape image (side)
            left = (original_width - original_height)
            top = 0
            right = original_width
            bottom = original_height
        else:
            # Landscape image (standard)
            left = (original_width - original_height) // 2
            top = 0
            right = left + original_height
            bottom = original_height
    else:
        # Portrait or square image (no crop needed)
        left = 0
        top = 0
        right = original_width
        bottom = original_height

    # Crop the image
    cropped_image = original_image.crop((left, top, right, bottom))

    # Resize the image to the desired size
    resized_image = cropped_image.resize((size, size))

    # Save the result
    resized_image.save(output_path)
    print(f"Image cropped and resized, saved to {output_path}")


def convert_images_to_png(folder_path, logger: TaskWrapper = NoOpTaskWrapper()):
    """
    Convert all image files in the given folder and its subfolders to PNG format.
    Removes files with non-standard extensions.

    Args:
        folder_path (str): Path to the folder containing image files.
        logger (TaskWrapper): Logger for tracing and debugging.

    Returns:
        None
    """
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            source_path = os.path.join(root, file)
            if file.lower().endswith(".jpg") or file.lower().endswith(".jpeg") or file.lower().endswith(
                    ".png") or file.lower().endswith(".webp"):
                if logger.can_trace():
                    logger.trace(f'{source_path} had a known image extension')
                dest_path = os.path.splitext(source_path)[0] + ".png"
                convert_image_to_png(source_path, dest_path, logger)
            else:
                if logger.can_trace():
                    logger.trace(f'{source_path} did not have a standard extension, removing file')
                os.remove(source_path)


def convert_image_to_png(source_file, destination_file, logger: TaskWrapper = NoOpTaskWrapper()):
    """
    Convert a single image file to PNG format.
    Removes the source file if it is less than 10 KB or if an error occurs.

    Args:
        source_file (str): Path to the source image file.
        destination_file (str): Path to save the converted PNG file.
        logger (TaskWrapper): Logger for tracing and debugging.

    Returns:
        bool: True if conversion was successful, False otherwise.
    """
    try:

        # Ensure the source file is within the expected directory
        source_path = Path(source_file).resolve()
        destination_path = Path(destination_file).resolve()
        if not source_path.is_file() or not source_path.exists():
            logger.set_failure()
            logger.critical(f'{source_file} is not a valid file')
            return False

        # Check if the file size is less than 10 KB
        if source_path.stat().st_size < 10 * 1024:
            if logger.can_trace():
                logger.trace(f'Erasing file {source_file} since it is less than 10KB')
            source_path.unlink()
            return False

        # Try to open the image
        with Image.open(source_file) as img:
            # Convert the image to RGB if it's not already in a mode suitable for PNG (e.g., 'P', 'RGBA')
            if img.mode not in ("RGB", "RGBA"):
                if logger.can_trace():
                    logger.trace(f'{source_file} was not in the correct color mode')
                img = img.convert("RGB")

            # Remove the source file before saving (in case it's the same as the destination)
            os.remove(source_file)

            # Save the image as PNG to the destination
            img.save(destination_path, format="PNG")

        return True

    except (OSError, IOError) as e:
        # If the image can't be opened or processed, erase the source file
        if os.path.exists(source_file):
            os.remove(source_file)

        logger.set_failure()
        logger.critical(str(e))

        return False


def clean_images_folder(folder_path, logger: TaskWrapper):
    """
    Clean the images folder by removing files that are less than 20 KB or not a valid format.

    Args:
        folder_path (str): Path to the folder containing image files.
        logger (TaskWrapper): Logger for tracing and debugging.

    Returns:
        None
    """
    # Supported file formats
    valid_formats = {"JPEG", "PNG", "WEBP"}

    # Path object for folder
    folder = Path(folder_path)

    # Loop through all files in the folder
    for file in folder.iterdir():
        # Check if it's a file and not a directory
        if file.is_file():
            try:
                # Check the size of the file (in bytes)
                if file.stat().st_size < 20 * 1024:
                    logger.debug(f"Deleting {file.name} (file size is less than 20KB)")
                    file.unlink()  # Remove file
                else:
                    # Open the image to check its format
                    with Image.open(file) as img:
                        if img.format not in valid_formats:
                            logger.warn(f"Deleting {file.name} (invalid format: {img.format})")
                            logger.set_warning()
                            file.unlink()  # Remove invalid format file
            except Exception as e:
                logger.debug(f"Deleting {file.name} (error opening file: {e})")
                file.unlink()  # Remove corrupt or unreadable files
                logger.set_failure()
