📣 Announcement – New Version Scheduled for Release on August 15, 2025

Current Version (July 14, 2025): New release now available online

sudo reboot> 📆 Starting June 2025 — One major version every month

## 🗓️ October 2025 - (In development)
- 📱 Android APK to control the frame (Pimmich remote)
-  Physical button support to start/stop the slideshow.
- 🗂️ Album management directly from the Pimmich interface (create, rename, etc.).

## ✅ September 2025 – (Scheduled Release: September 15)
- 🗣️ **Voice Control:** Added voice command support ("Magic Frame") to control the frame (next photo, pause, etc.).
- 🎨 **UI Overhaul:** New group-based navigation for a clearer and more intuitive user experience.
- 🎵 **Playlist Management:** Create custom virtual albums, view their content, rename them, and launch themed slideshows.
- 📊 **Advanced Monitoring:** Added history charts for CPU temperature, CPU usage, RAM, and disk in the "System" tab.
- 🖥️ **Display Management:** Ability to list and force a specific screen resolution directly from the interface, with automatic slideshow restart.
- 💾 **Storage Expansion:** Added a tool in the interface to easily expand the filesystem and use all available space on the SD card.
- 🚀 **Optimizations and Stability:**
    - ✅ Improved responsiveness of the "System" tab with optimized log reading.
    - ✅ Made the update script more reliable to prevent freezes.

## 🛠️✅ August 2025 – (Scheduled Release: August 15)

✅ Video support
✅ Added video thumbnail in the Actions tab
✅ Introduction of the "Postcard" feature via Telegram
  - ✅ Secured via invitation link
✅ Hardware acceleration support for Pi3
✅ App translation added (English and Spanish)
✅ QR Code for first-time setup
✅ "Postcard effect" added to all photo sources
✅ Text overlay feature
✅ Added "Restart Web App" button
✅ Favorites tab added (to increase photo display frequency)
✅ Weather and tides updated to show 3-day forecasts
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


---

<img src="static/pimmich_logo.png" alt="Pimmich Logo" width="300">

---

## 📖 Table of Contents

- ✨ Main Features
- 🧰 Technologies Used
- 🚀 Installation
- 🔧 Configuration
- 🗣️ Voice Control
- ❓ Troubleshooting (FAQ)
- 💖 Credits

---

## ✨ Main Features

Pimmich is packed with features to provide a complete and customizable experience:

#### 🖼️ **Display & Slideshow**
- **Multi-source:** Display photos from Immich, a network share (Samba/Windows), a USB drive, a smartphone, or via Telegram.
- **Advanced Customization:** Set display duration, active hours, transitions (fade, slide), and enable a "Pan & Zoom" motion effect.
- **Creative Filters:** Apply filters to your photos (Black & White, Sepia, Vintage) and unique effects like **Polaroid** or **Postcard**.
- **Format Handling:** Smart support for portrait photos (blurred background) and videos (with sound and optional hardware acceleration).

#### ⚙️ **Interface & Control**
- **Comprehensive Web Interface:** A local configuration page, password-protected and organized into clear tabs (Slideshow, Content, Interactions, Maintenance).
- **Voice Control:** Control your frame with voice commands like *"Magic Frame, next photo"* or *"Magic Frame, play Vacation playlist"*.
- **Content Management:**
    - **Playlists:** Create virtual albums, reorder photos with drag-and-drop, and launch themed slideshows.
    - **Favorites:** Mark your favorite photos to make them appear more often.
    - **Captions:** Add custom text to your photos and postcards.

#### 🌐 **Connectivity & Interactions**
- **Telegram:** Allow friends and family to send photos to the frame via a Telegram bot, with a secure and temporary invitation system.
- **Wi-Fi & Network:** Configure Wi-Fi, scan for networks, and manage network interfaces directly from the interface.
- **Smartphone Upload:** Import photos directly from your phone's browser.

#### 🛠️ **Maintenance & Monitoring**
- **Easy Updates:** Update Pimmich with a single click from the interface.
- **Backup & Restore:** Back up and restore your entire configuration.
- **System Monitoring:** Track real-time temperature, CPU, RAM, and disk usage with history graphs.
- **Detailed Logs:** Access logs for each service (web server, slideshow, voice control) for easy troubleshooting.

---

## 🧰 Technologies Used

- **Backend:** Python, Flask
- **Frontend:** HTML, TailwindCSS, JavaScript
- **Slideshow:** Pygame
- **Image Processing:** Pillow
- **Voice Control:** Picovoice Porcupine (wake word) & Vosk (recognition)
- **Web Server:** NGINX (as a reverse proxy)

---

##  Installation

The installation is automated to be as simple as possible.

### ✅ Requirements

- Raspberry Pi with Raspberry Pi OS Desktop (64-bit)
- Internet connection
- Python installed
- Keyboard + screen for first setup (or SSH access)
 
### 📝 Installation Steps

1.  **Clone the repository**
    Open a terminal on your Raspberry Pi and run:
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
