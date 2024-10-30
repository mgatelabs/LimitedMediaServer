# Limited Media Server

The Server part of Limited Media Server.  The site is located [here](https://github.com/mgatelabs/LimitedMediaServerSite).

## What is Limited Media Server?

Limited Media Server is a platform for sharing media and manga in a *local network environment*.

A common use case for this sever, is accessing it via a VPN to read manga or watch videos on the go, all streaming from your home.

### Notice
Do not expose this server to the general internet, you have been warned.  Always put it behind a VPN.

### Cool tip

I built this server to take advantage of the new Raspberry PI 5 feature to run on NVMe drives, which offers a substantial speed boost.

## Features

1. User Management
   1. Manage Users
   2. Control what content is visible
   3. Control the features each user has access to
2. Platform management
   1. Configure most features via the browser (Properties)
      1. Binding IP address
      2. PORT #
      3. Authentication timeout
      4. Primary Media Folder path
      5. Archived Media Folder path
      6. Temp Media Folder path
      7. Volume Folder path
   2. Configure security groups
      1. Lock media to certain groups
3. Volume Features (Manga)
   1. Organize your manga and track what you have read
   2. It has features to scrape websites, but this edition has been altered to remove those features
3. Media Features
   1. View Videos, Music & Images
   2. All files are accessed via a ID
   3. Access to media is verified before delivering content
   4. Download from YouTube (Make sure yt-dlp is installed)
      1. Download music as a single file or split by track.  Cover art is turned into the icon.
      2. De-duplicate music basic upon the name
      3. Assign MP3 tags
   5. Download from M3u8 sources (Make sure ffmpeg is installed)
4. Security features
   1. Volumes and Media Folders can have a rating limit
      2. G, PG, PG-13, R-17, Rx, Unrated
   3. Security groups
      1. Users can inherit a security group, groups can be assigned to a folder
5. Admin notices
   1. APP Admins don't have to follow the Security Group rules
6. Plugins
   1. The system can discover and utilize plugins to extend basic functionality
   2. Plugins can use Arguments or Properties

## Basic Setup

Open bash or a terminal on the target server to your desired root folder.

```bash
git clone https://github.com/mgatelabs/LimitedMediaServer.git
git clone https://github.com/mgatelabs/LimitedMediaServerSite.git
cd LimitedMediaServerSite
npm install
ng build
cd ..
cd LimitedMediaServer
pip install -r requirements.txt
python server.py
```

If everything is working, open your browser to http://serveraddress:18080/

### User setup

You can now log in as the user 'admin' with the password 'admin'.  The default account was created to not be very useful.

Use the Management (Top Right Icon) > User Listing > New User (2nd Right Icon).  After making a real account, logout and back in as your new user.  Please delete the existing ADMIN account.

### Property Setup

Use the Management (Top Right Icon) > Management > Property Listing

From here you need to adjust the following properties.  Server restart is required after making property changes.

#### SERVER.MEDIA.PRIMARY.FOLDER
This needs to be the path to folder where the primary media files will be stored.  It should be on a fast disk.

#### SERVER.MEDIA.ARCHIVE.FOLDER
This needs to be the path to folder where the archived media files will be stored.  This should be on a different disk.

#### SERVER.MEDIA.TEMP.FOLDER
This needs to be the path to folder where the temp media files will be stored.  This should be on a fast disk.

#### SERVER.VOLUME.FOLDER
This needs to be the path to folder where volume/manga folders will be stored.  This should be on a fast disk.

### Additional Setup

The server can be used with self-signed certificates for some added security.  When executing the server, add the following arguments:
1. -ssl_cert PATH_TO_cert.pem
2. -ssl_key PATH_TO_key.pem

## Advanced Development Configuration

### As a Raspberry PI 5 media/development server

#### Restarting from the User Interface
Use Management (Top Right Icon) use Restart or Stop server.  When you press *Restart Server*, the process will end with the code 69, nice.

#### Backend/Service setup

This is an example script used on a Raspberry Pi 5 to control the execution of the server.  On restart, it will do the following:
1. Download Site Source Code
2. Build Site from Source
3. Download Latest Site Source Code
4. Install requirements
5. Update the DB is needed
6. Start the server

In this example this script it was placed in the `/home/admin` folder as `run_limitedmediaserver.sh`.  Also, the projects were cloned into `/home/admin`.

```shell
#!/bin/bash

echo "Limited Media Server Start!"

while true; do
    
    cd LimitedMediaServerSite
    git fetch
    # Check if the current branch is behind the remote
    if [[ $(git status -uno | grep 'Your branch is behind') ]]; then
        git pull
        npm install
        ng build
    else
        echo "The current branch is up to date with its remote."
       # Add any other actions you want to perform if the repo is up to date
    fi
    cd ..
    
    cd LimitedMediaServer
    git fetch
    # Check if the current branch is behind the remote
    if [[ $(git status -uno | grep 'Your branch is behind') ]]; then
        git pull
        pip install -r requirements.txt --break-system-packages
        /home/admin/.local/bin/alembic upgrade head
    else
        echo "The current branch is up to date with its remote."
       # Add any other actions you want to perform if the repo is up to date
    fi    

    # Call your Python program here and capture its output
    python server.py -ssl_cert /home/admin/ssl/cert.pem -ssl_key /home/admin/ssl/key.pem
    result=$?

    echo "Result: $result"
    if [ "$result" = "69" ]; then
        echo "Result is 69, looping..."
    else
        echo "Result is not 69, exiting loop."
        break
    fi

    cd ..
done

echo "Limited Media Server End!"

```

With this file in place, you would be able to create a service to start automatically.

## Hardware Configuration

This is what I built

1. Raspberry PI 5 with NVMe shield
2. NVMe drive with minimal 2+ TB of storage
3. External drive compatible with RP5 with 7+ TB storage
4. RP5 is wired into the network
5. RP5 configured for SSH access with no desktop

## Known Issues and Fixes

1. iOS Won't Play Audio / Video
   1. It seems like the new privacy settings are blocking the app from sending cookies.  Turn off "Prevent Cross-Site Tracking" in Safari settings and it will work.
