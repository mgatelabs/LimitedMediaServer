from bs4 import BeautifulSoup

from db import Book
from feed_utils import extract_guid_numbers, fix_hyphenated_numbers
from html_utils import download_secure_text, remove_trailing_slash, guess_file_extension
from number_utils import pad_integer_number, pad_decimal_string
from processors.processor_core import CustomDownloadInterface
from soup_utils import get_first_valid_attribute
from text_utils import extract_webp_strings, extract_jpeg_strings
from thread_utils import TaskWrapper

"""
Generic class used to make a Book Processor
"""


class GenericBasicProcessor(CustomDownloadInterface):
    def __init__(self, processor_id: str, processor_name: str, chapter_query: str, image_query: str,
                 chapter_parser: str,
                 task_wrapper: TaskWrapper = None, image_method:str = 'default'):
        """
        :type processor_id: str
        :type processor_name: str
        :type chapter_query: str
        :type image_query: str
        :type chapter_parser: str
        :type task_wrapper: TaskWrapper
        :type image_method: str
        """
        super().__init__(processor_id, processor_name, task_wrapper)
        self.chapter_query = chapter_query
        self.image_query = image_query
        self.chapter_parser = chapter_parser
        self.image_method = image_method

    def list_chapters(self, definition: Book, headers=None):
        # Download the webpage
        response = download_secure_text(definition.info_url, headers, self.task_wrapper)

        if self.task_wrapper.can_trace():
            self.task_wrapper.trace(response)

        # Parse HTML content
        soup = BeautifulSoup(response, 'html.parser')

        a_items = soup.select(self.chapter_query)

        data_list = []
        for a in a_items:
            href = a['href'].strip()

            chapter_name = None

            if self.chapter_parser == 'chapter_with_trailing_slash':  # /chapter-23.2
                cleaned = remove_trailing_slash(href)
                front_part, known_decimal = extract_guid_numbers(cleaned)
                front_part = pad_integer_number(front_part, 4)
                if known_decimal > 0:
                    front_part = front_part + '.' + str(known_decimal)
                chapter_name = pad_decimal_string(front_part)
            elif self.chapter_parser == 'chapter_with_extra_hyphen_add_trailing_slash':  # /chapter-23-2/
                cleaned = fix_hyphenated_numbers(remove_trailing_slash(href))
                front_part, known_decimal = extract_guid_numbers(cleaned)
                front_part = pad_integer_number(front_part, 4)
                if known_decimal > 0:
                    front_part = front_part + '.' + str(known_decimal)
                chapter_name = pad_decimal_string(front_part)
            elif self.chapter_parser == 'chapter_without_trailing_slash':  # /chapter-23.2
                front_part, known_decimal = extract_guid_numbers(href)
                front_part = pad_integer_number(front_part, 4)
                if known_decimal > 0:
                    front_part = front_part + '.' + str(known_decimal)
                chapter_name = pad_decimal_string(front_part)

            if chapter_name is not None:
                data_list.append({'chapter': chapter_name, 'href': href})

        data_list.reverse()

        return data_list

    def list_images(self, definition: Book, chapter, headers=None):
        # Download the webpage
        response = download_secure_text(chapter['href'], headers, self.task_wrapper)

        if self.task_wrapper.can_trace():
            self.task_wrapper.trace(response)

        image_sources = []

        if self.image_method == 'default':
            # Parse HTML content
            soup = BeautifulSoup(response, 'html.parser')
            img_items = soup.select(self.image_query)
            image_index = 1
            for img in img_items:
                src = get_first_valid_attribute(img, 'src', 'data-src')
                if src:
                    extension = guess_file_extension(src)
                    image_sources.append({"src": src, "file": pad_integer_number(image_index, 4) + "." + extension})
                    image_index = image_index + 1
        elif self.image_method == 'find_strings':
            if self.task_wrapper.can_trace():
                self.task_wrapper.trace('Searching for webp')
            ending = '.wepb'
            found_images = extract_webp_strings(response)

            if self.task_wrapper.can_trace():
                self.task_wrapper.trace(f'Found {len(found_images)}')

            if len(found_images) <= 2:
                if self.task_wrapper.can_trace():
                    self.task_wrapper.trace('Searching for jpeg')
                ending = '.jpeg'
                found_images = extract_jpeg_strings(response)
                self.task_wrapper.trace(f'Found {len(found_images)}')

            image_index = 1
            for img in found_images:
                src = img
                if src.startswith('https:'):
                    image_sources.append({"src": src.replace("\\/", "/"), "file": pad_integer_number(image_index, 4) + ending})
                    image_index = image_index + 1

        return image_sources

    def get_tags(self, definition: Book, headers=None):
        return None

    def headers_required(self, definition: Book):
        return True

    def page_description(self):
        return 'The root page for the media'
