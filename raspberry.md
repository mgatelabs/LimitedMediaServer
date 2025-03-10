# Limited Media Server on a Raspberry PI

## Goal

The goal of this project is to build an energy-efficient Raspberry Pi server that seamlessly operates within your home network, enabling secure content streaming both locally and remotely via a VPN.

## Affiliate Disclosure  

Some of the links in this document are affiliate links, which means I may earn a small commission if you click on them and make a purchase. This comes at no additional cost to you and helps support my work. I only recommend products or services I genuinely believe in.  

Thank you for your support! 

## Software Requirements (Windows)

While it’s possible to type commands directly on your server device, using tools that enable copying, pasting, and file transfers can significantly streamline your workflow.

### Putty

PuTTY is a free SSH client that allows you to remotely connect to your server device over a local network. It’s essential for managing your server via a command-line interface.

[Official Webpage](https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html)

### WinSCP

WinSCP is a file transfer tool that supports SCP and SFTP protocols. It lets you easily transfer files between your Windows machine and your server device over a local network.

[Official Webpage](https://winscp.net/eng/index.php)

## Hardware Requirements

### 1. Raspberry PI 5

#### Raspberry Pi 5 8GB
https://amzn.to/40crYOc

### 2. Case & NVME Mount

#### [vElectroCookie Mini PC Case for Raspberry Pi 5 with M.2 NVMe SSD PCIe HAT and Active RGB Lighting Cooler (Black Case + NVMe Board)](https://amzn.to/4iRknMw)


This is the case I put together in the video.  I used another case for the 1st server,  but it was a hack job to force the NVMe Hat to fit.  This one actually have the NVMe hat taken into account.

Other Options (Not tested):
* https://amzn.to/3BOQJGZ

### 3. NVMe Drive

It’s important to carefully choose a compatible NVMe drive for the Raspberry Pi 5, as not all drives are supported. Specifically, avoid NVMe SATA drives, as they are incompatible.

The following drives have been tested:

#### [SABRENT Rocket 2230 NVMe 4.0 1TB High Performance PCIe 4.0 M.2 2230 SSD](https://amzn.to/409hD5D)
This is only 1 TB of fast storage, and it fills up fast.  I used this on my 1st server.

#### [SABRENT Rocket Q4 2230 NVMe 4.0 2TB High Performance PCIe 4.0 M.2 2230 SSD Compatible with Steam Deck, ASUS ROG Ally, Mini PCs](https://amzn.to/3ZTk76X)
This is 2 TB of fast storage.  I used this on my new server.

### 4. Noobs

This is just to save time, you could burn your own SD card for the initial installation.

#### [Raspberry Pi 32GB Preloaded (Noobs) SD Card](https://amzn.to/3BJ8OX2)


### 5. Power Supply

#### [PD 27W USB-C Power Supply 5.1V / 5A PSU Charger for Raspberry Pi 5 White](https://amzn.to/3DtypUu)
You could get the official power supply, but this one should work.

### 6. External Hard Drive

This is optional, but if you are going to store media, you might as well have as much space as possible.

#### [WD 4TB Elements Portable External Hard Drive for Windows, USB 3.2 Gen 1/USB 3.0 for PC & Mac, Plug and Play Ready - ‎WDBU6Y0040BBK-WESN](https://amzn.to/4iLa1xA)


This is only 4 TB.  I have used this for months with my 1st server.

#### [Western Digital 8TB Elements Desktop External Hard Drive, USB 3.0 external hard drive for plug-and-play storage - Western DigitalBWLG0080HBK-NESN, Black](https://amzn.to/3Dyx6U8) 


This one is 8 TB.  I have set this up on my new server.

### 7. Micro HDMI cable

The Raspberry PI 5 does not have a typical HDMI port, instead it has a Micro HDMI port.  So if you don't have this cable, these may suffice.

#### [Amazon Basics Micro HDMI to HDMI Display Cable, 18Gbps High-Speed, 4K@60Hz, 2160p, 48-Bit Color, Ethernet Ready, 6 Foot, Black](https://amzn.to/3ByhH5O) 
This is a 6 foot Micro HDMI > HDMI cable

#### [Twozoh Micro HDMI to HDMI Adapter Cable, Nylon Braided Micro HDMI Male to HDMI Female Cable (Type D to Type A) Support 4K/60Hz 1080p (0.6FT)](https://amzn.to/3ZUOuK7)
This is a short adapter, you will still need a real HDMI cable.

### 8. Keyboard

This is only needed for the initial setup and after that everything will be done via remote connections.

### 9. Mouse

This is only needed for the initial setup and after that everything will be done via remote connections.

### 10. Monitor / TV

This is only needed for the initial setup and after that everything will be done via remote connections.

## Instructions

### 00. Purchase

1. Raspberry PI 5 (4 or 8 GIG, but more ram better)
2. Case
3. NVMe HAT (Some cases come with these)
4. NVMe Drive (Not SATA)
5. Power Supply
6. External Hard Drive (Large)
7. Micro HDMI Cable
8. Noobs SD Card (Optional, you can burn your own)

Also have a:
1. Keyboard
2. Mouse
3. Monitor with HDMI input
4. Ethernet Cable (Optional)

### 01. Assembly

Put your Raspberry PI + NVMe Hat + NVMe Drive + Case together.

### 02. Attach

1. Insert Noobs SD Card
2. External Drive
3. Mouse
4. Keyboard
5. Monitor (Via Micro HDMI Cable)
6. Ethernet Cable (If available)
7. Power Cord

### 03. Power Up

If everything is plugged in right, the PI device will startup once you attach the power cord and the screen should show something.

#### Run through the NOOBS installation wizard.

1. *Welcome Screen*
*. Hit *Next*
2. *Set Country*
* Choose your Country, Language and Timezone
* Hit *Next*
3. *Create User*
* This user account is just for setup, keep it simple:
* username: admin
* password: admin
* Hit *Next*
4. *Select WiFi Network*
* I'm just going to *Skip* this step and use a wired connection
5. *Choose Browser*
* This step isn't critical, you can just hit *Next*
6. *Update Software*
* It never hurts to have up to date software, so just hit *Next*
7. Wait for Updates to Finish
8. System is up to date Popup
* Hit "OK"
9. *Setup Complete*
* This phase is done, hit "Restart"
10. Wait a bit and you should see a *desktop*, we are just getting ready, see the next section to continue.

### 04. Getting Ready for NVMe Booting

1. From the Desktop bring up the Terminal

![image](https://github.com/user-attachments/assets/56b8226e-a0e2-478d-a936-4053145c029c)

2. First, ensure that your Raspberry Pi runs the latest software. Run the following command to update:

```bash
sudo apt update && sudo apt full-upgrade
```

3. Next, ensure that your Raspberry Pi firmware is up-to-date.

run the following command to open the Raspberry Pi Configuration CLI:

```bash
sudo raspi-config
```

Under *Advanced Options* > *Bootloader Version*, choose *Latest*. Then, exit raspi-config with Finish or the Escape key.

Run the following command to update your firmware to the latest version:

```bash
sudo rpi-eeprom-update -a
```

You need to reboot the device.

### 05. Imaging your NVMe Drive

1. From the desktop open the Raspberry Pi Imager

From the Top LEFT, *Raspberry Icon* > *Accessories* > *Raspberry Pi Imager*

![image](https://github.com/user-attachments/assets/b2fa30ab-7ec7-42a0-8cc9-45fef8ad35fc)

2. Choose your Device

You need to select Raspberry PI 5

3. Choose your OS

You need to select *Raspberry Pi OS (other)* > *Raspberry Pi OS Lite (64-bit)*

4. Choose your Storage

If everything has worked, the PI should detect your NVMe drive and display it in the list.  If it is not in the list, either your previous step to update the ROM wasn't completed, or the device is not compatiable.

5. Choices

Hit *Next*

Hit *Edit Settings*

6. OS Configuration

#### One the 1st Tab

* Set Hostname: Give it a name, for example *limitedmediaserver*.
* Set a username and password.  I would keep the username as admin, but actually come up with a password for your device.
* You don't need to fill in the Wireless LAN portion if you plan on using wired internet.
* Set locale settings.  Just fill it in.

#### On the 2nd Tab *Services*

* Enable SSH (Check This) and keep it as *Use Password Authentication*

#### On the third Tab

Disable *Telemetry*, no need to phone home.

Finally hit *Save*

On the previous Popup hit *YES*

It will confirm that add data on your device will be wiped erased, hit *YES*

At this point you will be asked to provide your password a few times, it should be *admin*, if you followed the initial NOOBS setup instructions.

Just wait it out...

It should popup a dialog about *Write Successful*, hit *CONTINUE*

At this point your NVMe drive is ready, but, you need to swap the boot drive from SD to NVME, see the next set of instructions.

### 05. Enabling NVMe Booting

1. Open the Terminal

```bash
sudo raspi-config
```

Navigate to *Advanced Options* > *Boot Order* > *NVMe/USB Boot*

Wait a bit...

Get a notice *NVMe/USB is default boot device*

Press *Enter*

exit raspi-config with Finish

It will ask if you you *Would you like to reboot now?*, Hit Yes

Wait for a few cycles and you will eventually be sitting on a terminal based login prompt.  Take note of the IP address, you will need this for later.

Your device is now botting off the NVMe drive.  Good Job!  We're going to leave the physical connection and instead remote SSH into the device from a windows machine.

### 05.B Extra Work

#### How to Set Up a Static Local IP Address for Your Network Device

Setting a static local IP address ensures that your server or device retains the same IP address within your network. This is essential for advanced services like VPN access or remote server connections. The process varies depending on your router model, but the general steps remain consistent.

#### General Instructions for Setting a Static Local IP Address

1. Access Your Router's Configuration Page
* Open a web browser and enter your router's IP address (commonly 192.168.0.1 or 192.168.1.1).
* Log in using the administrator username and password. Refer to your router's manual if you're unsure of these credentials.

2. Locate the DHCP Settings
* Navigate to the section for DHCP (Dynamic Host Configuration Protocol) or LAN settings.
* Look for options like "Address Reservation," "Static IP," or "DHCP Reservation."

3. Assign a Static IP Address
* Identify your device in the list of connected devices or enter its MAC address manually.
* Specify the desired static IP address (e.g., 192.168.1.100) within the range of your local network but outside the DHCP allocation range.
* Save the changes.

4. Reboot the Device
* Restart the device to ensure it adopts the new static IP address.

### 06. Windows Tools

#### Install

Install Putty & WinSCP, link were provided earlier in the document.  WinSCP isn't needed at the moment, but if you want to transfer files between devices, it's neccessary.

#### Putty Setup

![image](https://github.com/user-attachments/assets/ad350e32-83ac-4e18-bde5-7efbc50f130b)

0. Run Putty
1. Enter the server's IP Address, you should have noted it down from the previous step.  Or have assigned it a static IP address as mentioned in *Extra Work*
2. You should give this session a name like *Limited Media Server*
3. Hit *Save*, this allows you to store a preset, so next time you can skip some steps
4. Hit *Open*

If everything worked, you should be prompted to enter a username and password

#### WinSCP Setup

![image](https://github.com/user-attachments/assets/48736405-a03a-42b4-90ed-f2202ef944b9)

0. Run WinSCP
1. Click *New Site*
2. Fill in the *Host name*
3. Fill in the *Username*
4. Fill in the *Password*
5. Hit Save

![image](https://github.com/user-attachments/assets/f5fb3922-9fec-4c7f-88b4-50ccc5dd1c3c)

1. Give it a decent Site Name, maybe *Limited Media Server*
2. This is upto you, but if you don't want to type the password every time, click it
3. This is also optional, but it would save you time
4. Hit OK

![image](https://github.com/user-attachments/assets/0ffd4b15-340c-453f-b931-31e6e2ae0ca2)

At this point just Hit *Login* and it should present you with a file browser in the Home directory

### 07. (Optional) Enable Gen 3 Speeds

By default the Raspberry PI 5 supports Gen 2 speeds, but it can achieve Gen 3, but it's not fully supported.

1. Open Your Putty Terminal to the Server
2. Enter the following command
```bash
sudo raspi-config
```
Navigate to *Advanced Options* > *PCIe Speed* > *Yes* > *OK*

You need to *Finish* the config tool and reboot when offered.

### 08. Required Server Software

Everything here will be from the Putty Terminal.

#### Getting Ready

Make sure your libraries and software are up to date

```bash
sudo apt update && sudo apt upgrade -y
```

#### GIT

Git is already Installed, so no action required

You can verify if GIT is installed via this command

```bash
git --version
```

#### Python 3 & Pip

Python 3 should already be available, so we just need to install PIP

```bash
sudo apt install python3-pip -y
```

You can verify if Python3 and PIP were installed via this command

```bash
python3 --version
pip3 --version
```

#### NodeJs and NPM

```bash
sudo apt install nodejs npm -y
```

You can verify if NODEJS and NPM were installed via this command

```bash
node -v
npm -v
```

### 09. Mounting your External Hard drive

You have all that extra storage, we need to make sure it's available.

#### 1. Identify the External Drive

First, list all connected drives:

```bash
lsblk -o NAME,FSTYPE,SIZE,MOUNTPOINT,LABEL
```

* Look for your external drive (e.g., sda, sdb).
* Ensure you identify the correct drive, as formatting will erase all data.
  - Example: /dev/sda or /dev/sdb1

#### 2. Format the Drive as ext4

Format the drive with mkfs.ext4:

```bash
sudo mkfs.ext4 /dev/sdX1
```

* Replace /dev/sdX1 with your partition name (e.g., sda1).
* If the drive doesn’t have partitions (e.g., just /dev/sda), you can format the entire disk.

####  3. Create the Mount Point

Create the mount directory:

```bash
sudo mkdir -p /mnt/external
```

#### 4. Configure Automount via /etc/fstab

Find the UUID of the Drive

```bash
sudo blkid /dev/sdX1
```

Look for the *UUID="XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"*

##### Edit `/etc/fstab`

Open the fstab file:

```bash
sudo nano /etc/fstab
```

Add the following line at the bottom:

```text
UUID=XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX /mnt/external ext4 defaults,noatime 0 2
```

##### Explanation:
* `defaults`: Standard mount options.
* `noatime`: Prevents writing file access times for better performance.
* `0`: Skip dump (backup utility).
* `2`: Run fsck (filesystem check) after boot, if needed.

#### 5. Test / Mount

Use the following command to re-load your fstab file

```bash
sudo systemctl daemon-reload
```

With everything reloaded, you can use the following command to verify that your drive has been mounted correctly

```bash
df -h /mnt/external
```

#### 6. Permissions

You might as well claim the drive for the ADMIN user, who will run all services, issue this command

```bash
sudo chown -R admin:admin /mnt/external
```

#### 7. Folders

You might as well create the folders needed for Limited Media Server.  You will also need these paths later when setting up the various properties.

#### Description of folders
* `/home/admin/data/primary`
  - Used to store media on your fast drive.
  - For `SERVER.MEDIA.PRIMARY.FOLDER` property.
* `/home/admin/data/temp`
  - Used for processing, should be on a fast drive.
  - For `SERVER.MEDIA.TEMP.FOLDER` property.
* `/home/admin/data/books`
  - Where books wil be stored.
  - For `SERVER.VOLUME.FOLDER` property.
* `/mnt/external/data/archive`
  - This is where media you don't need quick access to should be stored.
  - For `SERVER.MEDIA.ARCHIVE.FOLDER` property.

```bash
sudo mkdir -p /home/admin/data/primary
sudo mkdir -p /home/admin/data/temp
sudo mkdir -p /home/admin/data/books
sudo mkdir -p /mnt/external/data/archive
sudo chown admin:admin /home/admin/data/
sudo chown admin:admin /home/admin/data/primary
sudo chown admin:admin /home/admin/data/temp
sudo chown admin:admin /home/admin/data/books
sudo chown admin:admin /mnt/external/data
sudo chown admin:admin /mnt/external/data/archive
```

### 10. Installing Limited Media Server (From Source)

Start in Putty in your Admin's home directory, the default folder when you login.

You can issue the following command to install limited media server and start it up.

```bash
git clone https://github.com/mgatelabs/LimitedMediaServer.git
git clone https://github.com/mgatelabs/LimitedMediaServerSite.git
cd LimitedMediaServerSite
npm install
ng build
cd ..
cd LimitedMediaServer
pip install -r requirements.txt --break-system-packages
python server.py
```

If everything worked you should be able to open a browser to http://IP_ADDRESS:5000 and view the login page.

At this point you can use the [basic install instructions found](https://github.com/mgatelabs/LimitedMediaServer/blob/main/README.md#basic-setup).  For the initial user to login as and how to setup the various properties.

#### More Software

#### FFMPEG (Video Encoding & Downloading)

#####  1. Update Your System
First, make sure your Raspberry Pi is up to date:

```bash
sudo apt update
sudo apt upgrade -y
```
##### 2. Install FFmpeg from the Repository

FFmpeg is available in the default Raspberry Pi OS repositories. Install it with:

```bash
sudo apt install ffmpeg -y
```

This will install FFmpeg along with its dependencies.

##### 3. Verify the Installation

After installation, verify that FFmpeg is installed correctly by checking its version:

```bash
ffmpeg -version
```

#### YT-DLP (Downloading Content)

#### 1. Installation

You can install the PyPI package with:

```bash
python3 -m pip install -U "yt-dlp[default]" --break-system-packages
```


##### 2. Verify the Installation

After installation, verify that yt-dlp is installed correctly by checking its version:

```bash
yt-dlp --version
```

If installed successfully, you'll see information about the yt-dlp version.

##### 3. Updating

yt-dlp will eventually stop working and you will need to update it again, use the following command to refresh the insstall.

```bash
python3 -m pip install -U "yt-dlp[default]" --break-system-packages
```

#### curl-impersonate (Downloading Content)

Install dependencies for building all the components:

```bash
sudo apt install build-essential pkg-config cmake ninja-build curl autoconf automake libtool
# For the Firefox version only
sudo apt install python3-pip libnss3
pip install gyp-next
export PATH="$PATH:~/.local/bin" # Add gyp to PATH
# For the Chrome version only
sudo apt install golang-go unzip
```

Clone the repository:

```bash
git clone https://github.com/lwthiker/curl-impersonate.git
cd curl-impersonate
```

Configure and compile:

```bash
mkdir build && cd build
../configure
# Build and install the Firefox version
make firefox-build
sudo make firefox-install
# Build and install the Chrome version
make chrome-build
sudo make chrome-install
# You may need to update the linker's cache to find libcurl-impersonate
sudo ldconfig
# Optionally remove all the build files
cd ../ && rm -Rf build
```

#### VPN Installation (Optional)

##### DuckDNS

I had to search around, but DuckDNS.org is a working service to keep track of your IP address.  If you have a static IP address, you can skip to the PiVPN installation.

###### 1. Sign into DuckDNS.org

Visit https://www.duckdns.org and sign in with one of their available services.

###### 2. Create your Domain

Find this spot and enter a uniqwue sounding name for your domain

![image](https://github.com/user-attachments/assets/0a65df5e-c878-4992-88c1-96e84bc64bed)

###### 3. Create the local service

Now visit https://www.duckdns.org/install.jsp and choose "PI" and your DOMAIN.  Generally follow the instructions that are provided.

Just remember, login to your PI with PUTTY.

If it asks you to choose an editor just choose "1"

##### PiVPN

Start off by making sure everything is updated.

```bash
sudo apt-get update
sudo apt-get upgrade
```

Executing this script will start an install process to guide you through setup.

```bash
curl -L https://install.pivpn.io | bash
```

###### 1. Welcome Screen
![image](https://github.com/user-attachments/assets/2ff1f885-2003-452c-b6b3-d92fb0259d8f)
Press Enter
###### 2. Static IP Notice
![image](https://github.com/user-attachments/assets/2a714f2e-744f-4493-901d-c4362a363632)
This is a warning that you need a local static IP address.  This is typically accomplished via editing your router to assign a static IP address.

Press Enter
###### 3. IPv6 Notice
![image](https://github.com/user-attachments/assets/b1fe98cd-1344-4b93-a48c-35fbdadf31ef)
I'm not concerned, just choose NO, press Enter

###### 4. DHCP Reservation
![image](https://github.com/user-attachments/assets/570c1d33-9c1a-47f2-8907-8eedbe760e89)
For me, I already assigned a reserved IP address for the Paspberry PI, so I choose YES, press Enter.

###### 5. Local Users
![image](https://github.com/user-attachments/assets/e5d9fd07-96c0-4f2f-861d-ba7016fe68bd)
This is a notice, press Enter

###### 6. Choose A User
![image](https://github.com/user-attachments/assets/47ee200f-c1b7-46e3-926b-29b22e1e0c91)
I only have one user, Press Enter

###### 7. Installation mode
![image](https://github.com/user-attachments/assets/bd2c000b-d962-472f-8657-1ebb18484b82)
Stick with WireGuard, press Enter

###### 8. Default wireguard Port
![image](https://github.com/user-attachments/assets/5d0a54ef-1fbe-476a-a3f9-320c4fb30822)
Leave it as 51820, press Enter

###### 9. Confirm Custom Port Number
![image](https://github.com/user-attachments/assets/d82dbf77-ee0c-4cc9-8d39-4a51bb6dcb6f)
Verify yor answer, choose Yes, press Enter

###### 10. DNS Provider
![image](https://github.com/user-attachments/assets/bb42b98d-cf91-4cd0-8f44-77970dfad696)
I will leave this up to you...

###### 11. Public IP or DNS
![image](https://github.com/user-attachments/assets/11ca457a-fa42-4064-8a54-ea849ef08f0e)
For me, I already setup a DuckDNS account, so I choose DNS entry.  If you have a static IP address from your Internet Provider, you can use the 1st option.

###### 12. PiVPN Setup
![image](https://github.com/user-attachments/assets/bf3b6dde-11b7-4e23-b7ca-52dcc15b5757)
For your DuckDNS host it will be HOSTNAME.duckdns.org

###### 13. Confirm DNS Name
![image](https://github.com/user-attachments/assets/cb6765c2-a520-49ee-853c-a863483f5212)
If it looks right, select Yes and press Enter


###### 14. Server Information
![image](https://github.com/user-attachments/assets/59b5e254-58a8-4427-9d7a-91fdb2de06a6)
Press Enter

###### 15. Unattended Upgrades
![image](https://github.com/user-attachments/assets/a8065af4-9baa-409e-bb47-3acfac2b3b58)
This is another notice, press Enter

###### 16. Unattended Upgrades
![image](https://github.com/user-attachments/assets/5dd90d39-c04e-43c6-8d12-65d943c911e9)

For security, you should choose Yes and press Enter

###### 17. Installation Complete
![image](https://github.com/user-attachments/assets/0a2501f5-edae-493f-89d2-b0ac49dde5ac)
This is a notice screen, but take account of ```pivpn add``` which you will use later, press Enter

###### 18. Reboot
![image](https://github.com/user-attachments/assets/32b79b83-6498-4cb7-b625-9a1389d152ae)
It is a good idea to restart, select Yes, press Enter

###### 19. Rebooting
![image](https://github.com/user-attachments/assets/67058757-75da-4b1f-8943-623ba0386f74)
This is a confirmation, Press Enter

###### 20. Wait
Wait for the server to reboot and login again

###### 20. Add a client config
![image](https://github.com/user-attachments/assets/60440da0-60e0-44f9-9cce-24732adcbbfb)

Use the following command to add a configuration
```bash
pivpn add
```
For the client IP, just leave it blank, press Enter
You need to provide a name, just give it one, press Enter


###### 21. Use your Config

On your device you want to access your netowrk, install WireGuard.  You can search your phone's App Store.

![image](https://github.com/user-attachments/assets/c19fe226-4e59-4b98-8db4-8a6263f9e07f)

On your PI use the following command to display a QR code

```bash
pivpn -qr
```

You will need to choose the client config, and a QR will display

#### What else should you considder?

Look at [Advanced Development Configuration](https://github.com/mgatelabs/LimitedMediaServer?tab=readme-ov-file#advanced-development-configuration), to make the app run as a service.  So even after reboot, it's available.

Look at [Securing your server](https://github.com/mgatelabs/LimitedMediaServer/blob/main/README.md#securing-your-server) to setup a nginx proxy to allow HTTP port 80 access, and HTTPS port 443 access.

Setting up a VPN, to be continued.
