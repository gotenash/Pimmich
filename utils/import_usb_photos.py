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
                if mount.is_dir() and any(f.is_file() and is_image_file(f.name) for f in mount.iterdir() if f.is_file()):
                    return mount
    return None

def import_usb_photos():
    """Version améliorée avec meilleur feedback"""
    yield "[RECHERCHE] Recherche de clés USB connectées...\n"
    time.sleep(1)  # Simuler le temps de recherche
    
    usb_path = find_usb_mount_point()
    if not usb_path:
        yield "[ERREUR] Aucune clé USB avec des images détectée.\n"
        yield "[INFO] Vérifiez que la clé USB est bien connectée et contient des fichiers image.\n"
        return

    yield f"[DETECTE] Clé USB détectée : {usb_path}\n"
    yield "[NETTOYAGE] Nettoyage du dossier de destination...\n"

    # Nettoyage du dossier cible
    if TARGET_DIR.exists():
        shutil.rmtree(TARGET_DIR)
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    yield "[SCAN] Scan des images sur la clé USB...\n"
    
    # Récupération des fichiers image avec feedback
    image_files = []
    scanned_dirs = 0
    
    for root, dirs, files in os.walk(usb_path):
        scanned_dirs += 1
        if scanned_dirs % 10 == 0:  # Feedback tous les 10 dossiers
            yield f"[SCAN] Scan en cours... {scanned_dirs} dossiers analysés\n"
        
        for filename in files:
            if is_image_file(filename):
                image_files.append(Path(root) / filename)

    total = len(image_files)
    if total == 0:
        yield "[ERREUR] Aucune image compatible trouvée sur la clé USB.\n"
        yield "[INFO] Formats supportés : JPG, JPEG, PNG, GIF\n"
        return

    yield f"[STATS] {total} images trouvées, début de l'import...\n"

    # Copie avec progression améliorée
    for i, file_path in enumerate(image_files):
        try:
            dest_file = TARGET_DIR / file_path.name
            
            # Éviter les doublons en renommant si nécessaire
            counter = 1
            original_dest = dest_file
            while dest_file.exists():
                stem = original_dest.stem
                suffix = original_dest.suffix
                dest_file = TARGET_DIR / f"{stem}_{counter}{suffix}"
                counter += 1
            
            shutil.copy2(file_path, dest_file)
            
            progress = int((i + 1) / total * 80)  # 80% max pour l'import
            
            # Messages de progression plus détaillés
            if (i + 1) % max(1, total // 10) == 0 or i == total - 1:
                yield f"[IMPORT] Import en cours... {progress}% ({i + 1}/{total} photos)\n"
            
        except Exception as e:
            yield f"[ALERTE] Impossible de copier {file_path.name} : {str(e)}\n"

    yield f"[INFO] {total} photos importées depuis la clé USB.\n"
