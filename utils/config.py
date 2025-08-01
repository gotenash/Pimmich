# utils/config.py

import json
import os

CONFIG_PATH = os.path.join("config", "config.json")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def get_album_id_by_name(name):
    # Cette fonction n’est plus utilisée si tu récupères directement les albums dans `download_album.py`.
    return None
