import io
import json
import logging
import os
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from math import floor, ceil

from flask import Blueprint, request, current_app, send_file
from sqlalchemy.orm import sessionmaker, Session

from auth_utils import shall_authenticate_user, feature_required, feature_required_silent, get_username, get_uid, \
    get_user_features
from common_utils import generate_failure_response, generate_success_response
from constants import MAX_WORKERS
from db import db
from feature_flags import MANAGE_PROCESSES, VIEW_PROCESSES, MANAGE_APP
from key_lock_manager import KeyLockManager
from messages import msg_invalid_parameter, msg_tasks_started, msg_action_cancelled_duplicate_task, \
    msg_missing_parameter, msg_action_failed, msg_operation_complete, msg_action_failed_missing, msg_removed_x_items, \
    msg_found_x_results, msg_access_denied_content_rating, msg_found_x_results_removed_y, msg_auth_feature_required
from number_utils import is_integer
from text_utils import is_blank, clean_string
from thread_utils import TaskManager, get_exception, TaskWrapper, TaskWorker

process_blueprint = Blueprint('process', __name__)

# Initialize TaskManager
global task_manager, worker_queue_number
key_lock_manager = KeyLockManager()
task_manager = TaskManager(key_lock_manager=key_lock_manager)

# Initialize ThreadPoolExecutor with a maximum # of worker threads
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

def close_queue_session(my_task_manager: TaskManager, task_wrapper: TaskWrapper, session: Session,
                        worker_status: TaskWorker):
    try:
        my_task_manager.task_done_queue(task_wrapper, worker_status)
        task_wrapper.mark_end()
        if session is not None:
            session.close()
    except Exception as inst:
        logging.error(inst)
        task_wrapper.add_log(str(inst))
    worker_status.status = TaskWorker.STATUS_IDLE
    worker_status.job = 0
    worker_status.last_seen = time.time()


# Worker function to consume tasks
def queue_worker(my_task_manager: TaskManager, app, index: int):
    worker_status = my_task_manager.add_worker(index)
    idle_wait = 1

    while True:
        worker_status.status = TaskWorker.STATUS_IDLE
        worker_status.last_seen = time.time()
        task_wrapper = my_task_manager.get_task_queue()
        if task_wrapper is None:
            time.sleep(idle_wait)
            idle_wait = min(idle_wait + 1, 10)
            continue

        idle_wait = 2
        worker_status.job = task_wrapper.task_id
        worker_status.status = TaskWorker.STATUS_RUNNING
        session = None
        try:
            task_wrapper.trace('Before Context')
            with app.app_context():
                task_wrapper.trace('In Context')
                SessionMak = sessionmaker(bind=db.engine)
                session = SessionMak()

                task_wrapper.trace('Before Local Session')
                task_wrapper.mark_start()
                task_wrapper.always('Executing Task')
                username = get_username(task_wrapper.user)
                uid = get_uid(task_wrapper.user)
                task_wrapper.info(f'Executed by {username} ({uid})')
                task_wrapper.set_waiting(False)
                task_wrapper.run(session)
                task_wrapper.set_finished(True)
                task_wrapper.always('Finished Task')
        except Exception as inst:
            logging.error(inst)
            task_wrapper.add_log(str(inst))
            ex_json = get_exception()
            task_wrapper.set_finished(True)
            task_wrapper.set_failure(True)
            task_wrapper.error(
                'Exception: ' + ex_json['message'] + ' - ' + ex_json['file'] + '[' + ex_json['line'] + ']')
        finally:
            close_queue_session(my_task_manager, task_wrapper, session, worker_status)
    worker_status.status = TaskWorker.STATUS_DEAD


def init_processors(app):
    global task_manager, worker_queue_number
    worker_queue_number = 1
    for i in range(MAX_WORKERS):
        init_processor(app)


def init_processor(app):
    global task_manager, worker_queue_number
    executor.submit(queue_worker, task_manager, app, worker_queue_number)
    worker_queue_number = worker_queue_number + 1


@process_blueprint.route('/add/worker', methods=['POST'])
@feature_required(process_blueprint, MANAGE_PROCESSES)
def add_worker(user_details):
    app = current_app._get_current_object()  # gets the actual app, not the proxy
    with app.app_context():
        init_processor(app)
    return generate_success_response('', messages=[msg_operation_complete()])


@process_blueprint.route('/add/plugin', methods=['POST'])
@shall_authenticate_user(process_blueprint)
def add_plugin_task(user_details):
    global task_manager

    if 'bundle' in request.form:
        # Retrieve the value of the 'bundle' field
        bundle_data = request.form['bundle']

        # Parse the JSON data
        try:
            json_data = json.loads(bundle_data)
        except json.JSONDecodeError:
            return generate_failure_response("Invalid JSON data", 400, messages=[msg_invalid_parameter('bundle')])

        task_id = json_data['id']
        task_args = json_data['args']
        plugins = current_app.config['PLUGINS']['all']

        duplicate_check = True

        logging_level = 20
        if '_logging_level' in task_args:
            logging_level = int(task_args['_logging_level'])
            if logging_level % 10 == 0 and 0 <= logging_level <= 50:
                pass
            else:
                # fallback
                logging_level = 20

        if '_duplicate_checking' in task_args:
            duplicate_check = (task_args['_duplicate_checking']) == 'y'

        for plugin in plugins:
            if plugin.get_action_id() == task_id:

                if (plugin.get_feature_flags() & user_details['features']) != plugin.get_feature_flags():
                    return generate_failure_response("User is not allowed to use the specified plugin", 401,
                                                     messages=[msg_access_denied_content_rating()])

                task_args['_user_details'] = user_details
                error_list = plugin.process_action_args(task_args)
                if error_list is None:

                    task_wrapper = plugin.create_task(db.session, task_args)

                    if task_wrapper is not None:

                        if isinstance(task_wrapper, Iterable):
                            skip_count = 0
                            add_count = 0
                            for task in task_wrapper:
                                if duplicate_check and task_manager.has_task(task.name, task.description):
                                    skip_count = skip_count + 1
                                else:
                                    add_count = add_count + 1
                                    task.update_user(user_details)
                                    task.update_logging_level(logging_level)

                                    task_manager.add_task(task)

                            return generate_success_response(f'Tasks Added: ({add_count}), Skipped: ({skip_count})',
                                                             messages=[msg_tasks_started(add_count, skip_count)])
                        else:
                            if duplicate_check and task_manager.has_task(task_wrapper.name, task_wrapper.description):
                                return generate_failure_response('Error: Task is already in the Queue',
                                                                 messages=[msg_action_cancelled_duplicate_task()])

                            # Execute the task asynchronously
                            task_wrapper.update_user(user_details)
                            task_wrapper.update_logging_level(logging_level)
                            # future = executor.submit(task_content, task_wrapper, app)
                            # task_wrapper.future = future

                            task_manager.add_task(task_wrapper)

                            return generate_success_response('Task added successfully',
                                                             {"task_id": task_wrapper.task_id},
                                                             messages=[msg_tasks_started(1, 0)])
                    else:
                        return generate_failure_response("Unknown TASK", messages=[msg_action_failed_missing()])

                else:
                    return generate_failure_response("Argument errors: " + str(error_list),
                                                     messages=[msg_action_failed()])

    # If the 'bundle' field is missing, return an error response
    return generate_failure_response("parameter bundle is missing", 400, messages=[msg_missing_parameter('bundle')])


@process_blueprint.route('/clean', methods=['POST'])
@feature_required(process_blueprint, MANAGE_PROCESSES)
def clean_tasks(user_details):
    """
    Remove all finished tasks
    :return: empty json
    """
    global task_manager

    count = task_manager.clean_tasks(True)

    # If the 'bundle' field is missing, return an error response
    return generate_success_response('', messages=[msg_removed_x_items(count)])


@process_blueprint.route('/sweep', methods=['POST'])
@feature_required(process_blueprint, MANAGE_PROCESSES)
def sweep_tasks(user_details):
    """
    Remove tasks that are finished, but did no work...
    :return: empty json
    """
    global task_manager

    count = task_manager.clean_tasks(False)

    # If the 'bundle' field is missing, return an error response
    return generate_success_response('', messages=[msg_removed_x_items(count)])


@process_blueprint.route('/stop', methods=['POST'])
@feature_required(process_blueprint, MANAGE_APP)
def stop_service(user_details):
    logging.info(f'User {user_details["username"]} requested to stop the service')
    # noinspection PyProtectedMember
    os._exit(1)

    return generate_success_response("OK", 200)


@process_blueprint.route('/restart', methods=['POST'])
@feature_required(process_blueprint, MANAGE_APP)
def restart_service(user_details):
    logging.info(f'User {user_details["username"]} requested to restart the service')
    # noinspection PyProtectedMember
    os._exit(69)

    return generate_success_response("OK", 200)


@process_blueprint.route('/status/all', methods=['POST'])
@feature_required(process_blueprint, VIEW_PROCESSES)
def get_all_task_status(user_detail):
    return get_all_task_status_extra_method(user_detail, '')


@process_blueprint.route('/status/all/with/<extra_method_call>', methods=['POST'])
@feature_required(process_blueprint, VIEW_PROCESSES)
def get_all_task_status_extra_method(user_detail, extra_method_call):
    global task_manager

    page = clean_string(request.form.get('page'))
    page_size = clean_string(request.form.get('page_size'))

    if not page:
        page = 0
    elif is_integer(page):
        page = int(page)
    else:
        page = 0

    if not page_size:
        page_size = 20
    elif is_integer(page_size):
        page_size = int(page_size)
    else:
        page_size = 20



    removed = task_manager.remove_dead_tasks()

    if removed > 0:
        app = current_app._get_current_object()  # gets the actual app, not the proxy
        with app.app_context():
            for i in range(removed):
                init_processor(app)

    removed_tasks = 0

    is_active_mode = False
    if is_blank(extra_method_call) or extra_method_call == 'NONE':
        pass
    elif extra_method_call == 'ACTIVE':
        is_active_mode = True
    else:
        if get_user_features(user_detail) & MANAGE_PROCESSES != MANAGE_PROCESSES:
            return generate_failure_response('Not allowed to use this method', 401, msg_auth_feature_required())

        if extra_method_call == 'HARD':
            removed_tasks = task_manager.clean_tasks(True)
        elif extra_method_call == 'SOFT':
            removed_tasks = task_manager.clean_tasks(False)

    tasks = task_manager.get_all_tasks()

    result = []

    if is_active_mode:
        for task in tasks:
            if not task:
                break

            if task.is_finished or task.is_waiting:
                continue

            result.append({
                "id": task.task_id,
                "name": task.name,
                "description": task.description,
                "progress": task.get_progress(),
                "percent": task.percent,
                "finished": task.is_finished,
                "waiting": task.is_waiting,
                "failure": task.is_failure,
                "warning": task.is_warning,
                "worked": task.is_worked,
                "logging": task.logging_level,
                "log": task.log_entries[-2:],
                "delay_duration": task.duration_delayed,
                "running_duration": task.duration_running,
                "total_duration": task.duration_total,
                "init_timestamp": task.init_timestamp,
                "start_timestamp": task.start_timestamp,
                "end_timestamp": task.end_timestamp,
                "book_id": task.ref_book_id,
                "folder_id": task.ref_folder_id,
                "folder_img": task.ref_folder_preview,
                "folder_name": task.ref_folder_name,
                "priority": task.priority,
                "weight": task.weight
            })

        total_items = len(result)

        msg = None
        if removed_tasks == 0:
            msg = msg_found_x_results(len(result))
        else:
            msg = msg_found_x_results_removed_y(len(result), removed_tasks)

        return generate_success_response('', {'page': page,
                                              'pages': 1,
                                              'total': total_items,
                                              'tasks': result,
                                              'weight': task_manager.get_weight(),
                                              'workers': task_manager.get_worker_status()},
                                         messages=[msg])
    else:
        total_items = len(tasks)

        pages = floor(total_items / page_size)
        # Check for overflow
        if total_items % page_size > 0:
            pages = pages + 1

        # Sanity

        if page_size < 0:
            page_size = 20
        elif page_size > 150:
            page_size = 150

        if pages == 1:
            page = 0
        elif page < 0:
            page = 0
        elif pages > 0 and page >= page_size:
            page = page_size - 1
        elif pages == 0:
            page = 0

        start = page * page_size
        end = start + page_size

        for task in tasks[start:end]:
            if not task:
                break

            result.append({
                "id": task.task_id,
                "name": task.name,
                "description": task.description,
                "progress": task.get_progress(),
                "percent": task.percent,
                "finished": task.is_finished,
                "waiting": task.is_waiting,
                "failure": task.is_failure,
                "warning": task.is_warning,
                "worked": task.is_worked,
                "logging": task.logging_level,
                "log": task.log_entries[-2:],
                "delay_duration": task.duration_delayed,
                "running_duration": task.duration_running,
                "total_duration": task.duration_total,
                "init_timestamp": task.init_timestamp,
                "start_timestamp": task.start_timestamp,
                "end_timestamp": task.end_timestamp,
                "book_id": task.ref_book_id,
                "folder_id": task.ref_folder_id,
                "folder_name": task.ref_folder_name,
                "folder_img": task.ref_folder_preview,
                "priority": task.priority,
                "weight": task.weight
            })

        msg = None
        if removed_tasks == 0:
            msg = msg_found_x_results(len(tasks))
        else:
            msg = msg_found_x_results_removed_y(len(tasks), removed_tasks)

        return generate_success_response('', {'page': page,
                                              'pages': pages,
                                              'total': total_items,
                                              'tasks': result,
                                              'weight': task_manager.get_weight(),
                                              'workers': task_manager.get_worker_status()},
                                         messages=[msg])


# REST endpoint to get task status
@process_blueprint.route('/status/<int:task_id>', methods=['POST'])
@feature_required_silent(process_blueprint, VIEW_PROCESSES)
def get_task_status(task_id):
    global task_manager

    task = task_manager.get_task_by_id(task_id)

    if task is not None:
        log_page_size = request.form.get('log_page_size', '0')
        log_page = request.form.get('log_page', '0')

        include_files = clean_string(request.form.get('include_files', '0')) == '1'

        try:
            log_page_size = max(0, int(log_page_size))
        except (ValueError, TypeError):
            log_page_size = 0

        try:
            log_page = max(0, int(log_page))
        except (ValueError, TypeError):
            log_page = 0

        all_logs = task.log_entries
        total_logs = len(all_logs)

        if log_page_size > 0:
            log_pages = ceil(total_logs / log_page_size)
            log_page = min(log_page, log_pages - 1) if log_pages > 0 else 0
            start = log_page * log_page_size
            paged_log = all_logs[start:start + log_page_size]
        else:
            log_pages = 1
            log_page = 0
            paged_log = all_logs

        status = {
            "id": task.task_id,
            "name": task.name,
            "description": task.description,
            "progress": task.get_progress(),
            "percent": task.percent,
            "finished": task.is_finished,
            "waiting": task.is_waiting,
            "failure": task.is_failure,
            "warning": task.is_warning,
            "worked": task.is_worked,
            "logging": task.logging_level,
            "log": paged_log,
            "log_total": total_logs,
            "log_pages": log_pages,
            "log_page": log_page,
            "log_page_size": log_page_size,
            "delay_duration": task.duration_delayed,
            "running_duration": task.duration_running,
            "total_duration": task.duration_total,
            "init_timestamp": task.init_timestamp,
            "start_timestamp": task.start_timestamp,
            "end_timestamp": task.end_timestamp,
            "book_id": task.ref_book_id,
            "folder_id": task.ref_folder_id,
            "priority": task.priority,
            "weight": task.weight,
            "files": []
        }

        if include_files:
            temp_folder = task.temp_folder_path
            if temp_folder is not None and os.path.isdir(temp_folder):
                files = []
                for entry in sorted(os.scandir(temp_folder), key=lambda e: e.name):
                    if entry.is_file():
                        try:
                            files.append({
                                "name": entry.name,
                                "size": entry.stat().st_size
                            })
                        except OSError:
                            continue
                status["files"] = files

        return generate_success_response('', {'task': status})

    return generate_failure_response("Task not found", 404, messages=[msg_action_failed_missing()])


SEVERITY_NAMES = {0: 'TRACE', 10: 'DEBUG', 20: 'INFO', 30: 'WARN', 40: 'ERROR', 50: 'CRIT', 100: 'ALWAYS'}


@process_blueprint.route('/log/download/<int:task_id>', methods=['POST'])
@feature_required_silent(process_blueprint, VIEW_PROCESSES)
def download_task_log(task_id):
    global task_manager

    task = task_manager.get_task_by_id(task_id)
    if task is None:
        return generate_failure_response("Task not found", 404, messages=[msg_action_failed_missing()])

    fmt = clean_string(request.form.get('format', 'md')).lower()
    if fmt not in ('md', 'json'):
        fmt = 'md'

    safe_name = ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in task.name)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'{safe_name}_{timestamp}.{fmt}'

    entries = task.log_entries

    if fmt == 'json':
        payload = {
            'id': task.task_id,
            'name': task.name,
            'description': task.description,
            'log': entries,
        }
        data = json.dumps(payload, indent=2).encode('utf-8')
        mimetype = 'application/json'
    else:
        lines = [
            f'# {task.name}',
            f'**Description:** {task.description}',
            f'**Task ID:** {task.task_id}',
            '',
            '| Time | Level | Message |',
            '|---|---|---|',
        ]
        for entry in entries:
            level = SEVERITY_NAMES.get(entry.get('s', 20), 'INFO')
            time_str = entry.get('time', '')
            text = entry.get('text', '').replace('|', '\\|')
            lines.append(f'| {time_str} | {level} | {text} |')
        data = '\n'.join(lines).encode('utf-8')
        mimetype = 'text/markdown'

    buf = io.BytesIO(data)
    buf.seek(0)
    return send_file(buf, mimetype=mimetype, as_attachment=True, download_name=filename)



@process_blueprint.route('/cancel/<int:task_id>', methods=['POST'])
@feature_required(process_blueprint, MANAGE_PROCESSES)
def cancel_task(user_details, task_id: int):
    global task_manager

    username = get_username(user_details)

    task = task_manager.get_task_by_id(task_id)
    if task is not None:
        task.always(f'Task Cancelled by {username}')
        task.cancel()

        return generate_success_response("Task canceled", messages=[msg_operation_complete()])

    return generate_failure_response(f"Task {task_id} not found", 404, messages=[msg_action_failed_missing()])


@process_blueprint.route('/logging/<int:task_id>', methods=['POST'])
@feature_required_silent(process_blueprint, MANAGE_PROCESSES)
def change_task_logging(task_id):
    global task_manager

    level = request.form.get('level')

    if is_blank(level):
        return generate_failure_response('level parameter is required', messages=[msg_missing_parameter('level')])

    if not is_integer(level):
        return generate_failure_response('level parameter is not an integer', messages=[msg_invalid_parameter('level')])
    level = int(level)

    if level < 0 or level > 50 or level % 10 != 0:
        return generate_failure_response('level parameter is not valid', messages=[msg_invalid_parameter('level')])

    task = task_manager.get_task_by_id(task_id)

    if task is not None:
        task.update_logging_level(level)
        return generate_success_response("Task level updated", messages=[msg_operation_complete()])

    return generate_failure_response("Task not found", 404, messages=[msg_action_failed_missing()])


@process_blueprint.route('/purge/<int:task_id>', methods=['DELETE'])
@feature_required(process_blueprint, MANAGE_PROCESSES)
def purge_task(user_details, task_id: int):
    global task_manager

    if task_manager.purge_task(task_id):
        return generate_success_response('Task removed', messages=[msg_operation_complete()])

    return generate_failure_response(f'Task {task_id} not found or still active', 404,
                                     messages=[msg_action_failed_missing()])


@process_blueprint.route('/promote/<int:task_id>', methods=['POST'])
@feature_required(process_blueprint, MANAGE_PROCESSES)
def promote_task(user_details, task_id: int):
    global task_manager
    if task_manager.adjust_priority(task_id, 0):
        return generate_success_response("Task moved", messages=[msg_operation_complete()])
    else:
        return generate_failure_response("Task not found", 404, messages=[msg_action_failed_missing()])
