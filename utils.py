import json
import os
import glob

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}

def get_image_paths(config):
    folder = "photos"
    if config["source"] == "usb":
        folder = "/media/usb"  # Adapte selon ton point de montage

    image_extensions = ('*.jpg', '*.jpeg', '*.png')
    image_paths = []
    for ext in image_extensions:
        image_paths.extend(glob.glob(os.path.join(folder, ext)))
    return sorted(image_paths)
