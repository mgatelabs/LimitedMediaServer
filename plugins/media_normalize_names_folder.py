import argparse
import os.path
import re

from flask_sqlalchemy.session import Session

from feature_flags import MANAGE_MEDIA
from media_queries import find_folder_by_id, find_files_in_folder, find_folders_in_folder
from plugin_methods import PLUGIN_VALUES_Y_N, plugin_select_arg
from plugin_system import ActionMediaFolderPlugin
from text_utils import is_blank
from thread_utils import TaskWrapper

# An episode identifier (S followed by digits, E followed by digits) with an optional single
# A-Z trailing character (e.g. S01E01, S01E13J), optionally followed by an underscore and any
# suffix.
EPISODE_NAME_RE = re.compile(r'^(S(\d+))(E(\d+))([A-Z]?)?(_.+)?$')


def normalize_episode_name(filename: str) -> str:
    """
    Normalize an episode-named file: zero-pad the season and episode numbers to two digits
    (S1E3 becomes S01E03), keep an optional single A-Z trailing character (S01E13J stays
    S01E13J), and strip a "_..." suffix, keeping the extension if one is present.
    The name is returned unchanged when it is blank or does not start with an S##E##
    identifier.
    """
    if is_blank(filename):
        return filename
    base, ext = os.path.splitext(filename)
    match = EPISODE_NAME_RE.match(base)
    if match is None:
        return filename
    season = int(match.group(2))
    episode = int(match.group(4))
    letter = match.group(5) or ''
    return f'S{season:02d}E{episode:02d}{letter}' + ext


def collect_subfolder_ids(folder_id: str, db_session):
    """
    Breadth-first collect the ids of all descendant folders of the given folder.
    A seen-set guards against cycles in the parent links.
    """
    subfolder_ids = []
    seen = {folder_id}
    queue = [folder_id]
    while queue:
        current_id = queue.pop(0)
        for sub in find_folders_in_folder(current_id, db_session=db_session):
            if sub.id in seen:
                continue
            seen.add(sub.id)
            subfolder_ids.append(sub.id)
            queue.append(sub.id)
    return subfolder_ids


class NormalizeNamesForFolderPlugin(ActionMediaFolderPlugin):
    """
    Normalize episode-named files in a single media folder: zero-pad the season/episode
    numbers, keep an optional single A-Z trailing character, and strip a "_..." suffix.
    """
    AI_QUICK_DESCRIPTION = ('Normalizes episode-named files in a media folder (optionally every '
                            'subfolder beneath it): strips a "_..." suffix, zero-pads '
                            'season/episode (S1E3 becomes S01E03), and keeps an optional single '
                            'A-Z trailing character (S01E13J_SUB.mp4 becomes S01E13J.mp4), '
                            'keeping the extension when present.')
    AI_LONG_DESCRIPTION = (
        'Renames virtual file records inside a media folder and, when the Include Subfolders '
        'option is set, every folder nested beneath it. Any file whose name starts '
        'with an episode identifier (S followed by digits, E followed by digits, with an '
        'optional single A-Z trailing character such as S01E13J) is normalized: the season and '
        'episode numbers are zero-padded to two digits (S1E3.mp4 becomes S01E03.mp4), a '
        '"_..." suffix is stripped, and the trailing character is kept '
        '(S01E13J_SUB.mp4 becomes S01E13J.mp4); the file extension is kept when one exists and '
        'the name may also have none. For example S01E23_anything.mp4 becomes S01E23.mp4 and '
        'S01E23_sub becomes S01E23. This reverts the postfixes added by other actions such as '
        'Burn Subtitles (default "_sub") or encode ("_enc"). Files that do not start with an '
        'S##E## identifier are left untouched, and no duplicate checking is performed because '
        'names are virtual. Only the stored filename is updated - the underlying data file '
        '(which is stored by file ID) and previews are unaffected, so nothing is moved on disk. '
        'The Include Subfolders option (default No) extends the operation to every folder '
        'recursively nested beneath the selected folder. The task reports the total renamed and '
        'processed, plus a per-folder breakdown when subfolders are included.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'mednormfol'

    def get_sort(self):
        return {'id': 'media_normalize_names', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Normalize File Names'

    def get_action_id(self):
        return 'action.folder.normalize.names'

    def get_action_icon(self):
        return 'title'

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def get_action_args(self):
        result = super().get_action_args()
        result.append(plugin_select_arg('Include Subfolders', 'include_sub', 'n', PLUGIN_VALUES_Y_N,
                                        'Also normalize file names in every folder nested beneath '
                                        'the selected folder (recursively).',
                                        prefix_lang_id='mednormfol'))
        return result

    def process_action_args(self, args):
        results = []
        if 'folder_id' not in args or not args['folder_id']:
            results.append('folder_id is required')
        return results if results else None

    def create_task(self, db_session: Session, args):
        include_sub = str(args.get('include_sub', 'n')).lower() == 'y'
        return NormalizeNamesFolderTask(
            "NormalizeNames",
            f'Normalize names: {args.get("folder_name", args["folder_id"])}',
            args['folder_id'],
            include_sub,
        )


class NormalizeNamesFolderTask(TaskWrapper):
    def __init__(self, name, description, folder_id: str, include_sub: bool = False):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.include_sub = include_sub

    def run(self, db_session: Session):
        folder = find_folder_by_id(self.folder_id, db_session)
        if folder is None:
            self.critical('Folder not found in database.')
            self.set_failure()
            return

        if self.include_sub:
            folder_ids = [self.folder_id] + collect_subfolder_ids(self.folder_id, db_session)
        else:
            folder_ids = [self.folder_id]

        # Gather every (folder, files) pair up front so overall progress stays accurate.
        targets = []
        for fid in folder_ids:
            sub_folder = folder if fid == self.folder_id else find_folder_by_id(fid, db_session)
            if sub_folder is None:
                continue
            targets.append((sub_folder, list(find_files_in_folder(fid, db_session=db_session))))

        total = sum(len(files) for _, files in targets)
        if total == 0:
            self.info(f'Folder "{folder.name}" contains no files.')
            self.set_worked()
            return

        renamed = 0
        processed = 0
        for sub_folder, files in targets:
            if self.is_cancelled:
                break
            folder_renamed = 0
            for file_row in files:
                if self.is_cancelled:
                    self.info('Leaving early')
                    break
                processed = processed + 1
                self.update_progress((processed / total) * 100.0)

                new_name = normalize_episode_name(file_row.filename)
                if new_name != file_row.filename:
                    self.info(f'{file_row.filename} -> {new_name}')
                    file_row.filename = new_name
                    renamed = renamed + 1
                    folder_renamed = folder_renamed + 1

            if self.include_sub:
                self.info(f'Folder "{sub_folder.name}": renamed {folder_renamed} of {len(files)} file(s)')

        if renamed > 0:
            db_session.commit()

        if self.include_sub:
            self.info(f'Renamed {renamed} of {total} file(s) in {len(targets)} folder(s)')
        else:
            self.info(f'Renamed {renamed} of {total} file(s)')
        self.set_worked()
