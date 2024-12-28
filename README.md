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
   4. Hard Sessions
      1. For devices where typing the password can be challenging, use a pin instead.  The device must login normally first, then the user can establish a Hard Session.   
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

Also, incase you want to update to latest source code:

```bash
cd LimitedMediaServerSite
git fetch
git pull
npm install
ng build
cd ..
cd LimitedMediaServer
git fetch
git pull
pip install -r requirements.txt
```

If everything is worked, open your browser to http://serveraddress:5000/ (Linux), http://serveraddress/ (Windows), for your local windows machine it would be [http://localhost](http://localhost).

### User Setup

To begin using the server, you can log in with the default admin account:

- **Username**: `admin`  
- **Password**: `admin`

However, this default account is intentionally limited and should not be used for regular operations. Follow these steps to set up your own account and secure the server:

1. **Log in with the Default Admin Account**  
   Use the default credentials to access the system.

2. **Create a New User Account**  
   - Navigate to **Management** (Top Right Icon).  
   - Go to **User Listing**.  
   - Click **New User** (2nd Right Icon) to create a new account with the appropriate username, password, and permissions.
  
![image](https://github.com/user-attachments/assets/f78982af-95a4-4703-ba9d-6751872a663b)

3. **Log Out and Log In as the New User**  
   After creating your new user account, log out of the default `admin` account.  
   Log back in using your newly created account to ensure everything is set up correctly.

4. **Delete the Default Admin Account**  
   Once you are successfully logged in with your new account, delete the default `admin` account to improve security:  
   - Return to **User Listing** under **Management**.  
   - Select the default `admin` account and delete it.

---

By removing the default admin account, you significantly improve the security of your server.

### Property Setup  

Properties are key values stored in the database that control how the application operates. Without configuring these properties, certain features, such as viewing books or media, will not function properly.  

To set up properties:  

1. Navigate to **Management** (Top-right icon).  
2. Select **Management** > **Property Listing**.  
3. Adjust the following properties as needed:  

![image](https://github.com/user-attachments/assets/4845981e-1db1-49e1-9209-ef5f9cf56bf3)

> **Note:** A server restart is required after making property changes to apply them.

#### Key Properties  

1. **`SERVER.MEDIA.PRIMARY.FOLDER`**  
   - **Description**: The path to the folder where primary media files are stored.  
   - **Recommendation**: Store this folder on a fast disk for optimal performance.  

2. **`SERVER.MEDIA.ARCHIVE.FOLDER`**  
   - **Description**: The path to the folder where archived media files are stored.  
   - **Recommendation**: Use a separate disk for this folder to avoid overloading the primary disk.  

3. **`SERVER.MEDIA.TEMP.FOLDER`**  
   - **Description**: The path to the folder for temporary media files.  
   - **Recommendation**: Store this folder on a fast disk for quick read/write operations.  

4. **`SERVER.VOLUME.FOLDER`**  
   - **Description**: The path to the folder for volume/manga-related folders.  
   - **Recommendation**: Store this folder on a fast disk to enhance access speed.  

---

### Additional Setup

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
    python server.py
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

## Additional Arguments

### --list-plugins

The App will list the current Plugins to the command line / terminal.

### --list-processors

The App will list the current Processors to the command line / terminal.

### --skip-run

The App will stop early.  Useful for testing

### --port-override

Force the app to start on the specified Port number.

  
## Securing your Server

While it's possible to run the server with a self-signed certificate, doing so may cause issues with Mobile VR Station. Instead, a more reliable solution is to proxy your server via HTTPS to ensure a secure connection. Below, we’ll guide you through setting up NGINX as a reverse proxy on a Linux-based system, such as a Raspberry Pi.

The instructions provided will be for a linux based machince, like a Raspberry PI.

### Step -1: Free Port 80

Turn off Limited Media Server, so the Nginx install won't get angry with you holding onto port 80.

### Step 0: Generate a Self Signed Certificate

For a local server, generating a self-signed certificate is a quick and cost-effective solution. However, be warned: the browser will absolutely dislike using this certificate and will throw up warnings about the connection not being secure. This happens because the certificate isn't issued by a trusted Certificate Authority (CA), but it's the only way to make your server accessible securely without spending money on a trusted certificate — especially when dealing with a local, non-production server.

You can generate an SSL certificate pair (certificate and key) that will last for 365 days with the following command:

```bash
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365
```

After it expires, you can re-issue the command to make a new pair.

### Step 1: Install Nginx

If Nginx is not already installed, you can install it using the following command:

```bash
sudo apt update
sudo apt install nginx -y
```

### Step 2: Enable Nginx at Boot

By default, Nginx is installed as a systemd service, so you can enable it to start on boot:

```bash
sudo systemctl enable nginx
```

This ensures that Nginx starts automatically whenever your Raspberry Pi is rebooted.

### Step 3: Start Nginx

To start Nginx immediately, use the following command:

```bash
sudo systemctl start nginx
```

### Step 4: Verify Nginx is Running

Check the status of the Nginx service:
```bash
sudo systemctl status nginx
```

You should see output indicating that the service is active and running.

### Step 5: Configure Nginx as a Reverse Proxy
Next, configure Nginx to securely proxy HTTPS traffic to your Flask application. To do so, you'll need to edit the Nginx configuration file:

```bash
sudo nano /etc/nginx/sites-available/default
```

Replace the contents with this example configuration:

```text
server {
    listen 80;
    server_name limitedmediaserver;
    client_max_body_size 1600M;
    location / {
        proxy_pass http://127.0.0.1:5000; # Port your Flask app is running on
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}

server {
    listen 443 ssl;
    server_name limitedmediaserver;
    client_max_body_size 1600M;
    ssl_certificate /home/admin/ssl/cert.pem;
    ssl_certificate_key /home/admin/ssl/key.pem;

    location / {
        proxy_pass http://127.0.0.1:5000; # Port your Flask app is running on
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}

```

Note: Replace /path/to/cert.pem and /path/to/key.pem with the actual paths to your SSL certificate and key files.

Save and close the file (Ctrl+O, Enter, then Ctrl+X).

### Step 6: Test Nginx Configuration

Before applying the changes, ensure there are no syntax errors in your Nginx configuration:

```bash
sudo nginx -t
```

If the test is successful, you’ll see a message like:

```text
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### Step 7: Reload Nginx to Apply Changes

To activate the new configuration, reload Nginx:

```bash
sudo systemctl reload nginx
```

With these steps, your server should now be securely proxying HTTPS traffic to your Flask application, ensuring that Mobile VR Station and other services can connect without issues.
