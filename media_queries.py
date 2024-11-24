from datetime import datetime
from typing import Optional, List, Tuple

from flask_sqlalchemy.session import Session
from sqlalchemy import and_
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import joinedload

from db import MediaFolder, MediaFile, db, MediaFileProgress
from text_utils import is_not_blank


# Insert or Update Folder
def insert_folder(parent_id: str, name: str, rating: int, info_url: str, tags: str, active: bool,
                  group_id: Optional[int],
                  db_session: Session = db.session):
    """
    Insert a new folder or update an existing one.

    Args:
        db_session (Session): The database session to use.
        parent_id (str): The ID of the parent folder. Use an empty string for root folders.
        name (str): The name of the folder.
        rating (int): The rating of the folder.
        info_url (str): The URL with more information about the folder.
        tags (str): Tags associated with the folder.
        active (bool): Whether the folder is active.

    Returns:
        None
    """
    if len(parent_id) == 0:
        parent_id = None

    new_folder = MediaFolder(
        name=name,
        rating=rating,
        preview=False,
        parent_id=parent_id,
        info_url=info_url,
        tags=tags,
        owning_group_id=group_id,
        active=active
    )

    db_session.add(new_folder)
    db_session.commit()


# Update Folder
def update_folder(folder_id: str, name: str, rating: int, info_url: str, tags: str, active: bool,
                  group_id: Optional[int],
                  db_session: Session = db.session) -> bool:
    """
    Update an existing folder.

    Args:
        :param folder_id: The ID of the folder to update.
        :param name: The new name of the folder.
        :param rating: The new rating of the folder.
        :param info_url: The new URL with more information about the folder.
        :param tags: The new tags associated with the folder.
        :param active: Whether the folder is active.
        :param group_id:
        :param db_session: The database session to use.

    Returns:
        bool: True if the folder was updated, False if not found.

    """
    try:
        existing_folder = db_session.query(MediaFolder).filter_by(id=folder_id).one()

        existing_folder.name = name
        existing_folder.rating = rating
        existing_folder.info_url = info_url
        existing_folder.tags = tags
        existing_folder.owning_group_id = group_id
        existing_folder.active = active

        db_session.commit()

        return True
    except NoResultFound:
        return False


def _build_folders_in_folders_query(folder_id: str, db_session: Session = None, filter_text: str = None,
                                    max_rating: int = 0):
    if db_session is not None:
        query_builder = db_session.query(MediaFolder)
    else:
        query_builder = MediaFolder.query

    if is_not_blank(filter_text):
        query_builder = query_builder.filter(MediaFolder.name.like(f'%{filter_text}%'))

    if max_rating <= 200:
        query_builder = query_builder.filter(MediaFolder.rating <= max_rating)

    query_builder = query_builder.filter(MediaFolder.parent_id == folder_id)

    return query_builder


# Find Folders in Folder
def find_folders_in_folder(folder_id: str, filter_text: str = None, max_limit: int = 0, query_offset: int = 0,
                           query_limit: int = 0, sort_column=MediaFolder.name, sort_descending: bool = False,
                           db_session: Session = None) -> Optional[List[type[MediaFolder]]]:
    """
    Find all subfolders in a specific folder.

    Args:
        :param folder_id: The ID of the parent folder.
        :param db_session: The database session to use. Defaults to None.
        :param filter_text: Text that will be searched for
        :param max_limit:
        :param query_offset:
        :param query_limit:
        :param sort_column:
        :param sort_descending:
    Returns:
        Optional[List[MediaFolder]]: A list of subfolder MediaFolder objects or None if not found.

    """

    query = _build_folders_in_folders_query(folder_id, db_session, filter_text, max_limit)

    if sort_descending:
        query = query.order_by(sort_column.desc(), MediaFolder.id.desc())
    else:
        query = query.order_by(sort_column.asc(), MediaFolder.id.asc())

    if query_offset > 0:
        query = query.offset(query_offset)

    if query_limit > 0:
        query = query.limit(query_limit)

    return query.all()


def count_folders_in_folder(folder_id: str, filter_text: str = None, max_rating: int = 0,
                            db_session: Session = None) -> int:
    """
    Count the number of subfolders in a specific folder.

    Args:
        :param folder_id: The ID of the parent folder.
        :param db_session:  The database session to use. Defaults to None.
        :param filter_text: (Optional) Text string must exist in entry name
        :param max_rating: 0 - 200 rating limit
    Returns:
        Count of the numer of folders in a given folder.

    """

    return _build_folders_in_folders_query(folder_id, db_session, filter_text, max_rating).count()


# Find Folder by ID
def find_folder_by_id(folder_id: str, db_session: Session = None) -> Optional[MediaFolder]:
    """
    Find a media folder by its ID.

    Args:
        folder_id (str): The ID of the folder to find.
        db_session (Session, optional): The database session to use. Defaults to None.

    Returns:
        Optional[MediaFolder]: The found MediaFolder object or None if not found.
    """
    if db_session is not None:
        return db_session.query(MediaFolder).filter_by(id=folder_id).first()
    else:
        return MediaFolder.query.filter_by(id=folder_id).first()


def _build_root_folders_query(filter_text: str = None, max_limit: int = 0, db_session: Session = None):
    if db_session is not None:
        query_builder = db_session.query(MediaFolder)
    else:
        query_builder = MediaFolder.query

    if is_not_blank(filter_text):
        query_builder = query_builder.filter(MediaFolder.name.like(f'%{filter_text}%'))

    query_builder = query_builder.filter(MediaFolder.rating <= max_limit)

    query_builder = query_builder.filter(MediaFolder.parent_id.is_(None))

    return query_builder


def find_all_folders(db_session: Session = db.session):
    return db_session.query(MediaFolder).all()


# Find Root Folders
def find_root_folders(filter_text: str = None, max_limit: int = 0, query_offset: int = 0, query_limit: int = 0,
                      sort_column=MediaFolder.name, sort_descending: bool = False, db_session: Session = None) -> \
        Optional[
            List[type[MediaFolder]]]:
    """
    Find all root folders (folders without a parent).

    Args:
        :param filter_text:
        :param max_limit:
        :param query_offset:
        :param query_limit:
        :param sort_column:
        :param sort_descending:
        :param db_session (Session, optional): The database session to use. Defaults to None.
    Returns:
        Optional[List[MediaFolder]]: A list of root MediaFolder objects or None if not found.

    """

    query = _build_root_folders_query(filter_text, max_limit, db_session)

    if sort_descending:
        query = query.order_by(sort_column.desc(), MediaFolder.id.desc())
    else:
        query = query.order_by(sort_column.asc(), MediaFolder.id.asc())

    if query_offset > 0:
        query = query.offset(query_offset)

    if query_limit > 0:
        query = query.limit(query_limit)

    return query.all()


def count_root_folders(filter_text: str = None, max_limit: int = 0, db_session: Session = None) -> int:
    """
    Find all root folders (folders without a parent).

    Args:
        max_limit: 0 - 200 rating limit
        filter_text (str): Optional text to filter by
        db_session (Session, optional): The database session to use. Defaults to None.

    Returns:
        count of number of rows
    """

    query = _build_root_folders_query(filter_text, max_limit, db_session)

    return query.count()


# File Methods

def insert_file(folder_id: str, filename: str, mime_type: str, archive: bool, preview: bool, file_size: int,
                created: datetime, db_session: Session = db.session) -> MediaFile:
    """
    Insert a new file or update an existing one.

    Args:
        folder_id (str): The ID of the folder containing the file.
        filename (str): The name of the file.
        mime_type (str): The MIME type of the file.
        archive (bool): Whether the file is archived.
        preview (bool): Whether the file has a preview.
        file_size (int): The size of the file in bytes.
        created (datetime): The creation date of the file.
        db_session (Session, optional): The database session to use.

    Returns:
        MediaFile: The inserted or updated MediaFile object.
    """
    new_file = MediaFile(
        folder_id=folder_id,
        filename=filename,
        mime_type=mime_type,
        archive=archive,
        preview=preview,
        filesize=file_size,
        created=created
    )

    db_session.add(new_file)
    db_session.commit()

    return new_file


def update_file(file_id: str, filename: str, mime_type: str, db_session: Session = db.session) -> bool:
    """
    Update an existing file.

    Args:
        file_id (str): The ID of the file to update.
        filename (str): The new name of the file.
        mime_type (str): The new MIME type of the file.
        db_session (Session, optional): The database session to use.

    Returns:
        bool: True if the file was updated, False if not found.
    """
    try:
        existing_file = db_session.query(MediaFile).filter_by(id=file_id).one()

        existing_file.filename = filename
        existing_file.mime_type = mime_type

        db_session.commit()

        return True
    except NoResultFound:
        return False


# Find File by ID
def find_file_by_id(file_id: str, db_session: Session = None) -> Optional[MediaFile]:
    """
    Find a media file by its ID.

    Args:
        file_id (str): The ID of the file to find.
        db_session (Session, optional): The database session to use. Defaults to None.

    Returns:
        Optional[MediaFile]: The found MediaFile object or None if not found.
    """
    if db_session is not None:
        return db_session.query(MediaFile).filter_by(id=file_id).first()
    else:
        return MediaFile.query.filter_by(id=file_id).first()


# Find File by Name in folder
def find_file_by_filename(file_name: str, folder_id: str, db_session: Session = None) -> Optional[MediaFile]:
    """
    Find a media file by its name in a given folder.

    Args:
        file_name (str): The name the file to find.
        folder_id (str): The folder to look in.
        db_session (Session, optional): The database session to use. Defaults to None.

    Returns:
        Optional[MediaFile]: The found MediaFile object or None if not found.
    """
    if db_session is not None:
        return db_session.query(MediaFile).filter(MediaFile.filename == file_name).filter(
            MediaFile.folder_id == folder_id).first()
    else:
        return MediaFile.query.filter(MediaFile.filename == file_name).filter(MediaFile.folder_id == folder_id).first()


def _build_files_in_folders_query(folder_id: str, filter_text: str = None, db_session: Session = None):
    if db_session is not None:
        query_builder = db_session.query(MediaFile)
    else:
        query_builder = MediaFile.query

    if is_not_blank(filter_text):
        query_builder = query_builder.filter(MediaFile.filename.like(f'%{filter_text}%'))

    query_builder = query_builder.filter(MediaFile.folder_id == folder_id)

    return query_builder


# Find Files in Folder
def find_files_in_folder(folder_id: str, filter_text: str = None, query_offset: int = 0, query_limit: int = 0,
                         sort_column=MediaFile.filename, sort_descending: bool = False, db_session: Session = None,
                         uid: Optional[int] = None) -> Optional[List[type[MediaFile]]]:
    """
    Find all files in a specific folder.

    Args:
        :param folder_id (str): The ID of the folder to search in.
        :param filter_text (str, optional): Text that will be searched for. Defaults to None.
        :param query_offset (int, optional): The number of rows to skip. Defaults to 0.
        :param query_limit (int): The maximum number of rows to return. Defaults to unlimited.
        :param sort_column:
        :param sort_descending:
        :param db_session (Session, optional): The database session to use. Defaults to None.
        :param uid: User identify

    Returns:
        Optional[List[MediaFile]]: A list of MediaFile objects in the folder or None if not found.
    """

    query = _build_files_in_folders_query(folder_id, filter_text, db_session)

    if uid is not None:
        query = query.outerjoin(MediaFileProgress, and_(MediaFile.id == MediaFileProgress.file_id,
                                                        MediaFileProgress.user_id == uid)).options(
            joinedload(MediaFile.progress_records))

    if sort_descending:
        query = query.order_by(sort_column.desc(), MediaFile.id.desc())
    else:
        query = query.order_by(sort_column.asc(), MediaFile.id.asc())

    if query_offset > 0:
        query = query.offset(query_offset)

    if query_limit > 0:
        query = query.limit(query_limit)

    return query.all()


def count_files_in_folder(folder_id: str, filter_text: str = None, db_session: Session = None) -> int:
    """
    Find all files in a specific folder.

    Args:
        :param folder_id: The ID of the folder to search in.
        :param filter_text: The database session to use. Defaults to None.
        :param db_session: The database session to use. Defaults to None.
    Returns:
        Optional[List[MediaFile]]: A list of MediaFile objects in the folder or None if not found.
    """

    query = _build_files_in_folders_query(folder_id, filter_text, db_session)

    return query.count()


# Find MimeType Files in Folder
def find_files_in_folder_with_mime(folder_id: str, mime_type: str, db_session: Session = None) -> Optional[
    List[type[MediaFile]]]:
    """
    Find all files in a specific folder.

    Args:
        :param folder_id: The ID of the folder to search in.
        :param param mime_type:  The mime type to find
        :param db_session: The database session to use. Defaults to None.

    Returns:
        Optional[List[MediaFile]]: A list of MediaFile objects in the folder or None if not found.

    """
    if db_session is not None:
        return db_session.query(MediaFile).filter_by(folder_id=folder_id, mime_type=mime_type).order_by(
            MediaFile.filename, MediaFile.created).all()
    else:
        return MediaFile.query.filter_by(folder_id=folder_id, mime_type=mime_type).order_by(MediaFile.filename,
                                                                                            MediaFile.created).all()  # Find MimeType Files in Folder


def find_files_in_two_folders_with_mime(folder_id: str, folder_id_2: str, mime_type: str, db_session: Session = None) -> \
        Optional[List[type[MediaFile]]]:
    """
    Find all files in a specific folder.

    Args:
        :param folder_id: The ID of the folder to search in.
        :param folder_id_2: The Alternative ID of the folder to search in.
        :param mime_type:  The mime type to find
        :param db_session: The database session to use. Defaults to None.

    Returns:
        Optional[List[MediaFile]]: A list of MediaFile objects in the folder or None if not found.

    """
    if db_session is not None:
        return db_session.query(MediaFile).filter(MediaFile.folder_id.in_([folder_id, folder_id_2]),
                                                  MediaFile.mime_type == mime_type).order_by(MediaFile.filename,
                                                                                             MediaFile.created).all()
    else:
        return MediaFile.query.filter(MediaFile.folder_id.in_([folder_id, folder_id_2]),
                                      MediaFile.mime_type == mime_type).order_by(MediaFile.filename,
                                                                                 MediaFile.created).all()


# Find Missing File Previews in Folder
def find_missing_file_previews_in_folder(folder_id: str, db_session: Session = None) -> Optional[List[type[MediaFile]]]:
    """
    Find all files in a specific folder that are missing previews.

    Args:
        folder_id (str): The ID of the folder to search in.
        db_session (Session, optional): The database session to use. Defaults to None.

    Returns:
        Optional[List[MediaFile]]: A list of MediaFile objects missing previews or None if not found.
    """
    if db_session is not None:
        return db_session.query(MediaFile).filter_by(folder_id=folder_id, preview=False).order_by(
            MediaFile.filename).all()
    else:
        return MediaFile.query.filter_by(folder_id=folder_id, preview=False).order_by(MediaFile.filename).all()


# Find Missing File Previews in Folder
def find_missing_file_previews(db_session: Session = None) -> Optional[List[type[MediaFile]]]:
    """
    Find all files that are missing previews.

    Args:
        db_session (Session, optional): The database session to use. Defaults to None.

    Returns:
        Optional[List[MediaFile]]: A list of MediaFile objects missing previews or None if not found.
    """
    if db_session is not None:
        return db_session.query(MediaFile).filter_by(preview=False).order_by(MediaFile.folder_id,
                                                                             MediaFile.filename).all()
    else:
        return MediaFile.query.filter_by(preview=False).order_by(MediaFile.folder_id, MediaFile.filename).all()


# Progress

def find_progress_entry(user_id: int, file_id: str) -> Optional[MediaFileProgress]:
    """
    Try to find an entry for a media file
    :param user_id:
    :param file_id:
    :return:
    """
    return MediaFileProgress.query.filter_by(user_id=user_id, file_id=file_id).first()  # Progress


def find_progress_entries(user_id: int, max_rating: int = 200, db_session: Session = db.session) -> Optional[
    List[Tuple[MediaFileProgress, str]]]:
    """
    Try to find entries for a media file with the associated folder name.
    :param user_id: ID of the user.
    :param max_rating: Maximum folder rating.
    :param db_session: Database session.
    :return: List of tuples with MediaFileProgress entries and their associated MediaFolder names.
    """

    query = (
        db_session.query(MediaFileProgress, MediaFolder.name)
        .join(MediaFile, MediaFileProgress.file_id == MediaFile.id)
        .join(MediaFolder, MediaFile.folder_id == MediaFolder.id)
        .filter(
            MediaFileProgress.user_id == user_id,
            MediaFolder.rating < 200,  # Exclude records where rating is >= 200
            MediaFolder.rating <= max_rating,  # Exclude records they can't see
        )
        .order_by(MediaFileProgress.timestamp.desc(), MediaFileProgress.file_id)
        .limit(35)  # Limit to 50 records
    )

    return query.all()


# Function to insert or update a book record
def upsert_progress(user_id: int, file_id: str, progress: float, timestamp: datetime, db_session: Session = db.session):
    """
    This will add/update a recent entry, so we can track how far a user has progressed
    :param user_id:
    :param file_id:
    :param progress:
    :param timestamp:
    :param db_session:
    :return:
    """
    try:
        # Try to get the book with the specified ID
        existing_progress = db_session.query(MediaFileProgress).filter_by(user_id=user_id, file_id=file_id).one()

        existing_progress.progress = progress
        existing_progress.timestamp = timestamp

        # Commit the updates
        db_session.commit()

    except NoResultFound:
        # If no book is found, create a new record
        new_progress = MediaFileProgress(
            user_id=user_id,
            file_id=file_id,
            progress=progress,
            timestamp=timestamp
        )

        # Add and commit the new book
        db_session.add(new_progress)
        db_session.commit()
