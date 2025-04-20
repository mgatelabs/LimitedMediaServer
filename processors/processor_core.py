import copy
from abc import ABC, abstractmethod
from typing import Optional

from db import Book
from image_utils import convert_images_to_format
from thread_utils import TaskWrapper, NoOpTaskWrapper


class CustomDownloadInterface(ABC):

    def __init__(self, processor_id: str, processor_name: str, task_wrapper: TaskWrapper = None):
        """
        Create a new instance
        :param processor_id: The unique ID for this processor
        :param processor_name: The Name for this processor
        :param task_wrapper: A logger, not required
        """
        super().__init__()
        self.processor_id = processor_id
        self.processor_name = processor_name

        if task_wrapper is None:
            task_wrapper = NoOpTaskWrapper()
        self.task_wrapper = task_wrapper

    def get_name(self):
        return self.processor_name

    def get_id(self):
        return self.processor_id

    @abstractmethod
    def list_chapters(self, definition: Book, headers=None):
        """
        List the chapters for a given book definition
        :param definition: The book to process (JSON)
        :param headers: The headers, if available
        :return: list [{'chapter': "chapter_name", 'href': "chapter_url"}]
        """

        pass

    @abstractmethod
    def list_images(self, definition: Book, chapter, headers=None):
        """
        List the images for a given chapter
        :param definition: The book to process (JSON)
        :param chapter: This will be an item from list_chapters so {'chapter': "chapter_name", 'href': "chapter_url"}
        :param headers: The headers, if available
        :return: list [{'src': 'image_url', "file": 'desired_filename', "secure": False}]
        """
        pass

    def clean_folder(self, definition: Book, chapter, path, storage_format: str):
        """
        This is a chance for you to clean up the recently generated folder.  Maybe convert from JPG to PNG / WEBP.
        :param storage_format:
        :param definition: The book to process (JSON)
        :param chapter: This will be an item from list_chapters so {'chapter': "chapter_name", 'href': "chapter_url"}
        :param path: The folder path for this chapter
        :param storage_format: PNG or WEBP
        :return: Nothing
        """
        convert_images_to_format(path, storage_format, self.task_wrapper)

    @abstractmethod
    def get_tags(self, definition: Book, headers):
        pass

    @abstractmethod
    def headers_required(self, definition: Book):
        """
        Does this processor require Headers to be sent up?
        :param definition:
        :return:
        """
        return False

    def is_active(self, definition: Book, headers=None) -> Optional[bool]:
        """
        Is this book still ongoing?
        :param definition: The book row
        :param headers: Browser headers, if available
        :return: True/False/None.  None is Unknown.
        """
        return None

    def requires_starting_page(self):
        """
        Does the processor need the starting page field?
        :return: True if it needs the starting chapter number
        """
        return False

    def starting_page_description(self):
        """
        Describe what is needed for Starting page variable.
        :return: The description as a string
        """
        return ''

    def requires_base_url(self):
        """
        Does this processor need the BASE URL field?
        :return: True if it needs the BASE URL field
        """
        return False

    def base_url_description(self):
        """
        Describe what is needed for Base URL variable.
        :return: The description as a string
        """
        return ''

    def page_description(self):
        """
        Describe what is needed for PAGE variable.
        :return: The description as a string
        """
        return ''

    def requires_rss(self):
        """
                Does this processor need the RSS field?
                :return: True if it needs the RSS field
                """
        return False

    def check_and_retry(self):
        return False

    # noinspection PyMethodMayBeStatic
    def rss_description(self):
        """
        Describe what is needed for RSS variable.
        :return: The description as a string
        """
        return ''

    def clone_to(self, task_wrapper: TaskWrapper) -> "CustomDownloadInterface":
        """
        This is used to make a copy of the processor, since it can get into a weird state being "shared"
        :param task_wrapper: The logger to assign
        :return: A cloned copy of this processor
        """

        # Deep copy using copy.deepcopy()
        cloned_instance_deep = copy.deepcopy(self)

        # Modifying the value of the original instance
        cloned_instance_deep.task_wrapper = task_wrapper

        return cloned_instance_deep
