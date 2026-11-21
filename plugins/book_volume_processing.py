import os
import platform
import re
import shutil
import tempfile
import time
import zipfile
from typing import Optional
from urllib.parse import urlparse

import requests
from flask_sqlalchemy.session import Session

from app_queries import get_limited_scraper_host, get_limited_scraper_port
from batch_curl import download_image_batch
from constants import BOOK_KEY_PURPOSE_ALT_VALUE
from db import Book
from file_utils import delete_empty_folders, is_text_file, read_text_file
from html_utils import adv_download_file, get_headers, get_headers_when_empty
from image_utils import clean_images_folder, is_valid_image
from plugins.book_update_stats import generate_db_for_folder
from processors.processor_core import CustomDownloadInterface
from text_utils import is_not_blank, wildcard_to_regex
from thread_utils import TaskWrapper
from utility import random_sleep


def _process_file_download(headers_required: bool, task_wrapper: TaskWrapper, image_info, destination_folder,
                           headers) -> str:
    try_count = 0

    file_output = os.path.join(destination_folder, image_info['file'])

    orig_src = image_info['src']

    has_alternative = 'alt' in image_info and image_info['alt'] is not None

    images = [orig_src]
    if has_alternative:
        images.append(image_info['alt'])
    images.append(orig_src)
    if has_alternative:
        images.append(image_info['alt'])

    for image_src in images:

        if task_wrapper.can_trace():
            task_wrapper.trace('Secure: ' + image_src)

        download_response = adv_download_file(image_src, destination_folder, image_info['file'], headers,
                                              task_wrapper)

        if not download_response.success:
            task_wrapper.trace(f'Failed to download {image_src} with status {download_response.http_status}')
        else:
            # Maybe we had a download, but it isn't right
            if is_text_file(file_output):
                txt = read_text_file(file_output)

                if txt is not None:
                    txt = txt.lower()
                    if 'www.cloudflare.com' in txt:
                        return 'CF'

                    task_wrapper.trace("Found Text File, Trying Again")
                    random_sleep(10, 7, task_wrapper)
            else:
                return 'S'

    task_wrapper.set_failure()
    task_wrapper.critical(f"Too many failed attempts, failing: {orig_src}")
    return "X"


def _process_download_http2(processor, book, chapter, image_list, destination_folder,
                             headers, task_wrapper: TaskWrapper, storage_format: str) -> dict:
    if platform.system() != 'Linux':
        return {'success': False, 'bust': False, 'modified': False, 'downloaded': 0, 'fallback': True}

    _MAX_SET = 5

    pending = [{'image_info': img, 'current_set': 0, 'complete': False} for img in image_list]
    current_round = 1
    downloaded_count = 0

    while current_round <= _MAX_SET:

        to_attempt = [p for p in pending if not p['complete'] and p['current_set'] < current_round]
        if not to_attempt:
            break

        use_alt = (current_round % 2 == 0)

        batch_items = []
        for p in to_attempt:
            img = p['image_info']
            url = img.get('alt') if use_alt else img['src']
            if not url:
                continue
            batch_items.append({'entry': p, 'url': url})

        if not batch_items:
            current_round += 1
            continue

        host_groups = {}
        for item in batch_items:
            host = urlparse(item['url']).hostname or 'unknown'
            host_groups.setdefault(host, []).append(item)

        for group in sorted(host_groups.values(), key=len, reverse=True):

            batch_downloads = [
                {'file': g['entry']['image_info']['file'], 'url': g['url']}
                for g in group
            ]
            task_wrapper.debug(
                f'HTTP/2 round {current_round}: {len(batch_downloads)} from '
                f'{urlparse(group[0]["url"]).hostname}'
            )

            download_image_batch(batch_downloads, destination_folder, headers=headers, parallel_max=16)

            for g in group:
                file_path = os.path.join(destination_folder, g['entry']['image_info']['file'])

                if not os.path.exists(file_path):
                    g['entry']['current_set'] = current_round
                    continue

                if is_text_file(file_path):
                    task_wrapper.trace(f'Text file (not image): {g["entry"]["image_info"]["file"]}')
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
                    g['entry']['current_set'] = current_round
                    continue

                if is_valid_image(file_path):
                    g['entry']['complete'] = True
                    downloaded_count += 1
                    task_wrapper.update_percent(100.0 * (downloaded_count / len(image_list)))
                else:
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
                    g['entry']['current_set'] = current_round

        current_round += 1

        if current_round <= _MAX_SET:
            remaining = [p for p in pending if not p['complete'] and p['current_set'] < current_round]
            if remaining:
                random_sleep(3, 2, task_wrapper)

    if downloaded_count == 0:
        task_wrapper.error(
            f'HTTP/2 batch: chapter {chapter["chapter"]} — 0 images after {_MAX_SET} rounds'
        )
        return {'success': False, 'bust': True, 'modified': False, 'downloaded': 0, 'fallback': False}

    task_wrapper.info(
        f'HTTP/2 batch: chapter {chapter["chapter"]} — {downloaded_count}/{len(image_list)} images'
    )
    clean_images_folder(destination_folder, task_wrapper)
    processor.clean_folder(book, chapter, destination_folder, storage_format)
    return {'success': True, 'bust': False, 'modified': True, 'downloaded': downloaded_count, 'fallback': False}


def _process_download(processor, token, book: Book, task_wrapper, book_folder: str, storage_format: str,
                      clean_all: bool = False, chapter_url: str = None, chapter_name: str = None):
    headers = None

    headers_required = processor.headers_required(book)

    site_url = ''
    if is_not_blank(book.info_url):
        site_url = book.info_url
    elif is_not_blank(book.extra_url):
        site_url = book.extra_url

    skipList = []
    regex_list = []
    if is_not_blank(book.skip):
        skipList = [value.strip() for value in book.skip.split(',')]
        for skip_item in skipList:
            if "*" in skip_item:
                skip_regex = wildcard_to_regex(skip_item)
                if task_wrapper.can_trace():
                    task_wrapper.trace(f'Regex: {skip_regex}')
                regex_list.append(skip_regex)

    if headers_required:
        headers = get_headers_when_empty(None, site_url, task_wrapper)
        if headers is None:
            return False

    book_id = book.id

    if task_wrapper.can_trace():
        task_wrapper.trace(f'Book {book_id}')

    if chapter_url is not None and chapter_name is not None:
        chapters = [{'chapter': chapter_name, 'href': chapter_url}]
        task_wrapper.info(f'Forced Chapter: {chapter_name}')
    else:
        chapters = processor.list_chapters(book, headers)
        task_wrapper.info(f'Chapters Found: {len(chapters)}')

    if len(chapters) == 0:
        task_wrapper.set_warning()
        task_wrapper.warn('No chapters returned from service')

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
        elif len(regex_list) > 0:
            should_skip = False
            for skip_regex in regex_list:
                compiled = re.compile(skip_regex)
                result = compiled.match(chapter_id)
                if result:
                    skipped_chapters = skipped_chapters + 1
                    should_skip = True
                    if task_wrapper.can_trace():
                        task_wrapper.trace(f'Skipped Chapter: {chapter_id}')
                    break
            if should_skip:
                continue

        destination_folder = os.path.join(book_folder, book_id, chapter_id)

        if os.path.exists(destination_folder):

            if clean_all:
                clean_images_folder(destination_folder, task_wrapper)

            if task_wrapper.can_trace():
                task_wrapper.trace(f'Skipped Chapter: {chapter_id}')

            skipped_chapters = skipped_chapters + 1
            continue

        task_wrapper.debug('Working on Chapter: ' + chapter['chapter'])

        image_list = processor.list_images(book, chapter, headers)

        if image_list is None or len(image_list) == 0:
            task_wrapper.set_failure()
            task_wrapper.error(f'Chapter: {chapter["chapter"]} - Processor did not return images')
            return False

        task_wrapper.info(f'Chapter: {chapter["chapter"]} ({len(image_list)} images)')

        downloaded_chapters = downloaded_chapters + 1

        has_secure = any('secure' in img and img['secure'] for img in image_list)

        if processor.allow_http2() and not has_secure:
            h2_result = _process_download_http2(
                processor, book, chapter, image_list,
                destination_folder, headers, task_wrapper, storage_format
            )
            if h2_result.get('fallback'):
                pass  # not Linux — fall through to sequential loop below
            elif h2_result['bust']:
                task_wrapper.set_failure()
                return False
            else:
                if h2_result['modified']:
                    modified = True
                downloaded_images += h2_result['downloaded']
                task_wrapper.update_percent(100.0)
                continue

        current_image = 0

        check_image = True
        stop_download = False
        for image_info in image_list:

            if headers_required:
                pre_headers = headers
                headers = get_headers_when_empty(None, site_url, task_wrapper, chapter['href'])
                if headers is None:
                    headers = pre_headers

            if 'secure' in image_info and image_info['secure']:
                ref_url = site_url
                if 'ref' in image_info:
                    ref_url = image_info['ref']
                    headers = None
                headers = get_headers_when_empty(headers, ref_url, task_wrapper)

                if headers is None:
                    task_wrapper.critical('Headers not found, stopping')
                    task_wrapper.set_failure(True)
                    return False

            min_duration = 1
            delay = 3
            if 'delay' in image_info:
                delay = image_info['delay']
                if delay < 3:
                    delay = 3
                min_duration = delay - 2

            if headers is not None:
                headers['accept'] = 'image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5'

            resu = _process_file_download(headers_required, task_wrapper, image_info, destination_folder, headers)

            downloaded_images = downloaded_images + 1
            current_image = current_image + 1

            task_wrapper.update_percent(100.0 * (current_image / len(image_list)))

            modified = True
            random_sleep(delay, min_duration)

            if resu == 'CF':
                task_wrapper.error('Detected Cloudflare in the response, stopping...')
                break
            elif resu == 'F':
                continue
            elif resu == 'X':
                task_wrapper.error('Failed to download image, skipping item')
                # stop_download = True
                # break
            elif resu == 'E':
                break

            if check_image:
                check_image = False
                image_path = os.path.join(destination_folder, image_info['file'])
                if not is_valid_image(image_path):
                    task_wrapper.critical('1st file is not an image, stopping')
                    task_wrapper.info(chapter['href'])
                    break

        # Get rid of bad files
        clean_images_folder(destination_folder, task_wrapper)

        # Get rid of junk files and fix images
        processor.clean_folder(book, chapter, destination_folder, storage_format)

        if stop_download:
            break

    if skipped_chapters > 0:
        task_wrapper.info(f'Skipped {skipped_chapters} Chapters')

    if downloaded_chapters > 0:
        task_wrapper.info(f'Downloaded {downloaded_chapters} Chapters')

    if downloaded_images > 0:
        task_wrapper.info(f'Downloaded {downloaded_images} Images')
        task_wrapper.set_worked()

    return modified


def _list_local_chapters(book_folder: str, book_id: str) -> list:
    """
    List the chapter slabs already downloaded for a book.

    A chapter slab is a direct sub-folder of book_folder/book_id whose name is
    a pure number (optionally with a decimal, e.g. ``0001`` or ``0032.1``).
    Dot-prefixed entries (e.g. ``.previews``) and non-numeric folders are
    ignored.  Returns the slab names, sorted.
    """
    book_path = os.path.join(book_folder, book_id)

    if not os.path.isdir(book_path):
        return []

    chapters = []
    for entry in os.listdir(book_path):
        if entry.startswith('.'):
            continue
        if not re.match(r'^\d+(\.\d+)?$', entry):
            continue
        if os.path.isdir(os.path.join(book_path, entry)):
            chapters.append(entry)

    return sorted(chapters)


def _build_remote_known(chapters: list, exclude: str = None) -> str:
    """
    Join a list of chapter slabs into the ``known`` comma-separated string the
    limited scraper understands.  Optionally drop a single slab first (used for
    the single-chapter path, where the target is the only one we do NOT already own).
    """
    if exclude is not None:
        chapters = [c for c in chapters if c != exclude]
    return ",".join(sorted(chapters))


def _strip_non_images(chapter_path: str, task_wrapper: TaskWrapper) -> None:
    """
    Remove any file in ``chapter_path`` that is not a valid image.

    The limited scraper ships a ``manifest.json`` (and may ship other metadata)
    alongside each chapter's images.  ``clean_images_folder`` treats a file it
    cannot open as an image as a failure, so the non-image files must be gone
    first.
    """
    for filename in os.listdir(chapter_path):
        file_path = os.path.join(chapter_path, filename)
        if not os.path.isfile(file_path):
            continue
        if not is_valid_image(file_path):
            task_wrapper.debug(f'Removing non-image file: {filename}')
            try:
                os.remove(file_path)
            except OSError:
                pass


def _extract_remote_zip(zip_path: str, book: Book, book_folder: str, processor, storage_format: str,
                        task_wrapper: TaskWrapper) -> bool:
    """
    Extract a downloaded remote-scraper ZIP into the book folder and run the
    normal per-chapter cleanup on each chapter that arrived.

    The ZIP's top-level entries are the new chapter slab directories, each
    holding zero-padded page images plus a ``manifest.json``.  Returns True if
    at least one chapter was extracted.
    """
    book_path = os.path.join(book_folder, book.id)
    os.makedirs(book_path, exist_ok=True)

    modified = False

    with zipfile.ZipFile(zip_path, 'r') as zf:
        top_dirs = set(name.split('/', 1)[0] for name in zf.namelist() if '/' in name)
        zf.extractall(book_path)

        for chapter_slab in sorted(top_dirs):
            chapter_path = os.path.join(book_path, chapter_slab)
            if not os.path.isdir(chapter_path):
                continue

            _strip_non_images(chapter_path, task_wrapper)

            task_wrapper.info(f'Remote chapter: {chapter_slab}')

            # Get rid of bad files
            clean_images_folder(chapter_path, task_wrapper)

            # Get rid of junk files and fix images
            processor.clean_folder(book, {'chapter': chapter_slab, 'href': None}, chapter_path, storage_format)

            modified = True

    return modified


def _remote_download_and_extract(server_url: str, ticket_id: str, book: Book, book_folder: str, processor,
                                 storage_format: str, task_wrapper: TaskWrapper) -> bool:
    """
    Download the finished remote job's ZIP (one-shot) to a temp folder, extract
    it into the book folder, then clean up the temp folder.  Returns True if at
    least one chapter was added.
    """
    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp(prefix='remote_scrape_')
        zip_path = os.path.join(tmp_dir, f'{ticket_id}.zip')

        try:
            dl = requests.get(f'{server_url}/jobs/{ticket_id}/download', stream=True, timeout=(10, 120))
        except Exception as e:
            task_wrapper.critical(f'Failed to download remote result: {e}')
            task_wrapper.set_failure()
            return False

        if dl.status_code != 200:
            task_wrapper.critical(f'Remote download returned {dl.status_code}')
            task_wrapper.set_failure()
            return False

        with open(zip_path, 'wb') as f:
            for chunk in dl.iter_content(chunk_size=8 * 1024 * 1024):
                f.write(chunk)

        task_wrapper.info('Downloaded remote scrape result')

        return _extract_remote_zip(zip_path, book, book_folder, processor, storage_format, task_wrapper)

    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _process_remote_call(processor, token, book: Book, task_wrapper: TaskWrapper, book_folder: str,
                         storage_format: str, chapter_url: str = None, chapter_name: str = None) -> bool:
    """
    Hand a book (or a single chapter of it) off to the limited media scraper.

    The scraper receives the series URL plus the list of chapter slabs we
    already own (``known``) and returns, as a ZIP, only the chapters we do not
    have.  For a single-chapter request, every locally-owned slab except the
    target is put in ``known`` so the target is the new one returned.  Returns
    True when at least one chapter was added.
    """
    host = get_limited_scraper_host()
    if not is_not_blank(host):
        task_wrapper.critical('Limited scraper host is not configured')
        task_wrapper.set_failure()
        return False

    server_url = f'http://{host}:{get_limited_scraper_port()}'

    if is_not_blank(book.info_url):
        url = book.info_url
    elif is_not_blank(book.extra_url):
        url = book.extra_url
    else:
        task_wrapper.critical('Book has no info_url or extra_url for remote processing')
        task_wrapper.set_failure()
        return False

    local_chapters = _list_local_chapters(book_folder, book.id)

    if chapter_name is not None:
        known = _build_remote_known(local_chapters, exclude=chapter_name)
        task_wrapper.info(f'Remote single chapter: {chapter_name} (skip {len(known.split(",")) if known else 0} known chapters)')
    else:
        known = _build_remote_known(local_chapters)
        task_wrapper.info(f'Remote full book (skip {len(known.split(",")) if known else 0} known chapters)')

    payload = {
        'task_type': 'scrape',
        'plugin_id': processor.processor_id,
        'url': url,
        'known': known,
        'alt': book.get_keys_for_purpose(BOOK_KEY_PURPOSE_ALT_VALUE),
    }

    task_wrapper.info(f'Submitting remote scrape to {server_url}')

    try:
        submit_resp = requests.post(f'{server_url}/jobs', json=payload, timeout=30)
    except Exception as e:
        task_wrapper.critical(f'Failed to submit remote job: {e}')
        task_wrapper.set_failure()
        return False

    if submit_resp.status_code != 202:
        task_wrapper.critical(f'Remote submission returned {submit_resp.status_code}: {submit_resp.text}')
        task_wrapper.set_failure()
        return False

    try:
        ticket_id = submit_resp.json().get('ticket_id')
    except Exception:
        ticket_id = None

    if not ticket_id:
        task_wrapper.critical('No ticket_id in remote submission response')
        task_wrapper.set_failure()
        return False

    poll_interval = 3.0
    consecutive_errors = 0
    max_consecutive_errors = 10

    while True:
        time.sleep(poll_interval)

        if token is not None and token.should_stop:
            task_wrapper.critical('Token is triggered, stopping')
            return False

        try:
            status_resp = requests.get(f'{server_url}/jobs/{ticket_id}', timeout=30)
            if status_resp.status_code != 200:
                raise RuntimeError(f'status returned {status_resp.status_code}')
            data = status_resp.json()
        except Exception as e:
            consecutive_errors += 1
            task_wrapper.warn(f'Remote status poll failed ({consecutive_errors}/{max_consecutive_errors}): {e}')
            if consecutive_errors >= max_consecutive_errors:
                task_wrapper.critical('Too many consecutive remote poll failures, stopping')
                task_wrapper.set_failure()
                return False
            continue

        consecutive_errors = 0

        progress = data.get('progress')
        subprogress = data.get('subprogress')

        if progress is not None:
            task_wrapper.update_progress(float(progress))
        if subprogress is not None:
            task_wrapper.update_percent(float(subprogress))

        status = data.get('status')
        has_data = data.get('has_data')

        if task_wrapper.can_trace():
            task_wrapper.trace(f'Remote status: {status}')

        if status == 'finished':
            if not has_data:
                task_wrapper.info('Remote scrape finished with no new chapters (all known)')
                return False
            result = _remote_download_and_extract(server_url, ticket_id, book, book_folder, processor,
                                                  storage_format, task_wrapper)
            if result:
                task_wrapper.set_worked()
            return result
        elif status == 'failure':
            task_wrapper.critical(f"Remote job failed: {data.get('error', 'unknown error')}")
            task_wrapper.set_failure()
            return False


class VolumeProcessor:
    """
    This is merging the book logic into a single place for simplicity.
    """

    def __init__(self, processors, book_folder: str, storage_format, task_wrapper: TaskWrapper):
        self.process_types = {}
        self.processors = processors
        self.book_folder = book_folder
        self.storage_format = storage_format

        self.task_wrapper = task_wrapper

    def processor_for_id(self, processor_id: str) -> Optional["CustomDownloadInterface"]:
        for processor in self.processors:
            if processor.processor_id == processor_id:
                return processor
        return None

    def process_book(self, session: Session, book: Book, token, clean_all=False):

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
            self.task_wrapper.info('Using ' + processor.processor_name + " Processor")
            if processor.is_remote_process():
                book_result = _process_remote_call(processor.clone_to(self.task_wrapper), token, book,
                                                   self.task_wrapper, self.book_folder, self.storage_format)
            else:
                book_result = _process_download(processor.clone_to(self.task_wrapper), token, book,
                                                self.task_wrapper, self.book_folder, self.storage_format, clean_all)
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

    def process_book_chapter(self, session: Session, book: Book, token, chapter_url, chapter_name, clean_all=False):

        if token is not None and token.should_stop:
            self.task_wrapper.critical('Token is triggered, stopping')
            return False

        book_name: str = book.name
        book_type: str = book.processor

        self.task_wrapper.info('Processing: ' + book_name)

        processor = self.processor_for_id(book_type)

        if processor is not None:
            self.task_wrapper.info('Using ' + processor.processor_name + " Processor")
            if processor.is_remote_process():
                _process_remote_call(processor.clone_to(self.task_wrapper), token, book, self.task_wrapper,
                                     self.book_folder, self.storage_format, chapter_url, chapter_name)
            else:
                _process_download(processor.clone_to(self.task_wrapper), token, book, self.task_wrapper,
                                  self.book_folder, self.storage_format, clean_all, chapter_url, chapter_name)
        else:
            self.task_wrapper.critical('Unknown Processor: ' + book_type)

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
