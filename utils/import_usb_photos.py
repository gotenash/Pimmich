import os
import shutil
from pathlib import Path
import time

TARGET_DIR = Path("static/photos")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}

def is_image_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS

def find_usb_mount_point():
    """Recherche plus robuste des points de montage USB"""
    possible_paths = [
        Path("/media"),
        Path("/mnt"),
        Path("/run/media")
    ]
    
    for base_path in possible_paths:
        if base_path.exists():
            for mount in base_path.rglob("*"):
                try:
                    if mount.is_dir() and any(f.is_file() and is_image_file(f.name) for f in mount.iterdir() if f.is_file()):
                        return mount
                except (OSError, PermissionError):
                    # Ignorer les dossiers inaccessibles
                    continue
    return None

def import_usb_photos():
    """Importe les photos depuis une clé USB et retourne des objets structurés (dict) pour le suivi."""
    yield {"type": "progress", "stage": "SEARCHING", "percent": 5, "message": "Recherche de clés USB connectées..."}
    time.sleep(1)
    
    usb_path = find_usb_mount_point()
    if not usb_path:
        yield {"type": "error", "message": "Aucune clé USB avec des images détectée. Vérifiez la connexion."}
        return

    yield {"type": "progress", "stage": "DETECTED", "percent": 10, "message": f"Clé USB détectée : {usb_path}"}

    # S'assurer que le dossier existe sans le vider, pour permettre plusieurs sources.
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    yield {"type": "progress", "stage": "SCANNING", "percent": 15, "message": "Analyse des images sur la clé USB..."}
    
    image_files = []
    for root, dirs, files in os.walk(usb_path):
        for filename in files:
            if is_image_file(filename):
                image_files.append(Path(root) / filename)

    total = len(image_files)
    if total == 0:
        yield {"type": "error", "message": "Aucune image compatible trouvée sur la clé USB (formats supportés : JPG, JPEG, PNG, GIF)."}
        return

    yield {"type": "stats", "stage": "STATS", "percent": 20, "message": f"{total} images trouvées, début de l'import...", "total": total}

    for i, file_path in enumerate(image_files):
        try:
            dest_file = TARGET_DIR / file_path.name
            counter = 1
            original_dest = dest_file
            while dest_file.exists():
                stem = original_dest.stem
                suffix = original_dest.suffix
                dest_file = TARGET_DIR / f"{stem}_{counter}{suffix}"
                counter += 1
            
            shutil.copy2(file_path, dest_file)
            
            # La copie représente la phase de 20% à 80%
            percent = 20 + int(((i + 1) / total) * 60)
            yield {
                "type": "progress", "stage": "COPYING", "percent": percent,
                "message": f"Copie en cours... ({i + 1}/{total})",
                "current": i + 1, "total": total
            }
        except Exception as e:
            yield {"type": "warning", "message": f"Impossible de copier {file_path.name} : {str(e)}"}

    yield {"type": "done", "stage": "IMPORT_COMPLETE", "percent": 80, "message": f"{total} photos importées.", "total_imported": total}