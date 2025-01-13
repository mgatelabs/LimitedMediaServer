import json
import os
from datetime import date
from datetime import datetime

from flask_sqlalchemy.session import Session
from sqlalchemy import MetaData
from sqlalchemy.engine.reflection import Inspector

from app_queries import get_volume_folder
from db import db, UserGroup, User, Book, MediaFolder, MediaFileProgress, VolumeProgress, AppProperties, UserLimit, \
    UserHardSession, MediaFile, VolumeBookmark
from plugins.book_update_stats import generate_book_definitions
from text_utils import is_not_blank
from thread_utils import TaskWrapper


def validate_database_schema():
    """
    Validates if the database tables and their fields match the provided metadata.
    :return: True if all tables and fields match, False otherwise.
    """

    metadata = MetaData()
    engine = db.engine

    inspector = Inspector.from_engine(engine)
    all_tables_match = True

    for table_name, table in metadata.tables.items():
        # Check if the table exists in the database
        if table_name not in inspector.get_table_names():
            print(f"Table {table_name} is missing in the database.")
            all_tables_match = False
            continue

        # Get the columns in the table from the database
        db_columns = {col['name'] for col in inspector.get_columns(table_name)}
        meta_columns = set(table.columns.keys())

        # Check if the columns match
        missing_columns = meta_columns - db_columns
        extra_columns = db_columns - meta_columns

        if missing_columns:
            print(f"Table {table_name} is missing columns: {missing_columns}")
            all_tables_match = False
        if extra_columns:
            print(f"Table {table_name} has extra columns: {extra_columns}")
            # For now, we're just going to 'ignore' this
            # all_tables_match = False

    return all_tables_match


def backup_app_properties(output_folder, db_session: Session, tw: TaskWrapper):
    rows = db_session.query(AppProperties).all()
    file_path = os.path.join(output_folder, f"app_properties.json")
    count = 0
    with open(file_path, "w") as file:
        for row in rows:
            new_row = {"id": row.id, "value": row.value, "comment": row.comment}
            dumped_row = json.dumps(new_row)
            file.write(dumped_row + "\n")
            count += 1
    tw.debug(f'Wrote {count} App Property Records')


def restore_app_properties(restore_path: str, db_session: Session, tw: TaskWrapper):
    file_path = os.path.join(restore_path, "app_properties.json")
    count = 0
    with open(file_path, "r") as file:
        for line in file:
            row = json.loads(line.strip())
            # Check the required properties
            if 'id' in row and 'value' in row:
                comment = ''
                if 'comment' in row:
                    comment = row['comment']
                entry_item = AppProperties(id=row['id'], value=row['value'], comment=comment)
                db_session.add(entry_item)
                count += 1
        db_session.commit()

    tw.debug(f'Added {count} App Property Records')


def backup_user_groups(output_folder, db_session: Session, tw: TaskWrapper) -> dict[int, str]:
    user_group_lookup = {}

    rows = db_session.query(UserGroup).all()
    file_path = os.path.join(output_folder, f"user_groups.json")
    count = 0

    with open(file_path, "w") as file:
        for row in rows:
            user_group_lookup[row.id] = row.name
            new_row = {"name": row.name}
            if row.description is not None:
                new_row['description'] = row.description
            dumped_row = json.dumps(new_row)
            file.write(dumped_row + "\n")
            count += 1

    tw.debug(f'Wrote {count} User Group Records')

    return user_group_lookup


def restore_user_groups(restore_path: str, db_session: Session, tw: TaskWrapper) -> dict[str, int]:
    results = {}
    file_path = os.path.join(restore_path, "user_groups.json")
    count = 0
    with open(file_path, "r") as file:
        for line in file:
            row = json.loads(line.strip())
            # Check the required properties
            if 'name' in row:
                description = None
                if 'description' in row:
                    description = row['description']
                entry_item = UserGroup(name=row['name'], description=description)
                db_session.add(entry_item)
                db_session.commit()
                results[entry_item.name] = entry_item.id
                count += 1

    tw.debug(f'Added {count} User Group Records')

    return results


def backup_users(output_folder, db_session: Session, user_group_lookup: dict[int, str], tw: TaskWrapper) -> dict[
    int, str]:
    user_lookup = {}

    rows = db_session.query(User).all()
    file_path = os.path.join(output_folder, f"users.json")
    count = 0
    count_sessions = 0

    with open(file_path, "w") as file:
        for row in rows:
            user_lookup[row.id] = row.username

            new_row = {"username": row.username, "password": row.password, "features": row.features, "@limits": {}}

            # Calculate Limits
            for limit in row.limits:
                new_row['@limits'][limit.limit_type] = limit.limit_value

            # Figure out Group name
            if row.user_group_id is not None:
                new_row['@group'] = user_group_lookup[row.user_group_id]

            hard_sessions = []

            for hard_session in row.hard_sessions:
                # Skip expired tokens
                if hard_session.expired is None:
                    new_session = {'token': hard_session.token, 'pin': hard_session.pin,
                                   'created': hard_session.created.isoformat()}

                    if hard_session.last is not None:
                        new_session['last'] = hard_session.last.isoformat()

                    hard_sessions.append(new_session)
                    count_sessions = count_sessions + 1

            if len(hard_sessions) > 0:
                new_row['@sessions'] = hard_sessions

            dumped_row = json.dumps(new_row)
            file.write(dumped_row + "\n")
            count += 1

    tw.debug(f'Wrote {count} User Records')
    tw.debug(f'Wrote {count_sessions} Hard Session Records')

    return user_lookup


def restore_users(restore_path: str, db_session: Session, user_groups: dict[str, int], tw: TaskWrapper) -> dict[
    str, int]:
    results = {}
    file_path = os.path.join(restore_path, "users.json")
    count = 0
    count_sessions = 0
    with open(file_path, "r") as file:
        for line in file:
            row = json.loads(line.strip())
            # Check the required properties
            if 'username' in row and 'password' in row:
                features = 0
                if 'features' in row:
                    features = row['features']

                user_group_id = None
                if '@group' in row:
                    user_group_id = user_groups[row['@group']]

                entry_item = User(username=row['username'], password=row['password'], features=features,
                                  user_group_id=user_group_id)
                db_session.add(entry_item)
                db_session.commit()
                count += 1

                results[entry_item.username] = entry_item.id

                limit_values = row['@limits']

                if 'media' in limit_values:
                    media_limit_row = UserLimit(user_id=entry_item.id, limit_type='media',
                                                limit_value=limit_values['media'])
                    db.session.add(media_limit_row)

                if 'volume' in limit_values:
                    volume_limit_row = UserLimit(user_id=entry_item.id, limit_type='volume',
                                                 limit_value=limit_values['volume'])
                    db.session.add(volume_limit_row)

                if '@sessions' in row:
                    for session_row in row['@sessions']:
                        if 'token' in session_row and 'pin' in session_row and 'created' in session_row:
                            last = None
                            if 'last' in session_row:
                                last = datetime.fromisoformat(session_row['last'])

                            session_entry = UserHardSession(user_id=entry_item.id, token=session_row['token'],
                                                            pin=session_row['pin'],
                                                            created=datetime.fromisoformat(session_row['created']),
                                                            last=last)
                            db.session.add(session_entry)
                            count_sessions += 1
                db_session.commit()

    tw.debug(f'Added {count} User Records')
    tw.debug(f'Added {count_sessions} Hard Session Records')

    return results


def backup_books(output_folder, db_session: Session, tw: TaskWrapper):
    rows = db_session.query(Book).all()
    file_path = os.path.join(output_folder, f"books.json")
    count = 0
    with open(file_path, "w") as file:
        for row in rows:
            new_row = {"id": row.id, "name": row.name, "rating": row.rating, "style": row.style, "active": row.active,
                       "last_date": row.last_date.isoformat(),
                       "processor": row.processor}

            if row.info_url is not None:
                new_row['info_url'] = row.info_url

            if row.rss_url is not None and is_not_blank(row.rss_url):
                new_row['rss_url'] = row.rss_url

            if row.extra_url is not None and is_not_blank(row.extra_url):
                new_row['extra_url'] = row.extra_url

            if row.tags is not None:
                new_row['tags'] = row.tags

            dumped_row = json.dumps(new_row)
            file.write(dumped_row + "\n")
            count += 1

    tw.debug(f'Wrote {count} Book Records')


def restore_books(restore_path: str, db_session: Session, tw: TaskWrapper):
    file_path = os.path.join(restore_path, "books.json")
    count = 0
    with open(file_path, "r") as file:
        for line in file:
            row = json.loads(line.strip())
            if 'id' in row and 'name' in row and 'rating' in row and 'style' in row and 'active' in row and 'last_date' in row and 'processor' in row and 'last_date' in row:
                info_url = ''
                if 'info_url' in row:
                    info_url = row['info_url']

                rss_url = None
                if 'rss_url' in row and is_not_blank(row['rss_url']):
                    rss_url = row['rss_url']

                extra_url = None
                if 'extra_url' in row and is_not_blank(row['extra_url']):
                    extra_url = row['extra_url']

                skip = None
                if 'skip' in row and is_not_blank(row['skip']):
                    skip = row['skip']

                tags = None
                if 'tags' in row and is_not_blank(row['tags']):
                    tags = row['tags']

                entry_item = Book(id=row['id'], name=row['name'], rating=row['rating'],
                                  info_url=info_url, rss_url=rss_url, extra_url=extra_url, skip=skip, tags=tags,
                                  style=row['style'], active=row['active'], processor=row['processor'],
                                  last_date=date.fromisoformat(row['last_date']))
                db_session.add(entry_item)
                db_session.commit()
                count += 1
    tw.debug(f'Added {count} Book Records')


def backup_media_folders_and_files(output_folder, db_session: Session, user_group_lookup: dict[int, str],
                                   tw: TaskWrapper):
    folders = db_session.query(MediaFolder).all()
    file_path = os.path.join(output_folder, f"folders.json")
    count = 0
    count_files = 0
    with open(file_path, "w") as file:
        for row in folders:
            new_row = {"id": row.id, "name": row.name, "rating": row.rating,
                       "created": row.created.isoformat(),
                       "last_date": row.last_date.isoformat(),
                       "active": row.active}

            if row.preview:
                new_row['preview'] = row.preview

            if row.parent_id is not None:
                new_row['parent_id'] = row.parent_id

            if row.info_url is not None and is_not_blank(row.info_url):
                new_row['info_url'] = row.info_url

            if row.owning_group_id is not None:
                new_row['@group'] = user_group_lookup[row.owning_group_id]

            if row.tags is not None and is_not_blank(row.tags):
                new_row['tags'] = row.tags

            folder_files = []

            new_row['@files'] = folder_files

            for file_row in row.mediafiles:
                new_file_row = {"id": file_row.id, "filename": file_row.filename,
                                "mime_type": file_row.mime_type, "filesize": file_row.filesize,
                                "created": file_row.created.isoformat()}

                if file_row.archive:
                    new_file_row['archive'] = file_row.archive

                if file_row.preview:
                    new_file_row['preview'] = file_row.preview

                folder_files.append(new_file_row)
                count_files = count_files + 1

            dumped_row = json.dumps(new_row)
            file.write(dumped_row + "\n")
            count += 1

    tw.debug(f'Wrote {count} Folder Records')
    tw.debug(f'Wrote {count_files} File Records')


def restore_media_folders_and_files(restore_path: str, db_session: Session, user_groups: dict[str, int],
                                    tw: TaskWrapper):
    file_path = os.path.join(restore_path, "folders.json")
    count = 0
    count_files = 0
    with open(file_path, "r") as file:
        for line in file:
            row = json.loads(line.strip())
            if 'id' in row and 'name' in row and 'rating' in row and 'created' in row and 'last_date' in row and 'active' in row:
                preview = False
                if 'preview' in row:
                    preview = row['preview']
                parent_id = None
                if 'parent_id' in row:
                    parent_id = row['parent_id']
                info_url = None
                if 'info_url' in row:
                    info_url = row['info_url']
                tags = None
                if 'tags' in row:
                    tags = row['tags']
                group = None
                if '@group' in row:
                    group = user_groups[row['@group']]

                entry_item = MediaFolder(id=row['id'], name=row['name'], rating=row['rating'], preview=preview,
                                         parent_id=parent_id, info_url=info_url, active=row['active'],
                                         tags=tags, created=datetime.fromisoformat(row['created']),
                                         last_date=date.fromisoformat(row['last_date']),
                                         owning_group_id=group)

                db_session.add(entry_item)
                db_session.commit()
                count += 1

                count_files += restore_media_files(row['@files'], entry_item.id, db_session)

    tw.debug(f'Added {count} Folder Records')
    tw.debug(f'Added {count_files} File Records')


def restore_media_files(rows: list, folder_id: str, db_session: Session) -> int:
    count = 0
    for row in rows:
        if 'id' in row and 'filename' in row and 'mime_type' in row and 'created' in row:
            preview = False
            if 'preview' in row:
                preview = row['preview']
            archive = False
            if 'archive' in row:
                archive = row['archive']
            filesize = 0
            if 'filesize' in row:
                filesize = row['filesize']

            entry_item = MediaFile(id=row['id'], folder_id=folder_id, filename=row['filename'],
                                   mime_type=row['mime_type'], archive=archive, preview=preview, filesize=filesize,
                                   created=datetime.fromisoformat(row['created']))
            db_session.add(entry_item)
            db_session.commit()
            count += 1
    return count


def backup_media_progress(output_folder, db_session: Session, user_lookup: dict[int, str], tw: TaskWrapper):
    rows = db_session.query(MediaFileProgress).all()
    file_path = os.path.join(output_folder, f"progress_media.json")
    count = 0
    with open(file_path, "w") as file:
        for row in rows:
            new_row = {"@user": user_lookup[row.user_id], "file_id": row.file_id, "progress": row.progress,
                       "timestamp": row.timestamp.isoformat()}

            dumped_row = json.dumps(new_row)
            file.write(dumped_row + "\n")
            count += 1

    tw.debug(f'Wrote {count} Media Progress Records')


def restore_media_progress(restore_path: str, db_session: Session, users: dict[str, int], tw: TaskWrapper):
    file_path = os.path.join(restore_path, "progress_media.json")
    count = 0
    with open(file_path, "r") as file:
        for line in file:
            row = json.loads(line.strip())
            if '@user' in row and 'file_id' in row and 'progress' in row and 'timestamp' in row:
                entry_item = MediaFileProgress(user_id=users[row['@user']],
                                               file_id=row['file_id'],
                                               progress=row['progress'],
                                               timestamp=datetime.fromisoformat(row['timestamp']))
                db_session.add(entry_item)
                db_session.commit()
                count += 1

    tw.debug(f'Added {count} Media Progress Records')


def backup_volume_progress(output_folder, db_session: Session, user_lookup: dict[int, str], tw: TaskWrapper):
    rows = db_session.query(VolumeProgress).all()
    file_path = os.path.join(output_folder, f"progress_volume.json")
    count = 0
    with open(file_path, "w") as file:
        for row in rows:
            new_row = {"@user": user_lookup[row.user_id], "book_id": row.book_id, "chapter_id": row.chapter_id,
                       "timestamp": row.timestamp.isoformat()}

            if row.page_number is not None:
                new_row['page_number'] = row.page_number

            if row.page_percent is not None:
                new_row['page_percent'] = row.page_percent

            dumped_row = json.dumps(new_row)
            file.write(dumped_row + "\n")
            count += 1

    tw.debug(f'Wrote {count} Volume Progress Records')


def restore_volume_progress(restore_path: str, db_session: Session, users: dict[str, int], tw: TaskWrapper):
    file_path = os.path.join(restore_path, "progress_volume.json")
    count = 0
    with open(file_path, "r") as file:
        for line in file:
            row = json.loads(line.strip())
            if '@user' in row and 'book_id' in row and 'chapter_id' in row and 'timestamp' in row:

                page_number = None
                if 'page_number' in row:
                    page_number = row['page_number']

                page_percent = None
                if 'page_percent' in row:
                    page_percent = row['page_percent']

                entry_item = VolumeProgress(user_id=users[row['@user']],
                                            book_id=row['book_id'],
                                            chapter_id=row['chapter_id'],
                                            page_number=page_number,
                                            page_percent=page_percent,
                                            timestamp=datetime.fromisoformat(row['timestamp']))
                db_session.add(entry_item)
                db_session.commit()
                count += 1

    tw.debug(f'Added {count} Volume Progress Records')


def backup_volume_bookmarks(output_folder, db_session: Session, user_lookup: dict[int, str], tw: TaskWrapper):
    rows = db_session.query(VolumeBookmark).all()
    file_path = os.path.join(output_folder, f"bookmark_volume.json")
    count = 0
    with open(file_path, "w") as file:
        for row in rows:
            new_row = {"@user": user_lookup[row.user_id], "book_id": row.book_id, "chapter_id": row.chapter_id}

            if row.page_number is not None:
                new_row['page_number'] = row.page_number

            if row.page_percent is not None:
                new_row['page_percent'] = row.page_percent

            dumped_row = json.dumps(new_row)
            file.write(dumped_row + "\n")
            count += 1

    tw.debug(f'Wrote {count} Volume Bookmark Records')


def restore_volume_bookmarks(restore_path: str, db_session: Session, users: dict[str, int], tw: TaskWrapper):
    file_path = os.path.join(restore_path, "bookmark_volume.json")
    count = 0
    with open(file_path, "r") as file:
        for line in file:
            row = json.loads(line.strip())
            if '@user' in row and 'book_id' in row and 'chapter_id' in row:

                page_number = None
                if 'page_number' in row:
                    page_number = row['page_number']

                page_percent = None
                if 'page_percent' in row:
                    page_percent = row['page_percent']

                entry_item = VolumeBookmark(user_id=users[row['@user']],
                                            book_id=row['book_id'],
                                            chapter_id=row['chapter_id'],
                                            page_number=page_number,
                                            page_percent=page_percent)
                db_session.add(entry_item)
                db_session.commit()
                count += 1
    tw.debug(f'Added {count} Volume Bookmark Records')


def perform_backup(output_folder, db_session: Session, tw: TaskWrapper):
    tw.trace(f'Writing backup to {output_folder}')

    # App Properties
    tw.trace('Starting to save App Properties')
    backup_app_properties(output_folder, db_session, tw)
    tw.info('Saved App Properties')

    # User Groups
    tw.trace('Starting to save User Groups')
    user_group_lookup = backup_user_groups(output_folder, db_session, tw)
    tw.info('Saved User Groups')

    # Users
    tw.trace('Starting to save Users')
    user_lookup = backup_users(output_folder, db_session, user_group_lookup, tw)
    tw.info('Saved Users')

    # Books
    tw.trace('Starting to save Book Definitions')
    backup_books(output_folder, db_session, tw)
    tw.info('Saved Book Definitions')

    # Folders & Files
    tw.trace('Starting to save Media Folders and Files')
    backup_media_folders_and_files(output_folder, db_session, user_group_lookup, tw)
    tw.info('Saved Media Folders and Files')

    # Media Progress
    tw.trace('Starting to save Media Progress')
    backup_media_progress(output_folder, db_session, user_lookup, tw)
    tw.info('Saved Media Progress')

    # Book Progress
    tw.trace('Starting to save Volume Progress')
    backup_volume_progress(output_folder, db_session, user_lookup, tw)
    tw.info('Saved Volume Progress')

    # Book Bookmarks
    tw.trace('Starting to save Volume Bookmarks')
    backup_volume_bookmarks(output_folder, db_session, user_lookup, tw)
    tw.info('Saved Volume Bookmarks')

    tw.info("Database backup complete!")

    tw.set_worked()


def perform_restore(restore_path: str, tw: TaskWrapper):
    # Erase Everything
    tw.trace('Starting to Erase Database')
    db.drop_all()
    tw.info('Erased Database')
    # Re-create the database
    tw.trace('Starting to Create Database')
    db.create_all()
    tw.info('Created Database')

    db_session = db.session

    tw.trace('Starting to Restore App Properties')
    restore_app_properties(restore_path, db_session, tw)
    tw.info('Restored App Properties')

    tw.trace('Starting to Restore User Groups')
    user_groups = restore_user_groups(restore_path, db_session, tw)
    tw.info('Restored User Groups')

    tw.trace('Starting to Restore Users')
    users = restore_users(restore_path, db_session, user_groups, tw)
    tw.info('Restored Users')

    tw.trace('Starting to Restore Book Definitions')
    restore_books(restore_path, db_session, tw)
    tw.info('Restored Book Definitions')

    tw.trace('Starting to Restore Media Folders and Files')
    restore_media_folders_and_files(restore_path, db_session, user_groups, tw)
    tw.info('Restored Media Folders and Files')

    tw.trace('Starting to Restore Media Progress')
    restore_media_progress(restore_path, db_session, users, tw)
    tw.info('Restored Media Progress')

    tw.trace('Starting to Restore Volume Progress')
    restore_volume_progress(restore_path, db_session, users, tw)
    tw.info('Restored Volume Progress')

    tw.trace('Starting to Restore Volume Bookmarks')
    restore_volume_bookmarks(restore_path, db_session, users, tw)
    tw.info('Restored Volume Bookmarks')

    volume_folder = get_volume_folder()
    if is_not_blank(volume_folder) and os.path.isdir(volume_folder):
        tw.info('Updating Book Cache')
        generate_book_definitions(tw, None, volume_folder, False, db_session)
    else:
        tw.warn('Did not update Book Cache')

    tw.info("Database restore complete!")
