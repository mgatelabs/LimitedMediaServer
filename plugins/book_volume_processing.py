import os
from typing import Optional

from flask_sqlalchemy.session import Session

from db import Book
from file_utils import delete_empty_folders
from html_utils import download_unsecure_file, download_secure_file, get_headers, get_headers_when_empty
from image_utils import clean_images_folder
from plugins.book_update_stats import generate_db_for_folder
from processors.processor_core import CustomDownloadInterface
from text_utils import is_not_blank
from thread_utils import TaskWrapper
from utility import random_sleep


def _process_download(processor, token, book: Book, task_wrapper, book_folder: str, clean_all: bool = False):
    headers = None

    headers_required = processor.headers_required(book)

    site_url = ''
    if is_not_blank(book.info_url):
        site_url = book.info_url
    elif is_not_blank(book.extra_url):
        site_url = book.extra_url

    skipList = []
    if is_not_blank(book.skip):
        skipList = [value.strip() for value in book.skip.split(',')]

    if headers_required:

        headers = get_headers_when_empty(None, site_url, task_wrapper)

        if headers is None:
            return False

    book_id = book.id

    if task_wrapper.can_trace():
        task_wrapper.trace(f'Book {book_id}')

    chapters = processor.list_chapters(book)

    task_wrapper.info(f'Chapters Found: {len(chapters)}')

    book_index = 0
    chapter_index = 0

    skipped_chapters = 0
    downloaded_chapters = 0
    downloaded_images = 0

    modified = False

    for chapter in chapters:

        chapter_index = chapter_index + 1

        task_wrapper.update_progress(100.0 * (chapter_index / len(chapters)))

        book_index = book_index + 1

        if token is not None and token.should_stop:
            break

        chapter_id = chapter['chapter']

        if task_wrapper.can_trace():
            task_wrapper.trace(f'Chapter {chapter_id}')

        # If this chapter is skipped, don't look at it!
        if chapter_id in skipList:
            skipped_chapters = skipped_chapters + 1
            if task_wrapper.can_trace():
                task_wrapper.trace(f'Skipped Chapter: {chapter_id}')
            continue

        destination_folder = os.path.join(book_folder, book_id, chapter_id)

        if os.path.exists(destination_folder):

            if clean_all:
                clean_images_folder(destination_folder, task_wrapper)

            if task_wrapper.can_trace():
                task_wrapper.trace(f'Skipped Chapter: {chapter_id}')

            skipped_chapters = skipped_chapters + 1
            continue

        task_wrapper.info('Working on Chapter: ' + chapter['chapter'])

        image_list = processor.list_images(book, chapter)

        if image_list is None:
            task_wrapper.set_failure()
            task_wrapper.error('Did not get images from processor')
            return False

        if task_wrapper.can_debug():
            task_wrapper.debug(f'Number of Images: {len(image_list)}')

        downloaded_chapters = downloaded_chapters + 1

        current_image = 0

        for image_info in image_list:

            if 'secure' in image_info and image_info['secure']:
                headers = get_headers_when_empty(headers, site_url, task_wrapper)

                if headers is None:
                    task_wrapper.critical('Headers not found, stopping')
                    task_wrapper.set_failure(True)
                    return False

            if headers_required:
                if download_secure_file(
                        image_info['src'], destination_folder,
                        image_info['file'], headers, task_wrapper):
                    downloaded_images = downloaded_images + 1
                    current_image = current_image + 1
                    task_wrapper.update_percent(100.0 * (current_image / len(image_list)))
                    modified = True
                    random_sleep(3)
                else:
                    task_wrapper.critical('Invalid Secure download, stopping')
                    break
            else:
                if download_unsecure_file(
                        image_info['src'], destination_folder,
                        image_info['file'], headers, task_wrapper):
                    downloaded_images = downloaded_images + 1
                    current_image = current_image + 1
                    task_wrapper.update_percent(100.0 * (current_image / len(image_list)))
                    modified = True
                    random_sleep(3)
                else:
                    task_wrapper.critical('Invalid Insecure download, stopping')
                    break

        # Get rid of bad files
        clean_images_folder(destination_folder, task_wrapper)

        # Get rid of junk files and fix images
        processor.clean_folder(book, chapter, destination_folder)

    if skipped_chapters > 0:
        task_wrapper.info(f'Skipped {skipped_chapters} Chapters')

    if downloaded_chapters > 0:
        task_wrapper.info(f'Downloaded {downloaded_chapters} Chapters')

    if downloaded_images > 0:
        task_wrapper.info(f'Downloaded {downloaded_images} Images')
        task_wrapper.set_worked()

    return modified


class VolumeProcessor:
    """
    This is merging the book logic into a single place for simplicity.
    """

    def __init__(self, processors, book_folder: str, task_wrapper: TaskWrapper):
        self.process_types = {}
        self.processors = processors
        self.book_folder = book_folder

        self.task_wrapper = task_wrapper

    def processor_for_id(self, processor_id: str) -> Optional["CustomDownloadInterface"]:
        for processor in self.processors:
            if processor.processor_id == processor_id:
                return processor
        return None

    def process_book(self, session: Session, book: Book, token, processor_filter: str = None, clean_all=False):

        if token is not None and token.should_stop:
            self.task_wrapper.critical('Token is triggered, stopping')
            return False

        book_id: str = book.id
        book_name: str = book.name
        book_type: str = book.processor
        book_status: str = book.active

        if book_status and book_status == 'end':
            self.task_wrapper.debug('Book series is over, stopping')
            return False

        self.task_wrapper.info('Processing: ' + book_name)

        book_result = False

        processor = self.processor_for_id(book_type)

        if processor is not None:

            if processor_filter != "*" and processor_filter != processor.processor_id:
                self.task_wrapper.info('Skipping Processor: ' + book_type)
            else:
                self.task_wrapper.info('Using ' + processor.processor_name + " Processor")
                book_result = _process_download(processor.clone_to(self.task_wrapper), token, book, self.task_wrapper,
                                                self.book_folder,
                                                clean_all)
        else:
            self.task_wrapper.critical('Unknown Processor: ' + book_type)

        # clean up
        delete_empty_folders(os.path.join(self.book_folder, book_id), self.task_wrapper)

        # update JSON for book
        if book_result:
            # root_folder = BOOK_FOLDER
            item_path = os.path.join(self.book_folder, book_id)

            # generate_json_for_folder(book_id, item_path, lib, self.task_wrapper)
            generate_db_for_folder(session, book_id, item_path, self.task_wrapper)
        return book_result

    def get_tags(self, book: Book, token) -> Optional[bool]:

        if token is not None and token.should_stop:
            self.task_wrapper.error('Token is triggered, stopping')
            return False

        if is_not_blank(book.tags):
            self.task_wrapper.info('Skipping Tags, tags already exist')
            self.task_wrapper.set_worked()
            return False

        book_name: str = book.name
        book_processor: str = book.processor

        self.task_wrapper.always('Processing: ' + book_name)

        processor = self.processor_for_id(book_processor)

        if processor is not None:
            self.task_wrapper.info('Using ' + processor.processor_name + " Processor")

            headers = None
            if processor.headers_required(book):

                site_url = ''
                if is_not_blank(book.info_url):
                    site_url = book.info_url
                elif is_not_blank(book.extra_url):
                    site_url = book.extra_url

                headers = get_headers(site_url, True, self.task_wrapper, False)

                if headers is None:
                    self.task_wrapper.error('Unable to get Headers, stopping')
                    return False

            results = processor.clone_to(self.task_wrapper).get_tags(book, headers)

            if results is not None:
                book.tags = ','.join(results)
        else:
            self.task_wrapper.add_log('Unknown Processor: ' + book_processor)
            return False

        return is_not_blank(book.tags)

    def ia_active(self, book: Book, token) -> Optional[bool]:

        if token is not None and token.should_stop:
            self.task_wrapper.error('Token is triggered, stopping')
            return None

        book_name: str = book.name
        book_processor: str = book.processor

        self.task_wrapper.always(f'Processing: {book_name}')

        processor = self.processor_for_id(book_processor)

        if processor is not None:
            self.task_wrapper.trace(f'Using {processor.get_name()} Processor')

            headers = None
            if processor.headers_required(book):

                site_url = ''
                if is_not_blank(book.info_url):
                    site_url = book.info_url
                elif is_not_blank(book.extra_url):
                    site_url = book.extra_url

                headers = get_headers(site_url, True, self.task_wrapper, False)

                if headers is None:
                    self.task_wrapper.error('Unable to acquire Headers, stopping')
                    return None

            cloned = processor.clone_to(self.task_wrapper)

            is_book_active = cloned.is_active(book, headers)

            if is_book_active is not None and not is_book_active:
                book.active = False
                return False

            return True
        else:
            self.task_wrapper.error(f'Processor: {book_processor} not found')
            return None
