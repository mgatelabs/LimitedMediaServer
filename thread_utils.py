import inspect
import sys
import threading
import time
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from queue import PriorityQueue
from typing import Optional
import json

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

class TaskWorker:

    def __init__(self, index):
        self.index = index
        self.online = True
        self.position = 0
        self.job = 0
        self.wait_stamp = 0

class TaskManager:
    """
    Manages a list of tasks with thread-safe operations.
    """

    def __init__(self, max_capacity=100):

        self.known_workers: list[TaskWorker] = []

        self.task_queue = PriorityQueue()
        self.task_lookup: dict[int, TaskWrapper] = {}  # Map task IDs to task objects
        self.lock = threading.Lock()
        self.running_tasks: dict[int, TaskWrapper] = {}  # Store running tasks
        self.finished_tasks: dict[int, TaskWrapper] = {}  # Store finished tasks
        self.max_capacity = max_capacity  # Total capacity
        self.current_capacity = 0  # Capacity currently in use

    def get_worker_status(self):
        result = []
        for worker in self.known_workers:
            result.append({'index': worker.index,'online': worker.online,'position': worker.position,'job': worker.job})
        return result

    def add_worker(self, index: int) -> TaskWorker:
        new_worker = TaskWorker(index)
        self.known_workers.append(new_worker)
        return new_worker

    def add_task(self, task: 'TaskWrapper'):
        with self.lock:
            self.task_lookup[task.task_id] = task
            self.task_queue.put(task)

    def adjust_priority(self, task_id, new_priority) -> bool:
        with self.lock:
            if task_id in self.task_lookup:
                task = self.task_lookup.pop(task_id)
                task.priority = new_priority
                self.task_lookup[task.task_id] = task
                self._rebuild_queue()
                task.info(f"Priority adjusted to {new_priority}")
                return True
        return False

    def _rebuild_queue(self):
        # Clear and rebuild the priority queue with updated priorities
        items = list(self.task_lookup.values())
        while not self.task_queue.empty():
            self.task_queue.get()
        for item in items:
            self.task_queue.put(item)

    def get_task_queue(self):
        """
        Retrieve a task from the queue with strict priority group enforcement.
        Only tasks matching the first task's priority will be considered for execution.
        """
        with self.lock:
            # Skip it, no capacity
            if self.current_capacity >= self.max_capacity:
                return None

            if self.task_queue.empty():
                return None  # No tasks left

            temp_queue = []  # Temporary storage for tasks that can't run
            eligible_tasks = []  # Tasks eligible to run (same priority group)

            # Step 1: Identify the priority group
            first_task = self.task_queue.get()
            temp_queue.append(first_task)  # Hold the first task temporarily

            target_priority = first_task.priority

            # Step 2: Collect all tasks with the same priority
            while not self.task_queue.empty():
                task = self.task_queue.get()
                if task.priority == target_priority:
                    eligible_tasks.append(task)
                else:
                    temp_queue.append(task)

            # Step 3: Check eligible tasks for capacity
            for task in [first_task] + eligible_tasks:
                if task.weight + self.current_capacity <= self.max_capacity:

                    # Put back skipped tasks
                    for skipped_task in temp_queue + eligible_tasks:
                        if skipped_task.task_id != task.task_id:  # Don't re-add the running task
                            self.task_queue.put(skipped_task)

                    self.running_tasks[task.task_id] = task
                    self._update_weights()

                    return task

            # Step 4: No eligible task could run, put everything back
            for skipped_task in temp_queue + eligible_tasks:
                self.task_queue.put(skipped_task)

            return None  # No task could fit in the current capacity

    def _update_weights(self):
        calculated_weight = 0
        for running_task in self.running_tasks.values():
            calculated_weight = calculated_weight + running_task.weight

        self.current_capacity = calculated_weight

    def task_done_queue(self, task: 'TaskWrapper', worker_status: TaskWorker):
        worker_status.position = 88
        time.sleep(0.001)
        with self.lock:
            time.sleep(0.1)
            worker_status.position = 89
            if task.task_id in self.task_lookup:
                self.finished_tasks[task.task_id] = task
                del self.task_lookup[task.task_id]
            worker_status.position = 90
            if task.task_id in self.running_tasks:
                del self.running_tasks[task.task_id]
            worker_status.position = 91
            self._update_weights()
            worker_status.position = 92
            self.task_queue.task_done()

    def get_finished_tasks(self):
        with self.lock:
            return list(self.finished_tasks.values())

    def clear_finished_tasks(self):
        with self.lock:
            self.finished_tasks.clear()
            print("Finished tasks cleared.")

    def has_task(self, task_name: str, task_description: str) -> bool:
        """
        Check if there is an item in the QUEUE that already matches and isn't complete
        :param task_name:
        :param task_description:
        :return: True if the task exists and isn't finished
        """
        with self.lock:
            for task in self.task_lookup.values():
                if task.name == task_name and task.description == task_description and not task.is_finished:
                    return True
        return False

    def get_task_by_id(self, task_id: int) -> Optional['TaskWrapper']:
        with self.lock:
            if task_id in self.task_lookup:
                return self.task_lookup[task_id]
            if task_id in self.finished_tasks:
                return self.finished_tasks[task_id]
            return None

    def remove_dead_tasks(self) -> int:
        """
        Remove dead tasks
        :return: Number of removed tasks
        """
        with self.lock:
            before = len(self.known_workers)
            self.known_workers = [
                known for known in self.known_workers
                if not (known.position == 72 and 0 < known.wait_stamp < time.time() - 5)
            ]
            removed = before - len(self.known_workers)
        return removed

    def get_all_tasks(self) -> list['TaskWrapper']:
        """
        Get all tasks in the task list.

        Returns:
            tuple: A tuple containing all tasks.
        """
        with self.lock:
            # Combine tasks from both finished and pending
            all_tasks = list(self.finished_tasks.values()) + list(self.task_lookup.values())

            # Sort by task_id to maintain submission order
            return sorted(all_tasks, key=lambda task: task.task_id)

    def get_weight(self) -> int:
        return self.current_capacity


    def clean_tasks(self, hard_clean: bool = True) -> int:

        with self.lock:

            to_remove = []

            for task in self.finished_tasks.values():
                if hard_clean:
                    to_remove.append(task.task_id)
                elif not hard_clean and task.is_warning == False and task.is_failure == False and task.is_finished and not task.is_worked:
                    to_remove.append(task.task_id)

            for task_id in to_remove:
                del self.finished_tasks[task_id]

            return len(to_remove)

LOGGING_LEVEL_NAMES = {
    0: "TRACE",
    10: "DEBUG",
    20: "INFO",
    30: "WARN",
    40: "ERROR",
    50: "CRIT",
    100: "ALWAY"
}

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

    def __init__(self, name, description, priority: int = 5, weight: int = 1):
        with TaskWrapper.task_id_lock:
            TaskWrapper.task_id_counter += 1
            self.task_id = TaskWrapper.task_id_counter
        self.priority = priority
        self.weight = weight
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
        self.post_task = None
        self.ref_book_id = ''
        self.ref_folder_id = ''

    def __lt__(self, other: 'TaskWrapper'):
        # Compare by priority, then by ID to maintain order
        return (self.priority, self.task_id) < (other.priority, other.task_id)

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

    def run_after(self, task: 'TaskWrapper'):
        self.post_task = task

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

    def _add_log(self, severity, log_message):
        print(f'{LOGGING_LEVEL_NAMES[severity]}-{log_message}')

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
