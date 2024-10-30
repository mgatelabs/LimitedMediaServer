import random
import time

from thread_utils import TaskWrapper


def random_sleep(logger: TaskWrapper = None):
    """
    Make the program sleep for a random duration between 1 and 5 seconds.
    """
    sleep_duration = random.randint(1, 5)
    time.sleep(sleep_duration)
    if logger is not None and logger.can_trace():
        logger.trace(f"Slept for {sleep_duration} seconds.")


def random_sleep_fast(logger: TaskWrapper = None):
    """
    Make the program sleep for a random duration between 1 and 5 seconds.
    """
    sleep_duration = random.randint(1, 3)
    time.sleep(sleep_duration)
    if logger is not None and logger.can_trace():
        logger.trace(f"Fast slept for {sleep_duration} seconds.")
