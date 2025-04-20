import json
import logging
import os
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, request, current_app
from sqlalchemy.orm import sessionmaker, Session

from auth_utils import shall_authenticate_user, feature_required, feature_required_silent, get_username, get_uid
from common_utils import generate_failure_response, generate_success_response
from constants import MAX_WORKERS
from db import db
from feature_flags import MANAGE_PROCESSES, VIEW_PROCESSES, MANAGE_APP
from messages import msg_invalid_parameter, msg_tasks_started, msg_action_cancelled_duplicate_task, \
    msg_missing_parameter, msg_action_failed, msg_operation_complete, msg_action_failed_missing, msg_removed_x_items, \
    msg_found_x_results, msg_access_denied_content_rating
from number_utils import is_integer
from text_utils import is_blank
from thread_utils import TaskManager, get_exception, TaskWrapper, TaskWorker

process_blueprint = Blueprint('process', __name__)

# Initialize TaskManager
global task_manager, worker_queue_number
task_manager = TaskManager()

# Initialize ThreadPoolExecutor with a maximum # of worker threads
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


def close_queue_session(my_task_manager: TaskManager, task_wrapper: TaskWrapper, session: Session,
                        worker_status: TaskWorker):
    try:
        worker_status.position = 9
        my_task_manager.task_done_queue(task_wrapper, worker_status)
        worker_status.position = 10
        task_wrapper.mark_end()
        worker_status.position = 11
        if session is not None:
            worker_status.position = 12
            session.close()
    except Exception as inst:
        worker_status.position = 13
        logging.error(inst)
        worker_status.position = 14
        task_wrapper.add_log(str(inst))
        worker_status.position = 15
    worker_status.position = 20


# Worker function to consume tasks
def queue_worker(my_task_manager: TaskManager, app, index: int):
    worker_status = my_task_manager.add_worker(index)

    while True:
        worker_status.wait_stamp = 0
        worker_status.position = 1
        task_wrapper = my_task_manager.get_task_queue()
        if task_wrapper is None:
            worker_status.position = 2
            time.sleep(3)
            continue  # Sentinel to exit
        worker_status.job = task_wrapper.task_id
        session = None
        try:
            worker_status.position = 3
            task_wrapper.trace('Before Context')
            with app.app_context():
                task_wrapper.trace('In Context')
                worker_status.position = 4
                SessionMak = sessionmaker(bind=db.engine)
                session = SessionMak()

                # Create a new session for the thread
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
            worker_status.position = 5
            logging.error(inst)
            task_wrapper.add_log(str(inst))
            ex_json = get_exception()
            worker_status.position = 6
            task_wrapper.set_finished(True)
            task_wrapper.set_failure(True)
            task_wrapper.error(
                'Exception: ' + ex_json['message'] + ' - ' + ex_json['file'] + '[' + ex_json['line'] + ']')
        finally:
            worker_status.position = 70
            close_queue_session(my_task_manager, task_wrapper, session, worker_status)
            worker_status.position = 72
            worker_status.wait_stamp = time.time()
    worker_status.online = False


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


@process_blueprint.route('/new_worker', methods=['POST'])
@feature_required(process_blueprint, MANAGE_PROCESSES)
def new_worker(user_details):
    app = current_app._get_current_object()  # gets the actual app, not the proxy
    executor.submit(queue_worker, task_manager, app, generate_worker_id())
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
    global task_manager

    removed = task_manager.remove_dead_tasks()

    if removed > 0:
        app = current_app._get_current_object()  # gets the actual app, not the proxy
        with app.app_context():
            for i in range(removed):
                init_processor(app)

    tasks = task_manager.get_all_tasks()

    result = []

    for task in tasks:
        result.append({
            "id": task.task_id,
            "name": task.name,
            "description": task.description,
            "progress": task.progress,
            "percent": task.percent,
            "finished": task.is_finished,
            "waiting": task.is_waiting,
            "failure": task.is_failure,
            "warning": task.is_warning,
            "worked": task.is_worked,
            "logging": task.logging_level,
            "log": task.log_entries,
            "delay_duration": task.duration_delayed,
            "running_duration": task.duration_running,
            "total_duration": task.duration_total,
            "init_timestamp": task.init_timestamp,
            "start_timestamp": task.start_timestamp,
            "end_timestamp": task.end_timestamp,
            "book_id": task.ref_book_id,
            "folder_id": task.ref_folder_id,
            "priority": task.priority,
            "weight": task.weight
        })

    return generate_success_response('', {'tasks': result, 'weight': task_manager.get_weight(),
                                          'workers': task_manager.get_worker_status()},
                                     messages=[msg_found_x_results(len(tasks))])


# REST endpoint to get task status
@process_blueprint.route('/status/<int:task_id>', methods=['POST'])
@feature_required_silent(process_blueprint, VIEW_PROCESSES)
def get_task_status(task_id):
    global task_manager

    task = task_manager.get_task_by_id(task_id)

    if task is not None:
        status = {
            "id": task.task_id,
            "name": task.name,
            "description": task.description,
            "progress": task.progress,
            "percent": task.percent,
            "finished": task.is_finished,
            "waiting": task.is_waiting,
            "failure": task.is_failure,
            "warning": task.is_warning,
            "worked": task.is_worked,
            "logging": task.logging_level,
            "log": task.log_entries,
            "delay_duration": task.duration_delayed,
            "running_duration": task.duration_running,
            "total_duration": task.duration_total,
            "init_timestamp": task.init_timestamp,
            "start_timestamp": task.start_timestamp,
            "end_timestamp": task.end_timestamp,
            "book_id": task.ref_book_id,
            "folder_id": task.ref_folder_id,
            "priority": task.priority,
            "weight": task.weight
        }
        return generate_success_response('', {'task': status})

    return generate_failure_response("Task not found", 404, messages=[msg_action_failed_missing()])


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


@process_blueprint.route('/promote/<int:task_id>', methods=['POST'])
@feature_required(process_blueprint, MANAGE_PROCESSES)
def promote_task(user_details, task_id: int):
    global task_manager
    if task_manager.adjust_priority(task_id, 0):
        return generate_success_response("Task moved", messages=[msg_operation_complete()])
    else:
        return generate_failure_response("Task not found", 404, messages=[msg_action_failed_missing()])
