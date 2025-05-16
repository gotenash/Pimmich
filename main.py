# main.py
import os
import zipfile
import requests
from flask import Flask, render_template
from dotenv import load_dotenv

import time
from slideshow_window import SlideshowWindow
from utils import load_config, get_image_paths

if __name__ == "__main__":
    config = load_config()
    source = config.get("source", "immich")

    while True:
        current_hour = time.strftime("%H:%M")
        if config["start_time"] <= current_hour <= config["end_time"]:
            image_paths = get_image_paths(config)
            if image_paths:
                window = SlideshowWindow(image_paths)
                window.run()
            else:
                print("Aucune image trouvée.")
        else:
            print("Hors période d’activité.")
        time.sleep(60)

load_dotenv()

IMMICH_URL = os.getenv("IMMICH_URL")
IMMICH_API_KEY = os.getenv("IMMICH_API_KEY")
ALBUM_NAME = os.getenv("ALBUM_NAME", "cadrepi")
STATIC_FOLDER = "static/photos"
ARCHIVE_PATH = "album.zip"

app = Flask(__name__, static_folder="static", template_folder="templates")

def get_album_id():
    headers = {"x-api-key": IMMICH_API_KEY}
    resp = requests.get(f"{IMMICH_URL}/api/albums", headers=headers)
    resp.raise_for_status()
    albums = resp.json()
    for album in albums:
        if album["albumName"] == ALBUM_NAME:
            return album["id"]
    raise ValueError(f"Album '{ALBUM_NAME}' non trouvé")

def download_album(album_id):
    headers = {
        "x-api-key": IMMICH_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/octet-stream"
    }
    asset_ids = get_asset_ids(album_id)
    if not asset_ids:
        raise ValueError("Aucun asset trouvé dans l'album")

    data = {"assetIds": asset_ids}
    resp = requests.post(f"{IMMICH_URL}/api/download/archive", json=data, headers=headers)
    resp.raise_for_status()

    with open(ARCHIVE_PATH, "wb") as f:
        f.write(resp.content)

def get_asset_ids(album_id):
    headers = {"x-api-key": IMMICH_API_KEY}
    resp = requests.get(f"{IMMICH_URL}/api/albums/{album_id}/assets", headers=headers)
    resp.raise_for_status()
    return [asset["id"] for asset in resp.json()]

def extract_zip():
    if not os.path.exists(STATIC_FOLDER):
        os.makedirs(STATIC_FOLDER)
    with zipfile.ZipFile(ARCHIVE_PATH, "r") as zip_ref:
        zip_ref.extractall(STATIC_FOLDER)
    os.remove(ARCHIVE_PATH)

@app.route("/")
def slideshow():
    files = sorted([
        f for f in os.listdir(STATIC_FOLDER)
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif"))
    ])
    return render_template("slideshow.html", images=files)

if __name__ == "__main__":
    try:
        print("Téléchargement de l'album...")
        album_id = get_album_id()
        download_album(album_id)
        extract_zip()
    except Exception as e:
        print("Erreur :", e)
    app.run(host="0.0.0.0", port=5000)
