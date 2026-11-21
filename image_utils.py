import os
import shutil
from pathlib import Path

from PIL import Image, ImageFile

from thread_utils import TaskWrapper

# Book scans can legitimately be extremely tall; do not trip PIL's
# decompression bomb limit for them
Image.MAX_IMAGE_PIXELS = None


def resize_image(input_path, output_path, target_width, file_format='PNG'):
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
    resized_image.save(output_path, format=file_format)


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


# Hard WebP limit: no dimension may exceed this value
WEBP_MAX_DIMENSION = 16383

# Width cap: images wider than this are scaled down (screen display, saves space)
MAX_DISPLAY_WIDTH = 2048


def _convert_single_image(filepath: str, output_path: str) -> list[str]:
    """
    Load one image and normalize it entirely in memory: RGBA and CMYK are
    always converted to RGB, 1-bit images are converted to grayscale when they
    need scaling, a width above 2048 is scaled down, and a height above the
    hard WebP limit is sliced into uniform pieces.

    Returns the list of files written (one when not split, one per slice
    when split).  Slices are written as temporary files in the same folder
    for the caller to renumber.  Raises an exception on failure.
    """
    with Image.open(filepath) as img:
        img.load()

        modified = False

        needs_resize = img.width > MAX_DISPLAY_WIDTH or img.height > WEBP_MAX_DIMENSION

        # RGBA and CMYK are always stripped (accidental alpha only bloats comic
        # pages).  Modes other than RGB/L are converted before any scaling, so
        # LANCZOS never resamples in the wrong color space: 1-bit becomes
        # grayscale to keep a little fuzziness, everything else becomes RGB.
        if img.mode in ('RGBA', 'CMYK') or (needs_resize and img.mode not in ('RGB', 'L')):
            target_mode = 'L' if (needs_resize and img.mode == '1') else 'RGB'
            img = img.convert(target_mode)
            modified = True

        # Scale down images that are too wide
        if img.width > MAX_DISPLAY_WIDTH:
            new_height = max(1, int(img.height * (MAX_DISPLAY_WIDTH / float(img.width))))
            img = img.resize((MAX_DISPLAY_WIDTH, new_height), Image.LANCZOS)
            modified = True

        if not modified and filepath.lower().endswith('.webp'):
            # Already a WebP that needs nothing done to it
            return []

        if img.height > WEBP_MAX_DIMENSION:
            # Split into uniform slices (rounded up so all pieces are the same size)
            slice_count = (img.height + WEBP_MAX_DIMENSION - 1) // WEBP_MAX_DIMENSION
            step = (img.height + slice_count - 1) // slice_count
            src_name = os.path.basename(filepath)
            pieces = []
            for i in range(slice_count):
                box = (0, i * step, img.width, min((i + 1) * step, img.height))
                piece_path = os.path.join(os.path.dirname(filepath), f'___{src_name}_slice_{i}.webp')
                img.crop(box).save(piece_path, format='WEBP', lossless=True)
                pieces.append(piece_path)
            return pieces

        img.save(output_path, format='WEBP', lossless=True)
        return [output_path]


def _renumber_folder(folder_path: str, logger: TaskWrapper) -> None:
    """
    Rename every WebP image in the folder sequentially (0001.webp, 0002.webp,
    ...).
    """
    files = sorted(f for f in os.listdir(folder_path)
                   if f.lower().endswith('.webp') and os.path.isfile(os.path.join(folder_path, f)))

    if not files:
        return

    # Move to neutral temp names first so sequential renaming never
    # collides with an existing page name
    temp_names = []
    for filename in files:
        temp_name = f'___renumber_{filename}'
        shutil.move(os.path.join(folder_path, filename), os.path.join(folder_path, temp_name))
        temp_names.append(temp_name)

    for index, temp_name in enumerate(temp_names, 1):
        final_name = f'{str(index).zfill(4)}.webp'
        final_path = os.path.join(folder_path, final_name)
        if os.path.exists(final_path):
            os.remove(final_path)
        shutil.move(os.path.join(folder_path, temp_name), final_path)

    if logger.can_debug():
        logger.debug(f'Renumbered {len(files)} images in {folder_path}')


def _remove_temp_slices(folder_path: str, logger: TaskWrapper) -> None:
    """
    Remove leftover slice temp files (___*.webp) from a crashed or partially
    completed conversion run, so they never get mistaken for real pages.
    """
    for entry in os.listdir(folder_path):
        if entry.startswith('___') and os.path.isfile(os.path.join(folder_path, entry)):
            logger.debug(f'Removing leftover temp file: {entry}')
            try:
                os.remove(os.path.join(folder_path, entry))
            except OSError:
                pass


def convert_images_to_format(input_folder: str, image_format: str, logger: TaskWrapper) -> bool:
    """
    Converts all images in the given folder to lossless WebP and corrects
    each image to fit the hard WebP dimension limit: RGBA and CMYK are
    always converted to RGB, modes that do not resample well (1-bit to
    grayscale, palette and others to RGB) are converted when the image
    needs scaling, any width above 2048 is scaled down, and any image
    taller than 16383 pixels is split into uniform slices — after which
    every image in the folder is renumbered sequentially (0001.webp,
    0002.webp, ...).

    Any non-image file in the folder is removed.  The ``image_format``
    argument is kept for signature compatibility; output is always WEBP.
    """
    result = False

    # Ensure the folder exists
    if not os.path.isdir(input_folder):
        logger.error(f"Error: The folder '{input_folder}' does not exist.")
        return result

    if image_format not in ('WEBP', 'PNG'):
        logger.error('Unknown Image Output Format')
        return False

    supported_formats = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp')

    # Remove leftover slices from a previously crashed conversion run
    _remove_temp_slices(input_folder, logger)

    # Remove anything in the folder that is not a usable image
    for filename in os.listdir(input_folder):
        filepath = os.path.join(input_folder, filename)
        if not os.path.isfile(filepath) or filename.lower().endswith(supported_formats):
            continue
        if not is_valid_image(filepath):
            logger.debug(f"Removing non-image file: {filename}")
            try:
                os.remove(filepath)
            except OSError:
                pass

    files = sorted(f for f in os.listdir(input_folder)
                   if os.path.isfile(os.path.join(input_folder, f))
                   and f.lower().endswith(supported_formats))

    # A split happened, so the whole folder gets renumbered after the pass
    needs_renumber = False

    for filename in files:
        filepath = os.path.join(input_folder, filename)
        try:
            previous_truncated = ImageFile.LOAD_TRUNCATED_IMAGES
            ImageFile.LOAD_TRUNCATED_IMAGES = True

            base, _ = os.path.splitext(filepath)
            already_webp = filename.lower().endswith('.webp')
            output_path = filepath if already_webp else base + '.webp'

            pieces = _convert_single_image(filepath, output_path)

            if len(pieces) > 1:
                # The original is now fully contained in its slices
                needs_renumber = True
                os.remove(filepath)
            elif not already_webp:
                os.remove(filepath)

            result = True

            if logger.can_trace():
                logger.trace(f"Converted '{filename}' to WebP ({len(pieces)} part(s))")
        except Exception as e:
            logger.warn(f"Failed to convert '{filename}': {e}")
        finally:
            ImageFile.LOAD_TRUNCATED_IMAGES = previous_truncated

    if needs_renumber:
        _renumber_folder(input_folder, logger)

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
                if file.stat().st_size < 10 * 1024:
                    logger.debug(f"Deleting {file.name} (file size is less than 10KB)")
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


def merge_two_images(image_a_path: str, image_b_path: str, is_horizontal: bool = False):
    try:
        if image_a_path.lower().endswith('.png'):
            extension = '.png'
            format_value = 'PNG'
        elif image_a_path.lower().endswith('.webp'):
            extension = '.webp'
            format_value = 'WEBP'
        else:
            raise ValueError(f"Unsupported file type: {os.path.splitext(image_a_path)[1]}")

        # Open both images
        image_a = Image.open(image_a_path)
        image_b = Image.open(image_b_path)

        if is_horizontal:
            if image_a.height != image_b.height:
                # Scale the taller image down to match the shorter one
                target_h = min(image_a.height, image_b.height)
                if image_a.height != target_h:
                    image_a = image_a.resize((int(image_a.width * target_h / image_a.height), target_h), Image.LANCZOS)
                else:
                    image_b = image_b.resize((int(image_b.width * target_h / image_b.height), target_h), Image.LANCZOS)
            new_image = Image.new("RGB", (image_a.width + image_b.width, image_a.height))
            new_image.paste(image_a, (0, 0))
            new_image.paste(image_b, (image_a.width, 0))
        else:
            if image_a.width != image_b.width:
                # Scale the wider image down to match the narrower one
                target_w = min(image_a.width, image_b.width)
                if image_a.width != target_w:
                    image_a = image_a.resize((target_w, int(image_a.height * target_w / image_a.width)), Image.LANCZOS)
                else:
                    image_b = image_b.resize((target_w, int(image_b.height * target_w / image_b.width)), Image.LANCZOS)
            new_image = Image.new("RGB", (image_a.width, image_a.height + image_b.height))
            new_image.paste(image_a, (0, 0))
            new_image.paste(image_b, (0, image_a.height))

        output_path = os.path.splitext(image_a_path)[0] + extension
        save_kwargs = {'lossless': True} if format_value == 'WEBP' else {}
        new_image.save(output_path, format_value, **save_kwargs)

        # Delete image B
        os.unlink(image_b_path)

        return True
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"An error occurred: {e}")


def split_image_into_pieces(source_path: str, positions: list[int],
                            is_horizontal: bool, output_dir: str,
                            tmp_prefix: str = '__split_tmp_') -> list[str]:
    """
    Crop source_path into len(positions)+1 WEBP lossless pieces at the given
    pixel offsets. Writes temp files to output_dir and returns their paths.

    Raises ValueError if positions are not strictly increasing or exceed the
    relevant image dimension.
    """
    with Image.open(source_path) as img:
        width, height = img.size
        dimension = height if is_horizontal else width

        prev = 0
        for pos in positions:
            if pos <= prev:
                raise ValueError(
                    f"Position {pos} must be greater than previous position {prev}")
            if pos >= dimension:
                raise ValueError(
                    f"Position {pos} is out of bounds for dimension {dimension}")
            prev = pos

        boundaries = [0] + list(positions) + [dimension]
        tmp_paths = []

        for i, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
            if is_horizontal:
                box = (0, start, width, end)
            else:
                box = (start, 0, end, height)

            piece = img.crop(box)
            tmp_path = os.path.join(output_dir, f"{tmp_prefix}{i:04d}.webp")
            piece.save(tmp_path, format='WEBP', lossless=True)
            tmp_paths.append(tmp_path)

    return tmp_paths


def is_valid_image(filepath):
    try:
        # Try opening the image file
        img = Image.open(filepath)
        # Verify the image by loading it
        img.verify()  # This ensures it's a valid image without fully decoding it
        return True
    except (IOError, SyntaxError) as e:
        return False
