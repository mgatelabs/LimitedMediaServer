import random
import time

from thread_utils import TaskWrapper


def random_sleep(max_duration: int = 5, min_duration=1, logger: TaskWrapper = None):
    """
    Make the program sleep for a random duration between 1 and max_duration seconds.
    """
    # Make sure the limit is OK
    if max_duration < 2:
        max_duration = 2
    # Calculate the duration
    sleep_duration = random.randint(min_duration, max_duration)
    time.sleep(sleep_duration)
    if logger is not None and logger.can_trace():
        logger.trace(f"Slept for {sleep_duration} seconds.")
