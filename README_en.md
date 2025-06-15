📣 Announcement – (June 14, 2025): New release available

Photo previews with the ability to delete photos

Real screen sleep mode, not just a black screen

I'll try to publish one release per month with meaningful improvements.

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

### Create `credentials.json`

At the root of your SD card, create a file named `credentials.json` to define the login credentials for accessing the configuration page:

```json
{
  "username": "your_username",
  "password": "your_password"
}
```

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
