# ❓ Frequently Asked Questions (FAQ) - Pimmich

Here is a list of frequently asked questions to help you use and troubleshoot Pimmich.

---

### General Questions

**Q: What is Pimmich?**

**A:** Pimmich is software that turns a Raspberry Pi into a smart digital photo frame. It can display photos from an [Immich](https://immich.app/) server, a USB stick, a network share (Samba/Windows), a smartphone, or even via the Telegram messaging app.

**Q: What do I need to use Pimmich?**

**A:** You will need:
- A Raspberry Pi (model 3, 4, or 5 recommended) with its power supply.
- An SD card with Raspberry Pi OS (64-bit) installed.
- A screen.
- An internet connection (Wi-Fi or Ethernet).

---

### Installation and Configuration

**Q: How do I install Pimmich?**

**A:** The installation is designed to be simple:
1. Clone the GitHub repository: `git clone https://github.com/gotenash/pimmich.git`
2. Go into the directory: `cd pimmich`
3. Make the installation script executable: `chmod +x setup.sh`
4. Run the script with administrator rights: `sudo ./setup.sh`
The script takes care of installing all dependencies and configuring the system for automatic startup.

**Q: How do I access the configuration interface?**

**A:** Once the Raspberry Pi has started, open a web browser on another device (computer, smartphone) connected to the same network and simply type in your Raspberry Pi's IP address. For example: `http://192.168.1.25`. If you don't know the IP, it is often displayed on the frame's screen on the first boot or if no photos are found.

**Q: I forgot my password for the web interface. How can I reset it?**

**A:** The initial password is stored in the `/boot/firmware/credentials.json` file. You can connect to your Raspberry Pi via SSH to read this file. If you changed it through the interface and forgot it, you will need to delete this file and reboot the Pi for it to generate a new one (warning: this will reset the user).

**Q: How do I get an Immich API Token?**

**A:**
1. Log in to your Immich web interface.
2. Go to "Account Settings" (via your profile icon).
3. In the "API Keys" section, click "Generate New API Key".
4. Give it a name (e.g., "Pimmich") and copy the generated key.

*Tip:* For better security, create a dedicated Immich user for the frame with limited access to a single shared album.

---

### Features

**Q: How does the Telegram feature work?**

**A:** It allows you and your guests to send photos directly to the frame.
1.  **Create a bot** on Telegram by talking to `@BotFather`. It will give you a **Token**.
2.  **Get your user ID** on Telegram by talking to a bot like `@userinfobot`.
3.  Enter both pieces of information in the "Telegram" tab in Pimmich.
4.  You can then create secure, temporary invitation links for your loved ones.

**Q: What is the "Favorites" tab for?**

**A:** By marking a photo as a favorite (using the star icon <i class="fas fa-star"></i> in the "Preview" tab), you increase its display frequency in the slideshow. You can adjust the "boost factor" in the "Display" tab to make them appear more or less often.

**Q: What is the "Postcard" effect?**

**A:** It's a filter that adds a white border and a space for a caption (if you add one via the interface) to your photos, giving them a postcard look. Photos sent via Telegram use this effect by default for a more personal and warm touch.

---

### Troubleshooting

**Q: I have a problem, where can I find help?**

**A:** The **System** tab is the best place to start. It contains a **Logs** section.
- `app.py` contains the logs for the web server (configuration interface).
- `local_slideshow_stdout` and `local_slideshow_stderr` contain the logs for the slideshow itself. Errors will most often appear in `stderr`.

**Q: Videos are not smooth or don't display. What should I do?**

**A:** In the **Display** tab, try enabling the "**Enable hardware video decoding**" option. It is much more performant, especially on a Raspberry Pi. If it causes issues (black/blue screen after a video), disable it.

**Q: The Wi-Fi won't connect, but Ethernet (cable) works. Why?**

**A:** Sometimes, if an Ethernet cable is plugged in, the system gives it priority. In the **System** tab, you can try to temporarily disable the "**Wired Interface (eth0)**" to force the system to use Wi-Fi exclusively.

**Q: How do I update Pimmich?**

**A:** Go to the **System** tab and click the "**Check for updates**" button. Pimmich will download the latest version from GitHub and restart automatically.

**Q: I changed a setting, but nothing changes on the slideshow.**

**A:** Some changes, especially those related to display (font, weather, etc.), require the slideshow to be restarted to take effect. You can do this from the **Actions** tab by clicking "Stop" and then "Start Slideshow". For more significant changes, a restart of the web application or the system (from the **System** tab) may be necessary.