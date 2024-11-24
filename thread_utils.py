import inspect
import sys
import threading
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone


def get_caller_info():
    """
    Get the filename and line number of the caller.

    Returns:
        tuple: A tuple containing the filename and line number of the caller.
    """
    frame = inspect.currentframe()
    caller_frame = frame.f_back.f_back
    filename = caller_frame.f_code.co_filename
    line_number = caller_frame.f_lineno
    return filename, line_number


class TaskManager:
    """
    Manages a list of tasks with thread-safe operations.
    """

    def __init__(self):
        self.task_list = []
        self.lock = threading.Lock()

    def add_task(self, task_wrapper):
        """
        Add a task to the task list.

        Args:
            task_wrapper (TaskWrapper): The task to be added.
        """
        with self.lock:
            self.task_list.append(task_wrapper)

    def has_task(self, task_name: str, task_description: str) ->bool:
        """
        Check if there is an item in the QUEUE that already matches and isn't complete
        :param task_name:
        :param task_description:
        :return: True if the task exists and isn't finished
        """
        with self.lock:
            for task in self.task_list:
                if task.name == task_name and task.description == task_description and not task.is_finished:
                    return True
        return False


    def get_all_tasks(self):
        """
        Get all tasks in the task list.

        Returns:
            tuple: A tuple containing all tasks.
        """
        with self.lock:
            return tuple(self.task_list)

    def remove_task_by_id(self, task_id):
        """
        Remove a task from the task list by its ID.

        Args:
            task_id (int): The ID of the task to be removed.

        Returns:
            bool: True if the task was removed, False otherwise.
        """
        with self.lock:
            for task in self.task_list:
                if task.task_id == task_id:
                    self.task_list.remove(task)
                    return True
            return False

    def move_task_to_top(self, task_id):
        """
        Move a task to the top of the task list by its ID.

        Args:
            task_id (int): The ID of the task to be moved.

        Returns:
            bool: True if the task was moved, False otherwise.
        """
        with self.lock:
            for task in self.task_list:
                if task.task_id == task_id:
                    self.task_list.remove(task)
                    self.task_list.insert(0, task)
                    return True
            return False


class TaskWrapper(ABC):
    """
    Abstract base class for task wrappers, providing logging and task management functionalities.
    """
    TRACE = 0
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50
    ALWAYS = 100

    task_id_counter = 0
    task_id_lock = threading.Lock()

    def __init__(self, name, description):
        with TaskWrapper.task_id_lock:
            TaskWrapper.task_id_counter += 1
            self.task_id = TaskWrapper.task_id_counter
        self.name = name
        self.description = description
        self.progress = 0
        self.percent = 0
        self.is_finished = False
        self.is_waiting = True
        self.is_failure = False
        self.is_worked = False
        self.is_warning = False
        self.is_cancelled = False
        self.log_entries = []
        self.token = Token()
        self.logging_level = self.INFO
        self.init_time = datetime.now(timezone.utc)
        self.start_time = None
        self.end_time = None
        self.user = None

    def mark_start(self):
        self.start_time = datetime.now(timezone.utc)

    def mark_end(self):
        self.end_time = datetime.now(timezone.utc)

    @property
    def init_timestamp(self):
        if self.init_time is not None:
            return self.init_time.strftime("%Y-%m-%d %H:%M:%S")
        return ""

    @property
    def start_timestamp(self):
        if self.start_time is not None:
            return self.start_time.strftime("%Y-%m-%d %H:%M:%S")
        return ""

    @property
    def end_timestamp(self):
        if self.end_time is not None:
            return self.end_time.strftime("%Y-%m-%d %H:%M:%S")
        return ""

    @property
    def duration_delayed(self):
        # If start_time is None, calculate duration to the current time
        current_time = self.start_time or datetime.now(timezone.utc)
        diff = current_time - self.init_time
        return int(diff.total_seconds())

    @property
    def duration_running(self):
        # If start_time is None, return -1; otherwise calculate to end_time or current time
        if not self.start_time:
            return -1
        current_time = self.end_time or datetime.now(timezone.utc)
        diff = current_time - self.start_time
        return int(diff.total_seconds())

    @property
    def duration_total(self):
        # Calculate duration from init_time to end_time or current time
        current_time = self.end_time or datetime.now(timezone.utc)
        diff = current_time - self.init_time
        return int(diff.total_seconds())

    def update_logging_level(self, logging_level: int):
        """
        Update the logging level.

        Args:
            logging_level (int): The new logging level.
        """
        if logging_level % 10 == 0 and 0 <= logging_level <= 50:
            self.logging_level = logging_level

    def update_user(self, user):
        self.user = user

    def update_progress(self, value: float):
        """
        Update the progress percentage.

        Args:
            value (float): The new progress percentage.
        """
        self.progress = value

    def update_percent(self, value: float):
        """
        Update the sub-progress percentage.

        Args:
            value (float): The new sub-progress percentage.
        """
        self.percent = value

    def set_finished(self, value: bool = True):
        """
        Set the task as finished.

        Args:
            value (bool): True if the task is finished, False otherwise.
        """
        self.is_finished = value

    def set_waiting(self, value: bool = True):
        """
        Set the task as waiting.

        Args:
            value (bool): True if the task is waiting, False otherwise.
        """
        self.is_waiting = value

    def set_failure(self, value: bool = True):
        """
        Set the task as failed.

        Args:
            value (bool): True if the task has failed, False otherwise.
        """
        self.is_failure = value

    def set_warning(self, value: bool = True):
        """
        Set the task as having a warning.

        Args:
            value (bool): True if the task has a warning, False otherwise.
        """
        self.is_warning = value

    def set_worked(self, value: bool = True):
        """
        Set the task as worked.

        Args:
            value (bool): True if the task has worked, False otherwise.
        """
        self.is_worked = value

    def cancel(self):
        """
        Cancel the task.
        """
        self.is_cancelled = True
        self.token.set_stop()

    def critical(self, *args):
        """
        Log a critical message.

        Args:
            *args: The message to be logged.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        call_filename, call_line_number = get_caller_info()
        self._add_log(self.CRITICAL, f"file: {call_filename}, line: {call_line_number}, message: {log_message}")

    def error(self, *args):
        """
        Log an error message.

        Args:
            *args: The message to be logged.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        call_filename, call_line_number = get_caller_info()
        self._add_log(self.ERROR, f"file: {call_filename}, line: {call_line_number}, message: {log_message}")

    def warn(self, *args):
        """
        Log a warning message.

        Args:
            *args: The message to be logged.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        self._add_log(self.WARNING, log_message)

    def info(self, *args):
        """
        Log an info message.

        Args:
            *args: The message to be logged.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        self._add_log(self.INFO, log_message)

    def always(self, *args):
        """
        Log a message that is always logged regardless of the logging level.

        Args:
            *args: The message to be logged.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        self._add_log(self.ALWAYS, log_message)

    def debug(self, *args):
        """
        Log a debug message.

        Args:
            *args: The message to be logged.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        self._add_log(self.DEBUG, log_message)

    def trace(self, *args):
        """
        Log a trace message.

        Args:
            *args: The message to be logged.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        self._add_log(self.TRACE, log_message)

    def add_log(self, *args):
        """
        Add a log message with the ALWAYS severity.

        Args:
            *args: The message to be logged.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        self._add_log(self.ALWAYS, log_message)

    def _add_log(self, severity, log_message):
        """
        Add a log message with a specific severity.

        Args:
            severity (int): The severity level of the log message.
            log_message (str): The log message.
        """
        if severity >= self.logging_level or severity == self.ALWAYS:
            current_datetime = datetime.now()
            human_readable_timestamp = current_datetime.strftime("%Y-%m-%d %H:%M:%S")
            self.log_entries.append({"s": severity, "time": human_readable_timestamp, "text": log_message})

    def can_debug(self):
        """
        Check if debug messages can be logged.

        Returns:
            bool: True if debug messages can be logged, False otherwise.
        """
        return self.DEBUG >= self.logging_level

    def can_trace(self):
        """
        Check if trace messages can be logged.

        Returns:
            bool: True if trace messages can be logged, False otherwise.
        """
        return self.TRACE >= self.logging_level

    @abstractmethod
    def run(self, db_session):
        """
        Abstract method to be implemented by subclasses to define the task's behavior.
        :param db_session:
        """
        pass


class NoOpTaskWrapper(TaskWrapper):
    """
    A no-operation task wrapper for testing and default purposes.
    """

    def __init__(self):
        super().__init__('No Op', 'No Op')

    def add_log(self, message: str):
        """
        Override the add_log method to print the message.

        Args:
            message (str): The message to be logged.
        """
        print(message)

    def run(self, db_session):
        """
        Override the run method to do nothing.
        :param db_session:
        """
        pass


class Token:
    """
    A token to signal task cancellation.
    """

    def __init__(self):
        self.should_stop = False

    def set_stop(self):
        """
        Set the stop signal.
        """
        self.should_stop = True


def get_exception():
    """
    Get the current exception information.

    Returns:
        dict: A dictionary containing the exception message, line number, file, and traceback.
    """
    exc_type, exc_value, exc_traceback = sys.exc_info()
    trace = traceback.format_exception(exc_type, exc_value, exc_traceback)
    exception_info = {
        "message": str(exc_value),
        "line": exc_traceback.tb_lineno if exc_traceback else None,
        "file": exc_traceback.tb_frame.f_code.co_filename if exc_traceback else None,
        "traceback": trace
    }
    return exception_info
