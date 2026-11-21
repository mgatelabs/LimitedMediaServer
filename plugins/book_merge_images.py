import argparse
import json
import os

from PIL import Image
from flask_sqlalchemy.session import Session

from constants import PROPERTY_SERVER_VOLUME_FOLDER
from db import Chapter
from feature_flags import MANAGE_VOLUME
from filename_utils import compress_filenames, renumber_filenames_for_compression, apply_renaming
from plugin_methods import plugin_string_arg, plugin_long_string_arg
from plugin_system import ActionBookSpecificPlugin
from thread_utils import TaskWrapper


class BookMergeImagesPlugin(ActionBookSpecificPlugin):
    """Merge multiple images in a chapter into single images, per a JSON-defined group list."""
    AI_QUICK_DESCRIPTION = ('Destructive: stacks the listed chapter images into single vertical WEBP '
                            'images, deletes the sources and renumbers the remaining files.')
    AI_LONG_DESCRIPTION = (
        'Merges groups of images within a single chapter. merge_groups is a JSON array of '
        'groups; each group must list at least 2 files of identical width, which are stacked '
        'vertically (lossless WEBP) into one image that keeps the group\'s first filename, and '
        'whose source files are then deleted. Groups with mismatched widths or missing files '
        'are skipped with a warning. After all merges, the chapter files are renumbered to '
        'remove gaps (so other filenames may change) and the chapter record in the database is '
        'updated. Book ID, Chapter ID and Merge Groups are all required. This action cannot be '
        'undone.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'bkmerge'
        self.available_to_menu = False

    def get_sort(self):
        return {'id': 'book_workers', 'sequence': 21}

    def get_category(self):
        return 'book'

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Merge Images'

    def get_action_id(self):
        return 'action.book.merge.images'

    def get_action_icon(self):
        return 'merge'

    def get_action_args(self):
        args = super().get_action_args()
        args.append(plugin_string_arg('Chapter ID', 'chapter_id', 'Chapter to process', 'bkmerge'))
        args.append(plugin_long_string_arg(
            'Merge Groups', 'merge_groups',
            'JSON array of groups, each group is a list of filenames to stack vertically. '
            'Example: [["0001.webp","0002.webp"],["0005.webp","0006.webp","0007.webp"]]',
            'bkmerge',
        ))
        return args

    def process_action_args(self, args):
        errors = []

        chapter_id = args.get('chapter_id', '').strip()
        if not chapter_id:
            errors.append('chapter_id is required')

        merge_groups_raw = args.get('merge_groups', '').strip()
        if not merge_groups_raw:
            errors.append('merge_groups is required')
        else:
            try:
                groups = json.loads(merge_groups_raw)
                if not isinstance(groups, list):
                    errors.append('merge_groups must be a JSON array')
                else:
                    for i, group in enumerate(groups):
                        if not isinstance(group, list) or len(group) < 2:
                            errors.append(f'Group {i} must be a list of at least 2 filenames')
                        elif not all(isinstance(f, str) for f in group):
                            errors.append(f'Group {i} must contain only filename strings')
            except json.JSONDecodeError as e:
                errors.append(f'merge_groups is not valid JSON: {e}')

        return errors if errors else None

    def get_feature_flags(self):
        return MANAGE_VOLUME

    def absorb_config(self, config):
        super().absorb_config(config)
        self.book_storage_folder = config[PROPERTY_SERVER_VOLUME_FOLDER]

    def create_task(self, db_session: Session, args):
        book_id = args['book_id']
        chapter_id = args['chapter_id']
        return BookMergeImagesTask(
            'BookMergeImages', f'Merge images: {book_id}/{chapter_id}',
            book_id, chapter_id, args['merge_groups'],
            self.book_storage_folder,
        )


class BookMergeImagesTask(TaskWrapper):

    def __init__(self, name: str, description: str,
                 book_id: str, chapter_id: str, merge_groups_json: str,
                 book_storage_folder: str):
        super().__init__(name, description)
        self.book_id = book_id
        self.chapter_id = chapter_id
        self.merge_groups_json = merge_groups_json
        self.book_storage_folder = book_storage_folder
        self.ref_book_id = book_id
        # This is not a simple request, it should run ASAP
        self.priority = 0

    def run(self, db_session: Session):
        chapter_folder = os.path.join(self.book_storage_folder, self.book_id, self.chapter_id)

        if not os.path.isdir(chapter_folder):
            self.error(f'Chapter folder not found: {chapter_folder}')
            self.set_failure()
            return

        chapter_row = db_session.query(Chapter).filter_by(
            book_id=self.book_id, chapter_id=self.chapter_id
        ).first()
        if chapter_row is None:
            self.error(f'Chapter {self.book_id}/{self.chapter_id} not found in database')
            self.set_failure()
            return

        merge_groups = json.loads(self.merge_groups_json)
        temp_path = os.path.join(chapter_folder, 'temp.webp')
        merged_count = 0
        total_groups = len(merge_groups)

        # --- Phase 1: perform all merges on disk, no DB touched yet ---
        for i, group in enumerate(merge_groups):
            self.update_progress((i / total_groups) * 90)
            if self.can_trace():
                self.trace(f'Group {i + 1}/{total_groups}: {group}')
            paths = [os.path.join(chapter_folder, fname) for fname in group]
            missing = [fname for fname, p in zip(group, paths) if not os.path.isfile(p)]
            if missing:
                self.warn(f'Skipping group {group}: missing files {missing}')
                continue

            try:
                images = [Image.open(p) for p in paths]
                widths = [img.width for img in images]
                if len(set(widths)) > 1:
                    for img in images:
                        img.close()
                    self.warn(f'Skipping group {group}: mismatched widths {widths}')
                    continue
                if self.can_trace():
                    self.trace(f'Widths match: {widths[0]}px, heights: {[img.height for img in images]}')
            except Exception as e:
                self.warn(f'Skipping group {group}: could not open images: {e}')
                continue

            try:
                total_height = sum(img.height for img in images)
                if self.can_trace():
                    self.trace(f'Building composite {widths[0]}x{total_height}')
                composite = Image.new('RGB', (widths[0], total_height))
                y = 0
                for img in images:
                    composite.paste(img.convert('RGB'), (0, y))
                    y += img.height
                    img.close()
                composite.save(temp_path, format='WEBP', lossless=True)
                composite.close()
                if self.can_trace():
                    self.trace(f'Composite saved to temp.webp')
            except Exception as e:
                for img in images:
                    try:
                        img.close()
                    except Exception:
                        pass
                self.error(f'Failed to build composite for group {group}: {e}')
                continue

            try:
                for p in paths:
                    if self.can_trace():
                        self.trace(f'Deleting: {os.path.basename(p)}')
                    os.unlink(p)
                os.rename(temp_path, os.path.join(chapter_folder, group[0]))
                if self.can_trace():
                    self.trace(f'Renamed temp.webp to {group[0]}')
            except Exception as e:
                self.error(f'Failed to replace files for group {group}: {e}')
                continue

            self.info(f'Merged {len(group)} images into {group[0]}')
            merged_count += 1

        if os.path.isfile(temp_path):
            os.unlink(temp_path)

        if merged_count == 0:
            return

        # --- Phase 2: renumber files to close gaps, then update DB once ---
        self.update_progress(90)
        if self.can_trace():
            self.trace('Renumbering files to close gaps')
        try:
            new_filenames, changed = renumber_filenames_for_compression(chapter_folder)
            if changed:
                if self.can_trace():
                    self.trace(f'Renaming {len(new_filenames)} files')
                apply_renaming(chapter_folder, new_filenames)
            elif self.can_trace():
                self.trace('No renaming needed')
        except ValueError as e:
            self.error(f'Renumber failed: {e}')
            return

        if self.can_trace():
            self.trace(f'Updating DB: {len(new_filenames)} images')
        chapter_row.image_names = compress_filenames(new_filenames)
        chapter_row.page_count = len(new_filenames)
        db_session.commit()
        if self.can_trace():
            self.trace('Commit done')
        self.update_progress(100)
        self.set_worked()
