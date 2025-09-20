import argparse
import os

from flask_sqlalchemy.session import Session

from constants import PROPERTY_SERVER_VOLUME_FOLDER
from date_utils import convert_yyyymmdd_to_date, convert_timestamp_to_datetime
from feature_flags import MANAGE_VOLUME
from file_utils import reset_folder
from image_utils import resize_image
from plugin_methods import plugin_select_arg, plugin_select_values
from plugin_system import ActionBookSpecificPlugin, ActionBookGeneralPlugin
from text_utils import is_blank
from thread_utils import TaskWrapper
from volume_queries import update_book_live, manage_book_chapters


class UpdateAllCaches(ActionBookGeneralPlugin):
    """
    This is a generic way to cause every book to update its living DB definition.
    """

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'bkclnall'

    def get_sort(self):
        return {'id': 'books_workers', 'sequence': 3}

    def get_category(self):
        return 'book'

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Update All Caches'

    def get_action_id(self):
        return 'action.book.update.caches'

    def get_action_icon(self):
        return 'healing'

    def get_action_args(self):
        return [
            plugin_select_arg("Clean Previews", "clean_previews", "n", plugin_select_values('No', 'n', 'Yes', 'y'),
                              "Should the preview images be re-created?", 'bkclnall'),
            plugin_select_arg("Update Tags", "update_tags", "n", plugin_select_values('No', 'n', 'Yes', 'y'),
                              "Sync book tags?", 'bkclnall')
        ]

    def process_action_args(self, args):
        return None

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def absorb_config(self, config):
        super().absorb_config(config)

    def create_task(self, db_session: Session, args):
        return UpdateAllJson("Update", 'All Volume Definitions',
                             'clean_previews' in args and args['clean_previews'] == 'y',
                             'update_tags' in args and args['update_tags'] == 'y',
                             self.book_storage_folder)


class UpdateSingleCache(ActionBookSpecificPlugin):
    """
    This is a generic way to cause a single book to update its living DB definition.
    """

    def __init__(self):
        super().__init__()
        self.book_folder = ''
        self.prefix_lang_id = 'bkcln'

    def is_book(self):
        return True

    def get_category(self):
        return "book"

    def get_sort(self):
        return {'id': 'book_workers', 'sequence': 3}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Update Cache'

    def get_action_id(self):
        return 'action.book.update.cache'

    def get_action_icon(self):
        return 'healing'

    def get_action_args(self):
        args = super().get_action_args()

        args.append(
            plugin_select_arg("Clean Previews", "clean_previews", "n", plugin_select_values('No', 'n', 'Yes', 'y'),
                              "Should the preview images be re-created?", 'bkclnall'))

        return args

    def process_action_args(self, args):
        return None

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def absorb_config(self, config):
        super().absorb_config(config)
        self.book_folder = config[PROPERTY_SERVER_VOLUME_FOLDER]

    def create_task(self, db_session: Session, args):
        book_id = args['book_id']
        return UpdateSingleBookStats("Update", f'Update {book_id} Definition', book_id,
                                     'clean_previews' in args and args['clean_previews'] == 'y', self.book_folder)


def custom_chapter_sorting(obj):
    name = obj["name"]
    decimal_part = name.split("-")[-1]  # Get the part after "-"
    return float(decimal_part)  # Convert to float for sorting


def custom_decimal_sorting(obj):
    return float(obj["name"])  # Convert to float for sorting


def folder_creation_date(folder_path):
    try:
        # Get the creation time of the folder
        creation_time = os.path.getctime(folder_path)

        # Convert the creation time to a datetime object
        creation_datetime = convert_timestamp_to_datetime(creation_time)

        # Format the datetime object as YYYYMMDD string
        formatted_date = creation_datetime.strftime("%Y%m%d")

        return formatted_date
    except OSError as e:
        print(f"Error: {e}")
        return None


def generate_db_for_folder(session, item_name, folder_path, task_wrapper: TaskWrapper, clean_previews: bool = False,
                           sync_tags: bool = False):
    task_wrapper.always("Building for: " + item_name)

    json_data = {'id': item_name, 'chapters': []}

    if task_wrapper.can_trace():
        task_wrapper.trace(f'Sort Stuff')

    for root, dirs, files in os.walk(folder_path):
        if root == folder_path:
            previews_path = os.path.join(root, '.previews')

            if clean_previews:
                reset_folder(previews_path)
            else:
                os.makedirs(previews_path, exist_ok=True)

            prev_chapter = ''

            number_of_chapters = len(dirs)
            chapter_index = 1

            for chapter_dir in dirs:

                # Update the sub-progress
                progress = (chapter_index / number_of_chapters) * 100
                chapter_index = chapter_index + 1
                task_wrapper.update_percent(progress)

                if chapter_dir.startswith('.'):
                    continue
                chapter_path = os.path.join(root, chapter_dir)
                if os.path.isdir(chapter_path):

                    if task_wrapper.can_trace():
                        task_wrapper.trace(f'Working on {chapter_path}')

                    image_file_list = sorted(os.listdir(chapter_path))

                    if task_wrapper.can_trace():
                        task_wrapper.trace(f'Sorted')

                    json_data['chapters'].append({'name': chapter_dir, 'files': image_file_list, 'prev': '', 'next': '',
                                                  'date': folder_creation_date(chapter_path)})

                    if task_wrapper.can_trace():
                        task_wrapper.trace(f'Data Produced')

                    if len(image_file_list) > 0:

                        if task_wrapper.can_trace():
                            task_wrapper.trace(f'Make Thumbnail Image')

                        dest_image_file = os.path.join(previews_path, chapter_dir + '.webp')
                        if clean_previews and os.path.isfile(dest_image_file):
                            os.remove(dest_image_file)

                        imgpath = os.path.join(chapter_path, image_file_list[0])

                        if not os.path.isfile(dest_image_file) or os.path.getmtime(dest_image_file) < os.path.getmtime(
                                imgpath):
                            task_wrapper.set_worked()

                            if task_wrapper.can_trace():
                                task_wrapper.trace(f'New Image {imgpath}')
                            try:
                                resize_image(imgpath, dest_image_file, 200, "WEBP")
                                if task_wrapper.can_trace():
                                    task_wrapper.trace(f'Image Created')
                            except Exception as e:
                                task_wrapper.error("Error making thumbnail file")

    if json_data['chapters'][0]['name'].startswith("chapter-"):

        if task_wrapper.can_trace():
            task_wrapper.trace(f'Fancy Chapters')

        sorted_objects = sorted(json_data['chapters'], key=custom_chapter_sorting)
        json_data['chapters'] = sorted_objects
    else:

        if task_wrapper.can_trace():
            task_wrapper.trace(f'Cheap Chapters')

        sorted_objects = sorted(json_data['chapters'], key=custom_decimal_sorting)
        json_data['chapters'] = sorted_objects

    if task_wrapper.can_trace():
        task_wrapper.trace(f'Chapter Findings')

    array_of_objects = json_data['chapters']

    # Loop through the array indices
    for i in range(len(array_of_objects)):
        current_object = array_of_objects[i]

        # Get the previous object if it exists
        previous_object = array_of_objects[i - 1] if i > 0 else None

        if previous_object is not None:
            current_object['prev'] = previous_object['name']

        # Get the next object if it exists
        next_object = array_of_objects[i + 1] if i < len(array_of_objects) - 1 else None

        if next_object is not None:
            current_object['next'] = next_object['name']

    # Set a date in the FAR past
    json_data['date'] = '20050101'
    json_data['last'] = ''

    if task_wrapper.can_trace():
        task_wrapper.trace(f'Chapter Lookups')

    # If we have chapters, try to extract the dates from them
    if len(json_data['chapters']) > 0:
        json_data['cover'] = json_data['chapters'][0]['name']
        json_data['last'] = json_data['chapters'][-1]['name']
        json_data['date'] = json_data['chapters'][-1]['date']

    # Default the tags
    json_data['tags'] = []

    if task_wrapper.can_trace():
        task_wrapper.trace(f'Before Live Update')

    update_book_live(item_name, convert_yyyymmdd_to_date(json_data['date']), json_data['last'], json_data['cover'],
                     json_data['cover'], logger=task_wrapper, db_session=session, sync_tags=sync_tags)
    if task_wrapper.can_trace():
        task_wrapper.trace('Before manage_book_chapters')
    manage_book_chapters(item_name, json_data['chapters'], task_wrapper, session)
    if task_wrapper.can_trace():
        task_wrapper.trace('After manage_book_chapters')


def generate_book_definitions(task_wrapper: TaskWrapper, series_id: str = None, book_folder: str = '',
                              clean_previews: bool = False, sync_tags=False, session=None):
    if is_blank(book_folder) or not os.path.isdir(book_folder):
        task_wrapper.add_log("Invalid book folder path.")
        return

    if series_id is not None:
        folders = [series_id]
    else:
        folders = os.listdir(book_folder)
    index = 0

    for item in folders:
        index = index + 1

        # If it has been cancelled
        if task_wrapper.is_cancelled:
            break

        if series_id is not None and series_id != item:
            continue

        if task_wrapper.can_debug() and series_id is not None:
            task_wrapper.debug(f'Found config for {series_id}')

        task_wrapper.update_progress((index / len(folders)) * 100.0)

        item_path = os.path.join(book_folder, item)
        if os.path.isdir(item_path):
            try:
                generate_db_for_folder(session, item, item_path, task_wrapper, clean_previews, sync_tags)
            except Exception as ex:
                task_wrapper.critical(ex)


class UpdateAllJson(TaskWrapper):
    """
    Update every JSON file
    """

    def __init__(self, name, description, clean_previews: bool, sync_tags: bool = False, book_folder: str = ''):
        super().__init__(name, description)
        self.clean_previews = clean_previews
        self.sync_tags = sync_tags
        self.book_folder = book_folder

    def run(self, db_session):
        generate_book_definitions(self, None, self.book_folder, self.clean_previews, sync_tags=self.sync_tags,
                                  session=db_session)


class UpdateSingleBookStats(TaskWrapper):
    """
    Update a single book's JSON file
    """

    def __init__(self, name, description, series_id: str, clean_previews: bool, book_folder: str = ''):
        super().__init__(name, description)
        self.series_id = series_id
        self.clean_previews = clean_previews
        self.book_folder = book_folder
        self.ref_book_id = series_id

    def run(self, db_session):
        generate_book_definitions(self, self.series_id, self.book_folder, self.clean_previews, session=db_session)
