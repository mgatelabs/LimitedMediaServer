import os
from pathlib import Path

from PIL import Image

from thread_utils import TaskWrapper


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


def convert_images_to_format(input_folder: str, image_format: str, logger: TaskWrapper) -> bool:
    """
    Converts all images in the given folder to the specific format.
    Keeps the same filename but changes the extension.
    """
    result = False

    # Ensure the folder exists
    if not os.path.isdir(input_folder):
        logger.error(f"Error: The folder '{input_folder}' does not exist.")
        return result

    # Supported image formats
    if image_format == 'WEBP':
        extension = '.webp'
        supported_formats = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff')
    elif image_format == 'PNG':
        extension = '.png'
        supported_formats = ('.jpg', '.jpeg', '.webp', '.bmp', '.tiff')
    else:
        logger.error('Unknown Image Output Format')
        return False

    # Process each file in the folder
    files = os.listdir(input_folder)
    total = len(files)
    count = 0
    for filename in files:
        filepath = os.path.join(input_folder, filename)
        count = count + 1
        logger.update_percent((count / total) * 100.0)
        if os.path.isfile(filepath) and filename.lower().endswith(supported_formats):
            try:
                with Image.open(filepath) as img:
                    # Generate output file path with .webp extension
                    output_path = os.path.splitext(filepath)[0] + extension

                    # Save image in non-lossy WebP format
                    img.save(output_path, format=image_format, lossless=True)

                    result = True

                    if logger.can_trace():
                        logger.trace(f"Converted '{filename}' to '{os.path.basename(output_path)}'")
                # Remove the source file
                os.remove(filepath)

            except Exception as e:
                print(f"Failed to convert '{filename}': {e}")

    return result


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


def split_and_save_image(image_path: str, position: int, is_horizontal: bool, keep_first: bool):
    """
    Split an image and only save a part of it
    :param image_path: The image location
    :param position: The position top cut the image from
    :param is_horizontal: True for horizontal cut
    :param keep_first: True to keep the Top/Left image
    :return:
    """

    if image_path.lower().endswith('.png'):
        format_value = 'PNG'
    elif image_path.lower().endswith('.webp'):
        format_value = 'WEBP'
    else:
        # Wrong ending
        return False

    # Load the image
    with Image.open(image_path) as img:
        # Get dimensions
        width, height = img.size

        # Sanity check: ensure position is within bounds
        if is_horizontal:
            # For horizontal split, position must be between 1 and height - 1
            if position <= 0 or position >= height:
                raise ValueError(f"Position {position} is out of bounds for image height {height}.")
        else:
            # For vertical split, position must be between 1 and width - 1
            if position <= 0 or position >= width:
                raise ValueError(f"Position {position} is out of bounds for image width {width}.")

        # left, top, right, bottom

        # Define the box for cropping
        if is_horizontal:
            # Split horizontally at `position`
            if keep_first:
                box = (0, 0, width, position)
            else:
                box = (0, position, width, height)
        else:
            # Split vertically at `position`
            if keep_first:
                box = (0, 0, position, height)
            else:
                box = (position, 0, width, height)

        # Crop the image
        cropped_img = img.crop(box)

        # Save the cropped image, overwriting the original with PNG format
        cropped_img.save(image_path, format=format_value, lossless=True)


def merge_two_images(image_a_path: str, image_b_path: str):
    try:
        if image_a_path.lower().endswith('.png'):
            extension = '.png'
            format_value = 'PNG'
        elif image_a_path.lower().endswith('.webp'):
            extension = '.webp'
            format_value = 'WEBP'
        else:
            # Wrong ending
            return False

        # Open both images
        image_a = Image.open(image_a_path)
        image_b = Image.open(image_b_path)

        # Check if the widths are the same
        if image_a.width != image_b.width:
            return False

        # Calculate the new height (sum of both images' heights)
        new_height = image_a.height + image_b.height

        # Create a new image with the same width and new height
        new_image = Image.new("RGB", (image_a.width, new_height))

        # Paste image A at the top and image B right below it
        new_image.paste(image_a, (0, 0))
        new_image.paste(image_b, (0, image_a.height))

        # Overwrite A's path with a PNG extension
        output_path = os.path.splitext(image_a_path)[0] + extension
        new_image.save(output_path, format_value, lossless=True)

        # Delete image B
        os.unlink(image_b_path)

        return True
    except Exception as e:
        raise ValueError(f"An error occurred: {e}")
