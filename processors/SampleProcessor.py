from bs4 import BeautifulSoup

from db import Book
from html_utils import download_secure_text
from image_utils import convert_images_to_png
from number_utils import pad_integer_number
from processors.processor_core import CustomDownloadInterface
from thread_utils import TaskWrapper


def extract_image_sources(url, task_wrapper: TaskWrapper, headers=None):
    # Download the webpage
    response = download_secure_text(url, headers, task_wrapper)

    # Parse HTML content
    soup = BeautifulSoup(response, 'html.parser')

    # Find the images
    img_items = soup.select('#readerarea img')

    # The result
    image_sources = []

    # Give each image an index, so it's numbered
    image_index = 1

    for img in img_items:
        src = img.get('src').strip()
        alt = img.get('alt')
        task_wrapper.trace(src)
        task_wrapper.trace(alt)
        # Skip anything with discord in the title
        if src and (not alt or not alt.startswith('discord')):
            # This site mostly has JPG images, so save it as JPG, but everything will be converted later.
            image_sources.append({"src": src, "file": pad_integer_number(image_index, 4) + ".jpg"})
            # Update the index
            image_index = image_index + 1

    return image_sources


class SampleProcessor(CustomDownloadInterface):

    def __init__(self, task_wrapper: TaskWrapper = None):
        super().__init__('sample', 'Sample', task_wrapper)

    def list_chapters(self, definition: Book, headers=None):
        """
        From the Book's definition, extract the URLs for each chapter
        :param definition:
        :param headers:
        :return: list of {'chapter': 'chapter number (0 padded) or like chapter-X', 'href': 'link to chapter'}
        """
        return []

    def list_images(self, definition: Book, chapter, headers=None):
        """
        Given a book and chapter definition return a list of images
        :param definition:
        :param chapter:
        :param headers:
        :return: list of {"src":"web link", "file": "resulting file name, pad it, like 0012.jpg"}
        """

        return []

    def clean_folder(self, definition: Book, chapter, path):
        # Generally all images should be PNG, so lets just convert everything.  Also remove any pesky metadata.
        convert_images_to_png(path, self.task_wrapper)

    def get_tags(self, definition: Book, headers=None):
        """
        In a real implementation, you need to access a web page, extract the tags and return them as a string list.
        :param definition:
        :param headers:
        :return: None or a list of strings
        """

        return None

    def headers_required(self, definition: Book):
        """
        Return True if the website is protected and should use Fancy Google Chrome CURL
        :param definition:
        :return:
        """
        return False
