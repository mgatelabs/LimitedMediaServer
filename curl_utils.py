import subprocess
import platform
import urllib
from typing import Optional

from thread_utils import TaskWrapper, NoOpTaskWrapper

"""
This includes utility methods which will call a special version of CURL, that emulates Chrome
"""

def custom_curl_get(url, headers=None, download_file=None, task_wrapper:TaskWrapper = NoOpTaskWrapper(), insecure: bool = False):
    """
    This is to call the custom CHROM based CURL as a GET command
    :param url:
    :param headers:
    :param download_file:
    :param task_wrapper:
    :return:
    """
    if platform.system() != 'Linux':
        print("This function can only run on a Linux-based device.")
        return False

    command = ['curl_chrome116', url, '-L', '--max-redirs', '5']
    if headers:
        for key, value in headers.items():
            command.extend(['-H', f'{key}: {value}'])

    if download_file:
        command.extend(['-o', download_file])

    if insecure:
        command.extend(['-k'])

    if task_wrapper.can_trace():
        task_wrapper.trace("' '".join(command))

    try:

        if task_wrapper.can_trace():
            result = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            output_normal = result.stdout.decode('utf-8')
            output_error = result.stderr.decode('utf-8')

            task_wrapper.trace(f'Output: {output_normal}')
            task_wrapper.trace(f'Error: {output_error}')
            task_wrapper.trace(f'Return Code: {result.returncode}')
        else:
            subprocess.run(command, check=True)

        return True
    except subprocess.CalledProcessError as e:
        task_wrapper.set_failure()
        task_wrapper.error(f"Error: {e}")
        return False

def custom_curl_headers(url, headers=None, download_file=None, task_wrapper:TaskWrapper = NoOpTaskWrapper()):
    """
    This is to call the custom CHROM based CURL as a GET command
    :param url:
    :param headers:
    :param download_file:
    :param task_wrapper:
    :return:
    """
    if platform.system() != 'Linux':
        print("This function can only run on a Linux-based device.")
        return False

    command = ['curl_chrome116', url, '-I', '-L', '--max-redirs', '5']
    if headers:
        for key, value in headers.items():
            command.extend(['-H', f'{key}: {value}'])

    if download_file:
        command.extend(['-o', download_file])

    if task_wrapper.can_trace():
        task_wrapper.trace(" ".join(command))

    try:

        if task_wrapper.can_trace():
            result = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            output_normal = result.stdout.decode('utf-8')
            output_error = result.stderr.decode('utf-8')

            task_wrapper.trace(f'Output: {output_normal}')
            task_wrapper.trace(f'Error: {output_error}')
            task_wrapper.trace(f'Return Code: {result.returncode}')
        else:
            subprocess.run(command, check=True)

        return True
    except subprocess.CalledProcessError as e:
        task_wrapper.set_failure()
        task_wrapper.error(f"Error: {e}")
        return False


def dict_to_urlencoded(data: dict) -> str:
    return urllib.parse.urlencode(data)


def custom_curl_post(url, data: Optional[dict[str, str]], headers=None, download_file=None, task_logger:TaskWrapper=None):
    """
    This is to call the custom CHROM based CURL as a POST command
    :param url:
    :param data:
    :param headers:
    :param download_file:
    :param task_logger:
    :return:
    """
    if platform.system() != 'Linux':
        print("This function can only run on a Linux-based device.")
        return False

    command = ['curl_chrome116', url, '-L', '--max-redirs', '5']
    if headers:
        for key, value in headers.items():
            command.extend(['-H', f'{key}: {value}'])
    command.extend(['-H', f'Content-Type: application/x-www-form-urlencoded; charset=UTF-8'])

    command.extend(['-X', 'POST'])
    if data is not None:
        command.extend(['-d', dict_to_urlencoded(data)])

    if download_file:
        command.extend(['-o', download_file])

    try:
        subprocess.run(command, check=True)
        print("Download successful.")
        return True
    except subprocess.CalledProcessError as e:
        if task_logger is not None:
            task_logger.error(str(e))
        else:
            print(f"Error: {e}")
        return False

def read_temp_file(temp_file_path):
    try:
        with open(temp_file_path, 'r') as temp_file:
            file_content = temp_file.read()
            return file_content
    except IOError as e:
        print(f"Error: {e}")
        return None