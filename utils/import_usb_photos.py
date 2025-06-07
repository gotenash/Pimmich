import os
import shutil
from pathlib import Path
import time

# Dossier où les photos préparées doivent être copiées
TARGET_DIR = Path("static/photos")

# Extensions d’image acceptées
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}

def is_image_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS

def find_usb_mount_point():
    # Recherche dans /media/pi/ ou /media/usb
    possible_mounts = list(Path("/media").rglob("*"))
    for mount in possible_mounts:
        if mount.is_dir() and any(f.is_file() for f in mount.iterdir()):
            return mount
    return None

def import_usb_photos():
    usb_path = find_usb_mount_point()
    if not usb_path:
        raise FileNotFoundError("Aucune clé USB détectée avec des fichiers.")

    print(f"[INFO] Clé USB détectée : {usb_path}")

    # Nettoyage du dossier cible
    if TARGET_DIR.exists():
        shutil.rmtree(TARGET_DIR)
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    imported_count = 0

    for root, _, files in os.walk(usb_path):
        for filename in files:
            file_path = Path(root) / filename
            if is_image_file(file_path.name):
                dest_file = TARGET_DIR / file_path.name
                shutil.copy2(file_path, dest_file)
                imported_count += 1

    if imported_count == 0:
        raise ValueError("Aucune image compatible trouvée sur la clé USB.")

    print(f"[INFO] {imported_count} photos importées depuis la clé USB.")
