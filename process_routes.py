import json
import logging
import os
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, request, current_app
from sqlalchemy.orm import sessionmaker

from auth_utils import shall_authenticate_user, feature_required, feature_required_silent, get_username, get_uid
from common_utils import generate_failure_response, generate_success_response
from db import db
from feature_flags import MANAGE_PROCESSES, VIEW_PROCESSES, MANAGE_APP
from messages import msg_invalid_parameter, msg_tasks_started, msg_action_cancelled_duplicate_task, \
    msg_missing_parameter, msg_action_failed, msg_operation_complete, msg_action_failed_missing, msg_removed_x_items, \
    msg_found_x_results, msg_access_denied_content_rating
from number_utils import is_integer
from text_utils import is_blank
from thread_utils import TaskManager, get_exception, TaskWrapper

process_blueprint = Blueprint('process', __name__)

# Initialize TaskManager
task_manager = TaskManager()

# Initialize ThreadPoolExecutor with a maximum of 5 worker threads
executor = ThreadPoolExecutor(max_workers=5)


# Function to execute a task asynchronously
def execute_task(task_wrapper: TaskWrapper, app):
    session = None
    try:
        task_wrapper.trace('Before Context')
        with app.app_context():

            Session = sessionmaker(bind=db.engine)
            session = Session()

            # Create a new session for the thread
            task_wrapper.trace('Before Local Session')
            task_wrapper.mark_start()
            task_wrapper.always('Executing')
            username = get_username(task_wrapper.user)
            uid = get_uid(task_wrapper.user)
            task_wrapper.info(f'Executed by {username} ({uid})')
            task_wrapper.set_waiting(False)
            task_wrapper.run(session)
            task_wrapper.set_finished(True)
            task_wrapper.always('Finished')
    except Exception as inst:
        logging.error(inst)
        task_wrapper.add_log(str(inst))
        ex_json = get_exception()

        task_wrapper.set_finished(True)
        task_wrapper.set_failure(True)
        task_wrapper.error(
            'Exception: ' + ex_json['message'] + ' - ' + ex_json['file'] + '[' + ex_json['line'] + ']')
    finally:
        task_wrapper.mark_end()
        if session is not None:
            session.close()


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

        # Get the current application context
        app = current_app._get_current_object()

        def task_content(tw: TaskWrapper, a):
            # Run the one task
            execute_task(tw, a)
            # Let one task spawn off another
            if tw.post_task is not None:
                task_next = tw.post_task

                task_next.update_user(user_details)
                task_next.update_logging_level(logging_level)
                # Execute the task asynchronously
                future_next = executor.submit(task_content, task_next, app)
                task_next.future = future_next

                task_manager.add_task(task_next)



        for plugin in plugins:
            if plugin.get_action_id() == task_id:

                if (plugin.get_feature_flags() & user_details['features']) != plugin.get_feature_flags():
                    return generate_failure_response("User is not allowed to use the specified plugin", 401, messages=[msg_access_denied_content_rating()])

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
                                    # Execute the task asynchronously
                                    future = executor.submit(task_content, task, app)
                                    task.future = future
                                    task_manager.add_task(task)

                            return generate_success_response(f'Tasks Added: ({add_count}), Skipped: ({skip_count})', messages=[msg_tasks_started(add_count, skip_count)])
                        else:
                            if duplicate_check and task_manager.has_task(task_wrapper.name, task_wrapper.description):
                                return generate_failure_response('Error: Task is already in the Queue', messages=[msg_action_cancelled_duplicate_task()])

                            # Execute the task asynchronously
                            task_wrapper.update_user(user_details)
                            task_wrapper.update_logging_level(logging_level)
                            future = executor.submit(task_content, task_wrapper, app)
                            task_wrapper.future = future

                            task_manager.add_task(task_wrapper)

                            return generate_success_response('Task added successfully',
                                                             {"task_id": task_wrapper.task_id}, messages=[msg_tasks_started(1, 0)])
                    else:
                        return generate_failure_response("Unknown TASK", messages=[msg_action_failed_missing()])

                else:
                    return generate_failure_response("Argument errors: " + str(error_list), messages=[msg_action_failed()])

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

    tasks = task_manager.get_all_tasks()

    result = []

    count = 0

    for task in tasks:
        if task.is_finished:
            result.append(task.task_id)
            count = count + 1

    for task_id in result:
        task_manager.remove_task_by_id(task_id)

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

    tasks = task_manager.get_all_tasks()

    result = []
    count = 0

    for task in tasks:
        if task.is_warning == False and task.is_failure == False and task.is_finished and not task.is_worked:
            result.append(task.task_id)
            count = count + 1

    for task_id in result:
        task_manager.remove_task_by_id(task_id)

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
        })

    return generate_success_response('', {'tasks': result}, messages=[msg_found_x_results(len(tasks))])


# REST endpoint to get task status
@process_blueprint.route('/status/<int:task_id>', methods=['POST'])
@feature_required_silent(process_blueprint, VIEW_PROCESSES)
def get_task_status(task_id):
    global task_manager

    tasks = task_manager.get_all_tasks()

    for task in tasks:
        if task.task_id == task_id:
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
            }
            return generate_success_response('', {'task': status})

    return generate_failure_response("Task not found", 404, messages=[msg_action_failed_missing()])


# REST endpoint to get task status
@process_blueprint.route('/cancel/<int:task_id>', methods=['POST'])
@feature_required(process_blueprint, MANAGE_PROCESSES)
def cancel_task(user_details, task_id):
    global task_manager

    username = get_username(user_details)

    tasks = task_manager.get_all_tasks()

    for task in tasks:
        if task.task_id == task_id:
            task.always(f'Task Cancelled by {username}')
            task.cancel()

            return generate_success_response("Task canceled", messages=[msg_operation_complete()])

    return generate_failure_response(f"Task {task_id} not found", 404, messages=[msg_action_failed_missing()])


# REST endpoint to get task status
@process_blueprint.route('/logging/<int:task_id>', methods=['POST'])
@feature_required_silent(process_blueprint, MANAGE_PROCESSES)
def change_task_logging(task_id):
    global task_manager

    tasks = task_manager.get_all_tasks()

    level = request.form.get('level')

    if is_blank(level):
        return generate_failure_response('level parameter is required', messages=[msg_missing_parameter('level')])

    if not is_integer(level):
        return generate_failure_response('level parameter is not an integer', messages=[msg_invalid_parameter('level')])
    level = int(level)

    if level < 0 or level > 50 or level % 10 != 0:
        return generate_failure_response('level parameter is not valid', messages=[msg_invalid_parameter('level')])

    for task in tasks:
        if task.task_id == task_id:
            task.update_logging_level(level)
            return generate_success_response("Task level updated", messages=[msg_operation_complete()])

    return generate_failure_response("Task not found", 404, messages=[msg_action_failed_missing()])


@process_blueprint.route('/promote/<int:task_id>', methods=['POST'])
@feature_required(process_blueprint, MANAGE_PROCESSES)
def promote_task(user_details, task_id):
    global task_manager

    if task_manager.move_task_to_top(task_id):
        return generate_success_response("Task moved", messages=[msg_operation_complete()])
    else:
        return generate_failure_response("Task not found", 404, messages=[msg_action_failed_missing()])
