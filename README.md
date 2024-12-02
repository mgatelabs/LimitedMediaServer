# Limited Media Server

This is the back-end (Server) part of Limited Media Server.  The site portion is located [here](https://github.com/mgatelabs/LimitedMediaServerSite).

## What is Limited Media Server?

Limited Media Server is a platform for sharing media and manga in a *local network environment*.

A common use case for this sever, is accessing it via a VPN to read manga or watch videos on the go, all streaming from your home.  A 2nd use case is running the server locally on your desktop to stream content to compitable apps, such as Mobile VR Station.

### Notice
Do not expose this server to the general internet, you have been warned.  It should always be ran on a private network, and if internet access is desired, put it behind a VPN.

### Cool tip

I built this server to take advantage of the new Raspberry PI 5 feature to run on NVMe drives, which offers a substantial speed boost and larger storage.

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

### Example Media Browser

![image](https://github.com/user-attachments/assets/56eab409-3375-40b7-9312-dc4cbd167817)=

### Example Split Media Browser

![image](https://github.com/user-attachments/assets/cefcb7ed-afa2-45ab-92b2-f76788fd486d)

In this example the user could select items on the left side to delete or move them to the right side.

### Example Process Detail

![image](https://github.com/user-attachments/assets/91fbc363-fa54-42bc-8a51-c55ac42c86e9)

### How to access Server Management

![image](https://github.com/user-attachments/assets/bb33e2e0-f2fd-4876-b6df-a5a355e14ad6)

1. User Listing lets you Add, Edit and Remove users
2. Group Listing lets you setup a security group, which users can have a group and media folders can have a group
3. Property Listings lets you change how the server works.  Paths to folders, ports and other settings.

## Requirements

### Installing Python

To run the server, you need Python 3.x installed. Follow these steps to install Python:

1. **Download Python**  
   Visit the official Python website and download the latest version of Python 3.x:  
   [Python Downloads](https://www.python.org/downloads/)

2. **Install Python**  
   During the installation process:  
   - Select **"Install for all users"** to ensure Python is available for the entire machine, not just your user account.  
   - Check the box to **"Add Python to PATH"** at the beginning of the installation wizard. This step is crucial for Python to work seamlessly from the command line.  

3. **Verify Installation**  
   After the installation is complete, verify it by opening a terminal or Command Prompt and running the following commands:  
```bash
   python --version
```
or (depending on your system setup):

```bash
python3 --version
```
You should see the installed version of Python printed.

### Setting Up Node.js, NPM, and Angular CLI for Angular 17 Development

To develop with Angular 17, you need Node.js, NPM, and Angular CLI (`ng`) installed. Follow the steps below to set up your environment:

---

#### 1. **Install Node.js (Includes NPM)**

1. **Download Node.js**  
   Visit the official Node.js website and download the **LTS** version for your platform:  
   [Node.js Downloads](https://nodejs.org/)

2. **Install Node.js**  
   During the installation:
   - Check the option to install **"Tools for Native Modules"** if prompted (this ensures compatibility with certain npm packages).  
   - Confirm that Node.js is added to the system **PATH** (this is typically done automatically).

3. **Verify Installation**  
   Open a terminal or Command Prompt and run:
```bash
node -v
```

This will print the installed Node.js version. Ensure it is a version supported by Angular 17 (16.x or later).

4. Check NPM

NPM is bundled with Node.js. Verify it by running:

```bash
npm -v
```

This will print the installed NPM version.

#### 2. Install Angular CLI (ng)

1. Install the CLI

Use NPM to globally install Angular CLI:

```bash
npm install -g @angular/cli
```

2. Verify the Installation

Confirm that Angular CLI is installed by running:

```bash
ng version
```

This command displays the installed Angular CLI version and ensures your setup is working.
Ensure the CLI version supports Angular 17 (you may need the latest Angular CLI).

3. Update NPM (Optional)

If you encounter issues with NPM or want to ensure you're using the latest version, update NPM:

```bash
npm install -g npm@latest
```

Verify the update with:

```bash
npm -v
```

### Installing Git (For Easy Updates)

Git is essential for version control in development. Follow these steps to install and configure Git:

---

#### 1. **Download Git**

Visit the official Git website to download the latest version of Git for your operating system:  
[Git Downloads](https://git-scm.com/downloads)

---

#### 2. **Install Git**

1. **Run the Installer**  
   - Open the downloaded installer file and follow the setup wizard.

2. **Configuration Options**  
   During the installation, you will encounter several configuration options. Recommended settings include:
   - **Select Components**: Leave all default options checked.
   - **Adjust Path Environment**: Choose **"Git from the command line and also from 3rd-party software"** (recommended for most users).
   - **Default Editor**: Select your preferred text editor (e.g., Vim, Visual Studio Code, Notepad++).
   - **Configuring Line Endings**: Choose **"Checkout Windows-style, commit Unix-style line endings"** for cross-platform projects.
   - **Extra Options**: Enable **"Enable symbolic links"** if needed for your projects.

3. **Complete the Installation**  
   Click **Finish** to complete the installation.

---

#### 3. **Verify Installation**

1. Open a terminal or Command Prompt and run:
```bash
git --version
```

You should see the installed version of Git.

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

## Self Signed Certificates

If you want to run with HTTPS and you are using a raspberry pi, use the following command from the terminal to generate a key pair:

```
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365
```

Then in the script to load the service (seen later) you can point it to the files on disk via the following parameters:

```
python server.py -ssl_cert /home/admin/ssl/cert.pem -ssl_key /home/admin/ssl/key.pem
```

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

In this example this script it was placed in the `/home/admin` folder as `limitedmediaserver_script.sh`.  Also, the projects were cloned into `/home/admin`.

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

### Setting up a Service

#### Create your script
```shell
chmod +x /home/admin/limitedmediaserver_script.sh
```
#### Create a systemd service unit file

```shell
sudo nano /etc/systemd/system/limitedmediaserver.service
```

#### Edit the service file

```text
[Unit]
Description=Limited Media Server
After=network.target

[Service]
ExecStart=/home/admin/limitedmediaserver_script.sh
WorkingDirectory=/home/admin/
StandardOutput=inherit
StandardError=inherit
Restart=always
User=admin

[Install]
WantedBy=multi-user.target
```

#### Enable the service

```shell
sudo systemctl daemon-reload                      # Reload systemd manager configuration
sudo systemctl enable limitedmediaserver.service  # Enable the service to start on boot
sudo systemctl start limitedmediaserver.service   # Start the service now
```

#### Control the service

```shell
sudo systemctl start limitedmediaserver.service    # Start the service
sudo systemctl stop limitedmediaserver.service     # Stop the service
sudo systemctl restart limitedmediaserver.service  # Restart the service
sudo systemctl status limitedmediaserver.service   # Check the status of the service
```

#### Check logs

```shell
journalctl -u limitedmediaserver.service
```

#### Live Logs

```shell
journalctl --follow -u limitedmediaserver.service
```

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
