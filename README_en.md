# 🖼️ Pimmich – Smart Connected Photo Frame

Pimmich is a Python application designed to turn a Raspberry Pi into a smart and customizable digital photo frame. It can display photos from multiple sources, be controlled by voice, and much more.

<img src="static/pimmich_logo.png" alt="Pimmich Logo" width="300">

---

## 📖 Table of Contents

- ✨ Main Features
- 🧰 Technologies Used
- 🚀 Installation
- 🔧 Configuration
- 🗣️ Voice Control
- ❓ Troubleshooting (FAQ)
- 🛣️ Roadmap
  - June 2025
  - July 2025
  - August 2025
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
- **Comprehensive Web Interface:** A local configuration page, password-protected and organized into thematic groups and tabs for an intuitive navigation.
- **Voice Control:** Control your frame with voice commands like *"Magic Frame, next photo"* or *"Magic Frame, play Vacation playlist"*.
- **Content Management:**
    - **Playlists:** Create virtual albums, reorder photos with drag-and-drop, and launch themed slideshows with a dynamic title screen (photo jumble on a corkboard background).
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

## 🚀 Installation

There are two methods to install Pimmich.

### Method 1: Pre-configured Image (Recommended and easier)

This method is ideal for a quick first-time installation.

1.  **Download the current month's image**
    Go to the Pimmich Releases page and download the `.img` file of the latest version.

2.  **Flash the image to an SD card**
    Use software like Raspberry Pi Imager or BalenaEtcher to write the image file you just downloaded to your microSD card.

3.  **Start your Raspberry Pi**
    Insert the SD card into the Raspberry Pi, connect the screen and power supply. Pimmich will start automatically.

### Method 2: Manual Installation from Git Repository

This method is for advanced users or those who want to follow development closely.

#### ✅ Prerequisites

- A Raspberry Pi (model 3B+, 4, or 5 recommended) with Raspberry Pi OS Desktop (64-bit).
- An SD card, a power supply, a screen.
- An Internet connection.

#### 📝 Installation Steps

1.  **Clone the repository**
    Open a terminal on your Raspberry Pi and run:
    ```bash
    git clone https://github.com/gotenash/pimmich.git
    cd pimmich
    ```

2.  **Run the installation script**
    This script installs all dependencies, configures the environment, and prepares for automatic startup.
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
