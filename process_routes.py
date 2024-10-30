import json
import logging
import os
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, request, jsonify, current_app
from sqlalchemy.orm import sessionmaker

from auth_utils import shall_authenticate_user, feature_required
from db import db
from feature_flags import MANAGE_PROCESSES, VIEW_PROCESSES, MANAGE_APP
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

            task_wrapper.always('Executing')
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
            return jsonify({"status": "FAIL", "message": "Invalid JSON data"}), 400

        task_id = json_data['id']
        task_args = json_data['args']
        plugins = current_app.config['PLUGINS']['all']

        logging_level = 20
        if '_logging_level' in task_args:
            logging_level = int(task_args['_logging_level'])
            if logging_level % 10 == 0 and 0 <= logging_level <= 50:
                pass
            else:
                # fallback
                logging_level = 20

        # Get the current application context
        app = current_app._get_current_object()

        def task_content(tw, a):
            execute_task(tw, a)

        for plugin in plugins:
            if plugin.get_action_id() == task_id:

                if (plugin.get_feature_flags() & user_details['features']) != plugin.get_feature_flags():
                    return jsonify(
                        {"status": "FAIL", "message": "User is not allowed to use the specified plugin"}), 401

                error_list = plugin.process_action_args(task_args)
                if error_list is None:

                    task_wrapper = plugin.create_task(db.session, task_args)

                    if task_wrapper is not None:

                        if isinstance(task_wrapper, Iterable):
                            for task in task_wrapper:
                                task.update_logging_level(logging_level)
                                # Execute the task asynchronously
                                future = executor.submit(task_content, task, app)
                                task.future = future
                                task_manager.add_task(task)

                            return jsonify({"status": "OK", "message": "Tasks added successfully"})
                        else:
                            # Execute the task asynchronously
                            task_wrapper.update_logging_level(logging_level)
                            future = executor.submit(task_content, task_wrapper, app)
                            task_wrapper.future = future

                            task_manager.add_task(task_wrapper)

                            return jsonify(
                                {"status": "OK", "message": "Task added successfully", "task_id": task_wrapper.task_id})
                    else:
                        return jsonify({"error": "Unknown TASK"}), 400

                else:
                    return jsonify({"status": "FAIL", "message": "Argument errors: " + str(error_list)})

    # If the 'bundle' field is missing, return an error response
    return jsonify({"status": "FAIL", "message": "Form field 'bundle' is missing"}), 400


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

    for task in tasks:
        if task.is_finished:
            result.append(task.task_id)

    for task_id in result:
        task_manager.remove_task_by_id(task_id)

    # If the 'bundle' field is missing, return an error response
    return jsonify({}), 200


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

    for task in tasks:
        if task.is_warning == False and task.is_failure == False and task.is_finished and not task.is_worked:
            result.append(task.task_id)

    for task_id in result:
        task_manager.remove_task_by_id(task_id)

    # If the 'bundle' field is missing, return an error response
    return jsonify({}), 200


@process_blueprint.route('/stop', methods=['POST'])
@feature_required(process_blueprint, MANAGE_APP)
def stop_service(user_details):
    logging.info(f'User {user_details["username"]} requested to stop the service')
    # noinspection PyProtectedMember
    os._exit(1)

    return jsonify({"message": "OK"}), 200


@process_blueprint.route('/restart', methods=['POST'])
@feature_required(process_blueprint, MANAGE_APP)
def restart_service(user_details):
    logging.info(f'User {user_details["username"]} requested to restart the service')
    # noinspection PyProtectedMember
    os._exit(69)

    return jsonify({"message": "OK"}), 200


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
            "log": task.log_entries
        })

    return jsonify(result)


# REST endpoint to get task status
@process_blueprint.route('/status/<int:task_id>', methods=['POST'])
@feature_required(process_blueprint, VIEW_PROCESSES)
def get_task_status(user_detail, task_id):
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
                "log": task.log_entries
            }
            return jsonify(status)

    return jsonify({"error": "Task not found"}), 404


# REST endpoint to get task status
@process_blueprint.route('/cancel/<int:task_id>', methods=['POST'])
@feature_required(process_blueprint, MANAGE_PROCESSES)
def cancel_task(user_details, task_id):
    global task_manager

    tasks = task_manager.get_all_tasks()

    for task in tasks:
        if task.task_id == task_id:
            task.cancel()

            return jsonify({"message": "Task canceled"})

    return jsonify({"message": "Task not found"}), 404


@process_blueprint.route('/promote/<int:task_id>', methods=['POST'])
@feature_required(process_blueprint, MANAGE_PROCESSES)
def promote_task(user_details, task_id):
    global task_manager

    if task_manager.move_task_to_top(task_id):
        return jsonify({"message": "Task moved"})
    else:
        return jsonify({"message": "Task not found"}), 404
