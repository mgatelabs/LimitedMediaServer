import argparse
import os.path
import platform
import re
import shlex
import shutil
import subprocess
from datetime import datetime
from time import sleep
from urllib.parse import urljoin

from flask_sqlalchemy.session import Session

from curl_utils import custom_curl_get, read_temp_file, read_header_file
from feature_flags import MANAGE_MEDIA
from file_utils import is_valid_url, temporary_folder
from html_utils import get_headers
from media_probe import get_file_formats
from media_queries import find_folder_by_id, insert_file
from media_utils import get_data_for_mediafile, get_video_params, make_blank_segment
from plugin_methods import plugin_filename_arg, plugin_url_arg, plugin_select_arg, plugin_select_values
from plugin_system import ActionMediaFolderPlugin
from text_utils import is_blank
from thread_utils import TaskWrapper


class DownloadM3u8PluginEx(ActionMediaFolderPlugin):
    """
    Download from YTube
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'dlm3u8ex'

    def get_sort(self):
        return {'id': 'media_dl.m3u8.ex', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Save Video from M3u8 (Ex)'

    def get_action_id(self):
        return 'action.download.m3u8.ex'

    def get_action_icon(self):
        return 'download'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(
            plugin_select_arg('Location', 'dest', 'primary',
                              plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'), '', 'media', adv='Y')
        )

        result.append(
            plugin_url_arg('Origin', 'origin', 'The origin for the Url.', '', 'no', "Origin")
        )

        result.append(
            plugin_filename_arg('Filename', 'filename', 'The name of the file.')
        )

        result.append(
            plugin_url_arg('URL', 'url', 'The link to the m3u8 file.', '', 'yes', "url")
        )

        return result

    def process_action_args(self, args):
        results = []

        if 'url' not in args or args['url'] is None or args['url'] == '':
            results.append('url is required')

        if 'origin' not in args or args['origin'] is None or args['origin'] == '':
            results.append('origin is required')

        if 'filename' not in args or args['filename'] is None or args['filename'] == '':
            results.append('filename is required')

        if not is_valid_url(args['url']):
            results.append('url is not valid url')

        if not is_valid_url(args['origin']):
            results.append('origin is not valid url')

        if 'dest' not in args or is_blank(args['dest']):
            results.append('dest is required')
        elif not (args['dest'] == 'primary' or args['dest'] == 'archive'):
            results.append('Invalid dest value')

        if len(results) > 0:
            return results
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def is_ready(self):
        return super().is_ready() and platform.system() == 'Linux'

    def create_task(self, db_session: Session, args):
        filename = args['filename']
        return DownloadM3u8JobEx("Download M3u8", f'Downloading {filename} from M3u8 to folder ' + args['folder_id'],
                                 args['folder_id'], filename, args['url'].strip(), args['origin'].strip(),
                                 args['dest'], self.primary_path,
                                 self.archive_path, self.temp_path)


def file_to_hex_string(filepath):
    with open(filepath, "rb") as f:
        data = f.read()
    hex_string = data.hex()
    return hex_string


class DownloadM3u8JobEx(TaskWrapper):
    def __init__(self, name, description, folder_id, filename, url, origin, dest, primary_path, archive_path,
                 temp_path):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.filename = filename
        self.url = url
        self.origin = origin
        self.dest = dest
        self.primary_path = primary_path
        self.archive_path = archive_path
        self.temp_path = temp_path
        self.ref_folder_id = folder_id

    def run(self, db_session: Session):

        if is_blank(self.primary_path) or is_blank(self.archive_path) or is_blank(self.temp_path):
            self.critical('This feature is not ready.  Please configure the app properties and restart the server.')

        source_row = find_folder_by_id(self.folder_id, db_session)
        if source_row is None:
            self.critical('Source Folder not found')
            self.set_failure()
            return

        is_archive = self.dest == 'archive'

        with temporary_folder(self.temp_path, self) as temp_folder:

            self.debug(f'temp folder: {temp_folder}')

            # The M3u8 file
            temp_m3u8_file = os.path.join(temp_folder, 'download.m3u8')
            # The re-made M3u8 file
            made_m3u8_file = os.path.join(temp_folder, 'remade.m3u8')
            # The lines to re-make
            made_lines = []

            headers = get_headers(self.url, True, self, False, self.origin)

            if headers is None:
                self.error('Unable to get Headers, stopping')
                return False

            # Try to get the M3u8 file
            if not custom_curl_get(self.url, headers, temp_m3u8_file, self):
                self.error("Failed to download m3u8.")
                self.set_failure()
                return None

            # We have the file, read it in
            response_text = read_temp_file(temp_m3u8_file)

            # Break it up into lines
            lines = response_text.splitlines()

            # Figure out the base URL from the playlist URL
            base_url = self.url.rsplit("/", 1)[0] + "/"

            # This is where the final file will go
            temp_file = os.path.join(temp_folder, 'download.mp4')

            # We may need an encryption key
            temp_key = os.path.join(temp_folder, 'download.key')
            has_key = False

            # Process playlist
            i = 0
            total_length = len(lines)

            last_good_segment = None
            last_determined_ending = None

            while i < len(lines):

                if self.is_cancelled:
                    return

                # Update the progress
                self.update_progress((((i + 1) * (1.0)) / total_length) * 100.0)
                line = lines[i].strip()

                if line.startswith("#EXT-X-KEY:"):
                    self.info("Found Key Definition")
                    self.debug(line)
                    method_match = re.search(r'METHOD=([^,]+)', line)
                    uri_match = re.search(r'URI="([^"]+)"', line)
                    iv_match = re.search(r'IV=0x([0-9a-fA-F]+)', line)

                    self.debug(f'{method_match}, {uri_match}, {iv_match}')

                    if method_match:  # and method_match.group(1) == "AES-128":
                        key_url = urljoin(base_url, uri_match.group(1))
                        # iv_hex = iv_match.group(1) if iv_match else None

                        if not custom_curl_get(key_url, headers, temp_key, self):
                            self.error("Failed to download encryption key.")
                            self.set_failure()
                            return None

                        # key_data = file_to_hex_string(temp_key)
                        has_key = True

                        self.debug(f"Decryption key fetched from: {key_url}")

                    made_lines.append(line.replace(key_url, 'download.key'))

                    i += 1
                elif line.startswith("#EXTINF:"):
                    # duration = float(line.split(":")[1].split(",")[0])

                    segment_path = lines[i + 1].strip()
                    segment_url = urljoin(base_url, segment_path)
                    segment_name = f'seg_{i}.mp4'
                    segment_file = os.path.join(temp_folder, segment_name)

                    self.debug(f"Downloading segment: {segment_url}")

                    temp_header_file = os.path.join(temp_folder, f'seg_{i}.txt')

                    if not custom_curl_get(segment_url, headers, segment_file, self, header_file=temp_header_file):
                        self.warn(f"Failed to download m3u8 segment {segment_name}.")
                        self.set_warning()
                    else:

                        current_headers = read_header_file(temp_header_file)

                        http_status = current_headers['@HTTP_STATUS']

                        # Skip missing files
                        if http_status != '404':

                            if http_status != 200:
                                self.debug(f'http-status: {http_status}')

                            if 'content-type' in current_headers:
                                self.debug(f'{segment_name} content-type: {current_headers.get("content-type")}')

                            valid_format = True

                            determined_ending = 'mp4'

                            available_format = get_file_formats(segment_file, self)
                            if available_format is None:
                                valid_format = has_key
                            elif ('mp4' == available_format):
                                valid_format = True
                                self.trace(f'Segment {segment_name} is MP4')
                            else:
                                determined_ending = available_format

                            new_segment_name = f'seg_{i}.' + determined_ending
                            new_segment_file = os.path.join(temp_folder, new_segment_name)
                            # Move it to a new name
                            shutil.move(segment_file, new_segment_file)
                            self.trace(f'Segment {segment_name} is actually {determined_ending}')
                            segment_name = new_segment_name

                            last_good_segment = new_segment_file
                            last_determined_ending = determined_ending

                            if valid_format:
                                made_lines.append(line)
                                made_lines.append(segment_name)
                        else:
                            if last_good_segment is not None and not has_key:
                                new_segment_name = f'seg_{i}.' + last_determined_ending
                                new_segment_file = os.path.join(temp_folder, new_segment_name)
                                last_w, last_h, codec = get_video_params(last_good_segment)
                                if last_w is not None and last_h is not None:
                                    duration = float(line.split(":")[1].split(",")[0])
                                    make_blank_segment(new_segment_file, duration, last_w, last_h, self)
                                    if os.path.exists(new_segment_file):
                                        made_lines.append(line)
                                        made_lines.append(segment_name)
                                    else:
                                        self.debug(f'Could not generate segment for {segment_name}')
                                else:
                                    self.debug(f'Could not determine dimensions for {segment_name}')
                            else:
                                self.debug(f'{segment_name} is missing 404')

                    i += 2
                else:
                    made_lines.append(line)
                    i += 1

            with open(made_m3u8_file, "w") as f:
                for line in made_lines:
                    f.write(line + "\n")

            arguments = ['ffmpeg', '-allowed_extensions', 'ALL', '-nostdin', '-i', made_m3u8_file, '-c', 'copy',
                         temp_file]

            if self.can_trace():
                command_str = shlex.join(arguments)
                self.trace(command_str)

            # Run the program with the provided arguments
            process = subprocess.Popen(arguments, cwd=temp_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Wait for the process to finish
            stdout, stderr = process.communicate()  # Capture the output and error streams

            return_code = str(process.returncode)

            if return_code == '0' and os.path.exists(temp_file) and os.path.isfile(temp_file):

                # Get file size
                file_size = os.path.getsize(temp_file)

                if file_size > 0:

                    self.info(f'Found file with size {file_size}')

                    # Get created time and convert to readable format
                    created_time = os.path.getctime(temp_file)
                    created_datetime = datetime.fromtimestamp(created_time)

                    mime_type = 'video/mp4'  # MIME type

                    new_file = insert_file(source_row.id, self.filename, mime_type, is_archive, False, file_size,
                                           created_datetime, db_session)

                    dest_path = get_data_for_mediafile(new_file, self.primary_path, self.archive_path)

                    shutil.move(str(temp_file), str(dest_path))

                    self.set_worked()
                    self.set_finished()
                else:
                    self.set_failure()
                    self.error("Could not find MP4 file (0 len)")
            else:
                self.error(f'Return Code {return_code}')

                error_text = stderr.decode('utf-8')
                self.error(error_text)

                self.set_failure()

                # Wait a bit, so we can check
                sleep(35)
