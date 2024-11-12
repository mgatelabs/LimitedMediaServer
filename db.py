import datetime
import uuid

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, ForeignKey
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import object_session, relationship
from werkzeug.security import generate_password_hash

from feature_flags import MANAGE_APP, MANAGE_PROCESSES, UTILITY_PLUGINS, GENERAL_PLUGINS, VIEW_PROCESSES

# Initialize SQLAlchemy
db = SQLAlchemy()


# UserGroup model
class UserGroup(db.Model):
    __tablename__ = 'user_groups'

    id = db.Column(db.Integer, primary_key=True)  # Auto-generated ID
    name = db.Column(db.String(50), nullable=False)  # Group name, required
    description = db.Column(db.String(1024), nullable=True)  # Group description, optional


# User model
class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)  # Primary key
    username = db.Column(db.String(150), unique=True, nullable=False)  # Unique username, required
    password = db.Column(db.String(200), nullable=False)  # Password, required
    features = db.Column(db.Integer, nullable=False)  # Features, required

    # Relationship to UserLimit with cascade delete
    limits = relationship('UserLimit', back_populates='user', cascade='all, delete-orphan')

    # Foreign key to UserGroup
    user_group_id = db.Column(db.Integer, ForeignKey('user_groups.id'), nullable=True)  # Optional UserGroup
    user_group = db.relationship('UserGroup', backref='users')


# UserLimit model
class UserLimit(db.Model):
    __tablename__ = 'user_limits'

    id = db.Column(db.Integer, primary_key=True)  # Primary key
    user_id = db.Column(db.Integer, ForeignKey('users.id'), nullable=False)  # Foreign key to User
    limit_type = db.Column(db.String(15), nullable=False)  # Type of limit (e.g., 'book', 'series', 'media')
    limit_value = db.Column(db.Integer, nullable=False)  # Limit value

    # Relationship back to User
    user = relationship('User', back_populates='limits')

    # Ensure unique limit types per user
    __table_args__ = (db.UniqueConstraint('user_id', 'limit_type', name='user_limit_uc'),)


# Book model
class Book(db.Model):
    __tablename__ = 'books'

    id = db.Column(db.String(128), primary_key=True, nullable=False)  # Unique ID, string, not null
    name = db.Column(db.String(256), nullable=False)  # Name of the book, string, not null
    rating = db.Column(db.Integer, nullable=False, default=200)  # Rating, required, default 200

    info_url = db.Column(db.String(1024), nullable=False)  # Info URL, required
    rss_url = db.Column(db.String(1024), nullable=True)  # Optional RSS URL
    extra_url = db.Column(db.String(1024), nullable=True)  # Extra URL, optional

    style = db.Column(db.Enum('P', 'S', name='style_type'), nullable=False, default='P')  # Style, required, default 'P'

    active = db.Column(db.Boolean, nullable=False)  # Active status, required
    processor = db.Column(db.String(24), nullable=False)  # Processor ID, required

    skip = db.Column(db.String(1024), nullable=True)  # Comma-separated list of names to skip, optional
    tags = db.Column(db.String(1024), nullable=True)  # Comma-separated list of tags, optional

    cover = db.Column(db.String(32), nullable=True)  # Cover image ID, optional
    start_chapter = db.Column(db.String(32), nullable=True)  # First chapter ID, optional
    first_chapter = db.Column(db.String(32), nullable=True)  # First chapter ID, optional
    last_chapter = db.Column(db.String(32), nullable=True)  # Last chapter ID, optional
    last_date = db.Column(db.Date, nullable=False, default=datetime.date(2005, 1, 1))  # Last update date, required

    # Establish relationship with Chapter
    chapters = db.relationship("Chapter", back_populates="book", cascade="all, delete-orphan", lazy=True)


# Chapter model
class Chapter(db.Model):
    __tablename__ = 'chapters'

    book_id = db.Column(db.String(128), db.ForeignKey('books.id'), nullable=False)  # Foreign key to Book table
    chapter_id = db.Column(db.String(32), nullable=False)  # Chapter ID, part of composite key

    page_count = db.Column(db.Integer, nullable=False)  # Page count, required
    image_names = db.Column(db.Text, nullable=False)  # Image names, required

    sequence = db.Column(db.Integer, nullable=False)  # Sequence number, required
    date = db.Column(db.Date, nullable=False, default=datetime.date(2005, 1, 1))  # Date, required, default 1/1/2005

    # Composite primary key (book_id + chapter_id)
    __table_args__ = (
        db.PrimaryKeyConstraint('book_id', 'chapter_id'),
    )

    # Establish the back-population from Chapter to Book
    book = db.relationship("Book", back_populates="chapters")

    def remove_image(self, image_name):
        # Split the comma-separated image names into a list
        image_list = self.image_names.split(',')

        # Check if the image_name is in the list
        if image_name not in image_list:
            return False

        # Remove the image_name from the list
        image_list.remove(image_name)

        # Update the image_names by joining the list back into a comma-separated string
        self.image_names = ','.join(image_list)

        # Update the page_count based on the remaining images
        self.page_count = len(image_list)

        return True


class VolumeBookmark(db.Model):
    __tablename__ = 'volume_bookmarks'

    id = db.Column(db.Integer, primary_key=True)  # Primary key
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False)  # Foreign key to User table
    book_id = db.Column(db.String(128), db.ForeignKey('books.id', ondelete='CASCADE'),
                        nullable=False)  # Foreign key to Book table
    chapter_id = db.Column(db.String(32), nullable=False)  # Chapter ID, required
    page_number = db.Column(db.Integer, nullable=True)  # Page number, optional
    page_percent = db.Column(db.Float, nullable=True)  # Page percent, optional

    # Relationships
    user = db.relationship('User', backref=db.backref('volume_bookmarks', cascade='all, delete-orphan'))
    book = db.relationship('Book', backref=db.backref('volume_bookmarks', cascade='all, delete-orphan'))


class VolumeProgress(db.Model):
    __tablename__ = 'volume_progress'

    id = db.Column(db.Integer, primary_key=True)  # Primary key
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False)  # Foreign key to User table
    book_id = db.Column(db.String(128), db.ForeignKey('books.id', ondelete='CASCADE'),
                        nullable=False)  # Foreign key to Book table
    chapter_id = db.Column(db.String(32), nullable=False)  # Chapter ID, required
    page_number = db.Column(db.Integer, nullable=True)  # Page number, optional
    page_percent = db.Column(db.Float, nullable=True)  # Page percent, optional
    timestamp = db.Column(db.DateTime, nullable=False)  # Recent event datetime, optional

    # Relationships
    user = db.relationship('User', backref=db.backref('volume_progress', cascade='all, delete-orphan'))
    book = db.relationship('Book', backref=db.backref('volume_progress', cascade='all, delete-orphan'))
    # chapter = db.relationship('Chapter', backref=db.backref('volume_progress', cascade='all, delete-orphan'))

    # Composite unique constraint to prevent duplicate progress records
    __table_args__ = (
        db.UniqueConstraint('user_id', 'book_id', 'chapter_id', name='_user_book_chapter_uc'),
    )


class AppProperties(db.Model):
    __tablename__ = 'app_properties'

    id = db.Column(db.String(64), primary_key=True, unique=True, nullable=False)  # Unique ID, string, not null
    value = db.Column(db.Text, nullable=False)  # Value, non-null
    comment = db.Column(db.Text, nullable=True)  # Comment, optional


# Media

# Media Folder model
class MediaFolder(db.Model):
    __tablename__ = 'mediafolders'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(256), nullable=False)  # Name of the book, string, not null
    rating = db.Column(db.Integer, nullable=False, default=200)  # Rating, required, default 200
    preview = db.Column(db.Boolean, nullable=False, default=False)  # Does this have a preview?

    # Self-referential foreign key for parent folder
    parent_id = db.Column(db.String(36), db.ForeignKey('mediafolders.id'), nullable=True)
    parent = db.relationship("MediaFolder", remote_side=[id], backref=db.backref('children', cascade='all'))

    info_url = db.Column(db.String(1024), nullable=True)  # Info URL, required

    active = db.Column(db.Boolean, nullable=False)  # Active status, required

    tags = db.Column(db.String(1024), nullable=True)  # Comma-separated list of tags, optional

    created = db.Column(db.DateTime(timezone=True), nullable=False,
                        server_default=db.func.now())  # Auto store current UTC time

    last_date = db.Column(db.Date, nullable=False, default=datetime.date(2005, 1, 1))  # Last update date, required

    # Establish relationship with Chapter
    mediafiles = db.relationship("MediaFile", back_populates="mediafolder", cascade="all", lazy=True)

    # Foreign key for optional owning group
    owning_group_id = db.Column(db.Integer, db.ForeignKey('user_groups.id'), nullable=True)
    owning_group = db.relationship("UserGroup", backref="mediafolders")


@event.listens_for(MediaFolder, 'before_delete')
def prevent_deletion_if_children(mapper, connection, target):
    # Check if there are any related MediaFile objects
    session = object_session(target)
    if session.query(MediaFile).filter_by(folder_id=target.id).count() > 0:
        raise IntegrityError(None, None, "Cannot delete MediaFolder with existing MediaFile records.")


class MediaFile(db.Model):
    __tablename__ = 'mediafiles'

    # The random file id
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Link to parent
    folder_id = db.Column(db.String(36), db.ForeignKey('mediafolders.id'), nullable=False)  # Foreign key to Book table

    filename = db.Column(db.String(256), nullable=False)  # Name of the book, string, not null
    mime_type = db.Column(db.String(255), nullable=False)  # What type of content
    archive = db.Column(db.Boolean, nullable=False)  # Is this an archived file?
    preview = db.Column(db.Boolean, nullable=False, default=False)  # Does this have a preview?
    filesize = db.Column(db.Integer, nullable=False)  # Filesize, optional

    created = db.Column(db.DateTime(timezone=True), nullable=False,
                        server_default=db.func.now())  # Auto store current UTC time

    # Establish the back-population from Chapter to Book
    mediafolder = db.relationship("MediaFolder", back_populates="mediafiles")

    # Single relationship to MediaFileProgress
    progress_records = db.relationship(
        'MediaFileProgress',
        back_populates='file',
        cascade='all, delete-orphan'
    )


class MediaFileProgress(db.Model):
    __tablename__ = 'media_file_progress'

    id = db.Column(db.Integer, primary_key=True)  # Primary key
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False)  # Foreign key to User table
    file_id = db.Column(db.String(36), db.ForeignKey('mediafiles.id', ondelete='CASCADE'),
                        nullable=False)  # Foreign key to Book table
    progress = db.Column(db.Float, nullable=False)  # Page percent, optional
    timestamp = db.Column(db.DateTime, nullable=False)  # Recent event datetime, optional

    # Define relationships
    user = db.relationship('User', backref=db.backref('media_file_progress', cascade='all, delete-orphan'))
    file = db.relationship('MediaFile', back_populates='progress_records')


# Initialize the database
def init_db(app):
    db.init_app(app)
    with app.app_context():
        db.create_all()

        # Check if any users exist
        if not User.query.first():
            # Create the default admin user, if necessary
            admin_user = User(
                username='admin',
                password=generate_password_hash('admin'),
                features=MANAGE_APP | MANAGE_PROCESSES | GENERAL_PLUGINS | UTILITY_PLUGINS | VIEW_PROCESSES,
            )
            db.session.add(admin_user)
            db.session.commit()
