📣 Announcement – New Version Scheduled for Release on August 15, 2025

Current Version (July 14, 2025): New release now available online

📆 Starting June 2025 — One major version every month

## 🛠️✅ August 2025 – (Scheduled Release: August 15)

✅ Video support
✅ Introduction of the "Postcard" feature via Telegram
  - ✅ Secured via invitation link
✅ Hardware acceleration support for Pi3
✅ App translation added (English and Spanish)
✅ QR Code for first-time setup
✅ "Postcard effect" added to all photo sources
✅ Text overlay feature
✅ Favorites tab added (to increase photo display frequency)
✅ Bug fixes
  - ✅ Photo display start time
  - ✅ Log deletion in the system tab without container issues

## ✅ July 2025 – Current Version

- ✅ 🧭 Added Wi-Fi configuration from the web interface  
- ✅ 🗂️ Reorganized the settings page into tabs  
- ✅ 🔁 Automatic periodic update of the Immich album  
- ✅ 📁 SMB protocol support to access network-shared photos  
- ✅ ⏰🌤️ Display of time and weather on screen  
- ✅ Added NGINX – no more need to specify port 50000  
- ✅ Added photo filters (B&W, Sepia, Polaroid, etc.)  
- ✅ Added various delete buttons  
- ✅ Added configuration backup option  
- ✅ Added password change menu  
- ✅ Added creation of `credentials.json` during setup  
- ✅ Added transition effects  
- ✅ Automatic resolution detection added  
- ✅ Import from smartphone (admin and guest modes)  
- ✅ Photo approval interface for guest mode  
- ✅ Added logs to the System tab  
- ✅ Added Raspberry Pi stats (temperature, RAM usage, CPU load)

## ✅ June 2025 – Current Release

- ✅ Photo previews with delete option  
- ✅ Real screen sleep mode (using `wlr-randr`)  
- ✅ Screen height percentage setting (usable screen area)  
- ✅ EXIF-based orientation fix and photo preparation  



## 💡 Ideas for Future Releases

- 📱 Android APK to control the frame  
 

---

# 🖼️ Pimmich – Smart Digital Photo Frame

**Pimmich** is a Python application that turns a Raspberry Pi into a smart digital photo frame. It displays photo albums hosted on an **Immich server** or from a **USB stick**. All suggestions for improvement are welcome!

<img src="static/pimmich_logo.png" alt="Pimmich Logo" width="300">

---

## ✨ Features

- 🔒 Secure login interface
- 🖼️ Photo preview with GLightbox CSS
- 🖼️ Slideshow with portrait photo support (blurred background)
- 🌐 Immich API integration (automatic album fetching)
- 📂 USB stick as an alternative image source
- 🗑️ Delete photos directly from the preview interface
- 🕒 Configurable display schedule
- 💡 Local web interface for configuration (`http://<Pi-IP>:5000`)
- 🔌 Reboot and shutdown buttons

---

## 🧰 Technologies Used

- Python  
- Flask  
- Requests  
- Pygame  
- Pillow  
- Tkinter (for the slideshow interface)  
- Immich API  
- GLightbox CSS  

---

## 📦 Installation

Eventually, two installation methods will be available:  
1. A ready-to-use `.img` file (not available yet)  
2. Manual setup via repository clone (currently functional, USB import is still under refinement)

### ✅ Requirements

- Raspberry Pi with Raspberry Pi OS Desktop (64-bit)
- Internet connection
- Python installed
- Keyboard + screen for first setup (or SSH access)

---

### Install from Repository

#### Clone the repository

```bash
git clone https://github.com/gotenash/pimmich.git
cd pimmich
```

#### Run `setup.sh`

Make the script executable and launch it:

```bash
chmod +x setup.sh
sudo ./setup.sh
```

This script installs system and Python dependencies, sets up the environment, and configures auto-start of the slideshow.

---

### 🔑 Get Your Immich API Token

1. Log into your Immich web interface  
2. Go to **Account Settings**

Click your profile icon (top-right), then choose **Account Settings**.

3. Generate a new API key  
In the **API Key** section, click **Generate new API Key** and give it a name (e.g., `PimmichFrame`).

⚠️ Once the token is shown, **copy it immediately** — you won’t be able to see it again. If lost, you’ll need to generate a new one.

🔒 We recommend creating a dedicated Immich account for the photo frame, with access to a single shared album.

---

### Connect to Pimmich

From a web browser on another device, access:

```
http://<your-raspberry-ip>:5000
```

---

## ⚙️ Configuration Interface

### Slideshow Settings

Here, you can set the display time per photo (minimum ~10s, due to background blur processing for portrait images) and define active hours for the slideshow.

### Photo Import Settings

Choose between importing from an Immich album or a USB stick, and manage downloaded files.
