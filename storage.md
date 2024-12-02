## Storage

This app uses various ways to store your data.

- Volume (Books, Manga)
- Media (Videos, Photos and random Files)

### Volume Storage

This storage solutiuon is straight forward.  You define the property **SERVER.VOLUME.FOLDER**.  This property acts as the base for everything related to books/manga.

#### Book Folder

Once you define a Book, you should define a folder with the same ID as your book at <SERVER.VOLUME.FOLDER>/<Book_Id>

*For example*
- <SERVER.VOLUME.FOLDER>/Some_Random_Book_Title
- <SERVER.VOLUME.FOLDER>/I_Was_Once_An_Adventurer_Like_You_But_

#### Chapter Folder

Each chapter will be represented by a folder and the following naming formats are available:  "Chapter-#" or "####"

*For example*
- <SERVER.VOLUME.FOLDER>/<Book_Id>/0001
- <SERVER.VOLUME.FOLDER>/<Book_Id>/Chapter-1

#### Image Storage

Each chapter will be made up of a series of PNG images.  The Images names shall be in this format "###.png".  It is not important to have a "000.png" file, since the lowest determined number will be used as the cover image.

*For example*
- <SERVER.VOLUME.FOLDER>/<Book_Id>/0001/000.png
- <SERVER.VOLUME.FOLDER>/<Book_Id>/0001/059.png

#### Automation

There is a plugin to automate this process of downloading book chapters and correcting file names, but the current software is missing the site definitions which allow proper scraping.

Also a lot of the internet is behind cloudflare, and for the scraper to peer into those sites, you need a valid cookie from a site protected from cloudflare.  Use the Update Headers plugin.

### Media Storage

This storage solution is more of a one way street.  Once you put a file into the system, its stuck, until we come up with a SYNC method, to demigrate files.

You need to define three different properties:

**SERVER.MEDIA.PRIMARY.FOLDER**
This is where files you want quickly are stored.  This should be on a solid state drive.  Preview images are also stored here.

**SERVER.MEDIA.ARCHIVE.FOLDER**

This is where files you can wait a bit are stored.  For example, after watching a series, you could migrate the files to Archived to save space on your faster drive.

**SERVER.MEDIA.TEMP.FOLDER**

This is where work is performed for processing, it should be on a fast drive.  The content here will be blown away after it's complete.  You can freely clean the folder when the server is down.

#### Where did my files go?

When you upload a file, or import a local folder, each file is inspected, it's mime type determined and a random GUID value is assigned.

Then the file is moved to either the archived or primary storage as <GUID>.dat.

If a preview is generated for a file it will be stored as <primary_storage>/<guid>_prev.png.
