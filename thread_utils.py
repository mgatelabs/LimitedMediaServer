import inspect
import logging
import os
import sys
import threading
import time
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from queue import PriorityQueue
from typing import Optional

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

WORKER_NAMES = [
    'Alan', 'Barry', 'Carl', 'Dean', 'Eddie', 'Frank', 'Gary', 'Harry',
    'Ivan', 'Jack', 'Kevin', 'Larry', 'Mick', 'Neil', 'Oscar', 'Peter',
    'Quinn', 'Ringo', 'Steve', 'Terry', 'Ulric', 'Vince', 'Wayne', 'Xavier',
    'Yogi', 'Ziggy', 'Bruce', 'Clive', 'Derek', 'Ellis', 'Floyd', 'Grant',
]


class TaskWorker:

    STATUS_IDLE = 'idle'
    STATUS_RUNNING = 'running'
    STATUS_WAITING = 'waiting'
    STATUS_DEAD = 'dead'

    def __init__(self, index, name):
        self.index = index
        self.name = name
        self.status = self.STATUS_IDLE
        self.job = 0
        self.created = time.time()
        self.last_seen = time.time()
        self.lock_key = None

class TaskManager:
    """
    Manages a list of tasks with thread-safe operations.
    """

    def __init__(self, key_lock_manager=None, max_capacity=100):

        self.known_workers: list[TaskWorker] = []
        self.key_lock_manager = key_lock_manager

        self.task_queue = PriorityQueue()
        self.task_lookup: dict[int, TaskWrapper] = {}  # Map task IDs to task objects
        self.lock = threading.Lock()
        self.running_tasks: dict[int, TaskWrapper] = {}  # Store running tasks
        self.finished_tasks: dict[int, TaskWrapper] = {}  # Store finished tasks
        self.max_capacity = max_capacity  # Total capacity
        self.current_capacity = 0  # Capacity currently in use

    def get_worker_status(self):
        now = time.time()
        result = []
        with self.lock:
            for worker in self.known_workers:
                task = self.running_tasks.get(worker.job)
                result.append({
                    'index': worker.index,
                    'name': worker.name,
                    'status': worker.status,
                    'job': worker.job,
                    'job_name': task.name if task else None,
                    'job_description': task.description if task else None,
                    'last_seen': worker.last_seen,
                    'uptime': int(now - worker.created),
                })
        return result

    def _pick_worker_name(self) -> str:
        active_names = [w.name for w in self.known_workers]
        counts: dict[str, int] = {}
        for name in active_names:
            base = name.rsplit(' ', 1)[0]
            counts[base] = counts.get(base, 0) + 1

        for base in WORKER_NAMES:
            if base not in counts:
                return base

        # All 32 names taken — append a generation number
        min_base = min(WORKER_NAMES, key=lambda b: counts.get(b, 0))
        return f'{min_base} {counts.get(min_base, 0) + 1}'

    def add_worker(self, index: int) -> TaskWorker:
        with self.lock:
            name = self._pick_worker_name()
            new_worker = TaskWorker(index, name)
            self.known_workers.append(new_worker)
        return new_worker

    def add_task(self, task: 'TaskWrapper'):
        with self.lock:
            self.task_lookup[task.task_id] = task
            self.task_queue.put(task)

    def adjust_priority(self, task_id, new_priority) -> bool:
        with self.lock:
            if task_id in self.task_lookup:
                task = self.task_lookup[task_id]
                task.priority = new_priority
                self._rebuild_queue()
                task.info(f"Priority adjusted to {new_priority}")
                return True
        return False

    def _rebuild_queue(self):
        new_queue = PriorityQueue()
        for item in self.task_lookup.values():
            new_queue.put(item)
        self.task_queue = new_queue

    def return_task_to_queue(self, task):
        """
        Return a previously running task back into the queue.
        This is used when a processor is not ready to execute.
        """
        with self.lock:
            if task.task_id not in self.running_tasks:
                return

            del self.running_tasks[task.task_id]
            self._update_weights()
            task.retry_seq += 1
            self.task_lookup[task.task_id] = task
            self.task_queue.put(task)

    def get_task_queue(self):
        """
        Retrieve the highest-priority task that can run right now.

        Weight-blocked top task → block the queue (return None), preserving
        capacity-fill semantics for high-weight barrier tasks.
        Lock-blocked tasks → skip past them so other workers stay busy.
        """
        with self.lock:
            if self.current_capacity >= self.max_capacity:
                return None

            if self.task_queue.empty():
                return None

            # Peek at the top task first for weight check
            top = self.task_queue.get()

            if top.weight + self.current_capacity > self.max_capacity:
                # Top task can't fit — block; nothing else should run ahead of it
                self.task_queue.put(top)
                return None

            # Top task fits on capacity. Now check its lock.
            # If unlocked, take it immediately.
            klm = self.key_lock_manager
            if klm is None or klm.acquire(top.get_locking_key()):
                del self.task_lookup[top.task_id]
                self.running_tasks[top.task_id] = top
                self._update_weights()
                return top

            # Top task is lock-blocked. Scan the rest for a runnable alternative.
            skipped = [top]
            chosen = None

            while not self.task_queue.empty():
                task = self.task_queue.get()

                if task.weight + self.current_capacity > self.max_capacity:
                    # This and everything behind it may also be too heavy; put back and stop
                    skipped.append(task)
                    break

                if klm is None or klm.acquire(task.get_locking_key()):
                    chosen = task
                    break

                skipped.append(task)

            # Restore all skipped tasks
            for s in skipped:
                self.task_queue.put(s)

            if chosen is not None:
                del self.task_lookup[chosen.task_id]
                self.running_tasks[chosen.task_id] = chosen
                self._update_weights()
                return chosen

            return None

    def _update_weights(self):
        self.current_capacity = sum(t.weight for t in self.running_tasks.values())

    def task_done_queue(self, task: 'TaskWrapper', worker_status: TaskWorker):
        time.sleep(0.001)
        with self.lock:
            time.sleep(0.1)
            self.finished_tasks[task.task_id] = task
            self.task_lookup.pop(task.task_id, None)
            self.running_tasks.pop(task.task_id, None)
            self._update_weights()
        if self.key_lock_manager is not None:
            self.key_lock_manager.release(task.get_locking_key())

    def get_finished_tasks(self):
        with self.lock:
            return list(self.finished_tasks.values())

    def clear_finished_tasks(self):
        with self.lock:
            self.finished_tasks.clear()
            print("Finished tasks cleared.")

    def has_task(self, task_name: str, task_description: str) -> bool:
        with self.lock:
            for store in (self.task_lookup, self.running_tasks):
                for task in store.values():
                    if task.name == task_name and task.description == task_description and not task.is_finished:
                        return True
        return False

    def get_task_by_id(self, task_id: int) -> Optional['TaskWrapper']:
        with self.lock:
            if task_id in self.task_lookup:
                return self.task_lookup[task_id]
            if task_id in self.running_tasks:
                return self.running_tasks[task_id]
            if task_id in self.finished_tasks:
                return self.finished_tasks[task_id]
            return None

    def remove_dead_tasks(self) -> int:
        """
        Remove dead tasks
        :return: Number of removed tasks
        """
        stale_threshold = time.time() - 30
        with self.lock:
            before = len(self.known_workers)
            self.known_workers = [
                w for w in self.known_workers
                if not (w.status == TaskWorker.STATUS_IDLE and w.last_seen < stale_threshold)
            ]
            removed = before - len(self.known_workers)
        return removed

    def get_all_tasks(self) -> list['TaskWrapper']:
        with self.lock:
            all_tasks = (
                list(self.finished_tasks.values()) +
                list(self.running_tasks.values()) +
                list(self.task_lookup.values())
            )
            return sorted(all_tasks, key=lambda task: task.task_id)

    def get_weight(self) -> int:
        return self.current_capacity


    def purge_task(self, task_id: int) -> bool:
        with self.lock:
            if task_id in self.finished_tasks:
                del self.finished_tasks[task_id]
                return True
            if task_id in self.task_lookup:
                del self.task_lookup[task_id]
                self._rebuild_queue()
                return True
        return False

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
        self.retry_seq = 0
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
        self.ref_folder_name = ''
        self.ref_folder_preview = False
        self._lock_key = None
        self.temp_folder_path = None
        self.expected_files_count = -1
        self.expected_files_as_progress = False

    def __lt__(self, other: 'TaskWrapper'):
        return (self.priority, self.retry_seq, self.task_id) < (
            other.priority,
            other.retry_seq,
            other.task_id
        )

    def set_locking_key(self, key):
        self._lock_key = key

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

    def get_progress(self):
        if (self.expected_files_as_progress
                and self.expected_files_count > 0
                and self.temp_folder_path is not None
                and os.path.exists(self.temp_folder_path)):
            file_count = len(os.listdir(self.temp_folder_path))
            return (file_count / self.expected_files_count) * 100
        # Revert to basic value
        return self.progress

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

    def critical(self, *args, _markdown=False, _json=False):
        """
        Log a critical message.

        Args:
            *args: The message to be logged.
            _markdown (bool): Whether the message is in Markdown format.
            _json (bool): Whether the message is in JSON format.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        call_filename, call_line_number = get_caller_info()
        self._add_log(self.CRITICAL, f"file: {call_filename}, line: {call_line_number}, message: {log_message}", _markdown, _json)

    def error(self, *args, _markdown=False, _json=False):
        """
        Log an error message.

        Args:
            *args: The message to be logged.
            _markdown (bool): Whether the message is in Markdown format.
            _json (bool): Whether the message is in JSON format.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        call_filename, call_line_number = get_caller_info()
        self._add_log(self.ERROR, f"file: {call_filename}, line: {call_line_number}, message: {log_message}", _markdown, _json)

    def warn(self, *args, _markdown=False, _json=False):
        """
        Log a warning message.

        Args:
            *args: The message to be logged.
            _markdown (bool): Whether the message is in Markdown format.
            _json (bool): Whether the message is in JSON format.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        self._add_log(self.WARNING, log_message, _markdown, _json)

    def info(self, *args, _markdown=False, _json=False):
        """
        Log an info message.

        Args:
            *args: The message to be logged.
            _markdown (bool): Whether the message is in Markdown format.
            _json (bool): Whether the message is in JSON format.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        self._add_log(self.INFO, log_message, _markdown, _json)

    def always(self, *args, _markdown=False, _json=False):
        """
        Log a message that is always logged regardless of the logging level.

        Args:
            *args: The message to be logged.
            _markdown (bool): Whether the message is in Markdown format.
            _json (bool): Whether the message is in JSON format.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        self._add_log(self.ALWAYS, log_message, _markdown, _json)

    def debug(self, *args, _markdown=False, _json=False):
        """
        Log a debug message.

        Args:
            *args: The message to be logged.
            _markdown (bool): Whether the message is in Markdown format.
            _json (bool): Whether the message is in JSON format.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        self._add_log(self.DEBUG, log_message, _markdown, _json)

    def trace(self, *args, _markdown=False, _json=False):
        """
        Log a trace message.

        Args:
            *args: The message to be logged.
            _markdown (bool): Whether the message is in Markdown format.
            _json (bool): Whether the message is in JSON format.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        self._add_log(self.TRACE, log_message, _markdown, _json)

    def add_log(self, *args, _markdown=False, _json=False):
        """
        Add a log message with the ALWAYS severity.

        Args:
            *args: The message to be logged.
            _markdown (bool): Whether the message is in Markdown format.
            _json (bool): Whether the message is in JSON format.
        """
        if all(arg is None for arg in args):
            return
        log_message = ' '.join(map(str, args))
        self._add_log(self.ALWAYS, log_message, _markdown, _json)

    def _add_log(self, severity, log_message, _markdown=False, _json=False):
        """
        Add a log message with a specific severity.

        Args:
            severity (int): The severity level of the log message.
            log_message (str): The log message.
            _markdown (bool): Whether the message is in Markdown format.
            _json (bool): Whether the message is in JSON format.
        """
        # If it is TRACE, also dump to the logging stream
        if self.logging_level == severity == self.TRACE:
            logging.info(log_message)

        if severity >= self.logging_level or severity == self.ALWAYS:
            current_datetime = datetime.now()
            human_readable_timestamp = current_datetime.strftime("%Y-%m-%d %H:%M:%S")
            fmt = "json" if _json else ("md" if _markdown else "txt")
            self.log_entries.append({"s": severity, "time": human_readable_timestamp, "text": log_message, "fmt": fmt})

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

    def get_locking_key(self) -> str:
        return self._lock_key

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

    def _add_log(self, severity, log_message, _markdown=False, _json=False):
        print(f'{LOGGING_LEVEL_NAMES[severity]}-{log_message}')

    def run(self, db_session):
        """
        Override the run method to do nothing.
        :param db_session:
        """
        pass


class RunReport(TaskWrapper):
    """
    A task whose only purpose is to replay a pre-built list of log messages and
    set the appropriate status flags.  Useful when job-building logic needs to
    surface warnings or errors back to the task queue without doing real work.

    Usage:
        report = RunReport("Import Report", "Tracker import summary")
        report.add_warn("Group S01E01: no folder found, skipped")
        report.add_error("Group S01E02: invalid URL, skipped")
        jobs.append(report)
    """

    # Severity constants mirror TaskWrapper
    _WARN = TaskWrapper.WARNING
    _ERROR = TaskWrapper.ERROR

    def __init__(self, name: str, description: str):
        super().__init__(name, description)
        self._entries: list[tuple[int, str]] = []  # (severity, message)

    def add_info(self, message: str) -> 'RunReport':
        self._entries.append((TaskWrapper.INFO, message))
        return self

    def add_warn(self, message: str) -> 'RunReport':
        self._entries.append((TaskWrapper.WARNING, message))
        return self

    def add_error(self, message: str) -> 'RunReport':
        self._entries.append((TaskWrapper.ERROR, message))
        return self

    def has_entries(self) -> bool:
        return bool(self._entries)

    def run(self, db_session):
        has_error = False
        has_warn = False

        for severity, message in self._entries:
            if severity == TaskWrapper.ERROR:
                self.error(message)
                has_error = True
            elif severity == TaskWrapper.WARNING:
                self.warn(message)
                has_warn = True
            else:
                self.info(message)

        if has_error:
            self.set_failure()
        elif has_warn:
            self.set_warning()
        else:
            self.set_worked()


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
