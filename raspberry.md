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
