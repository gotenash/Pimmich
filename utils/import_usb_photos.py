import os
import shutil
import json
import subprocess
from pathlib import Path
import tempfile
import time

TARGET_DIR = Path("static/photos")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}

def is_image_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS

def find_and_mount_usb():
    """
    Recherche un périphérique USB. S'il est déjà monté, retourne le point de montage.
    Sinon, le monte dans un répertoire temporaire et retourne ce chemin.
    Retourne un tuple: (chemin_montage, chemin_périphérique, a_été_monté_par_script)
    """
    try:
        # Utiliser lsblk pour une détection fiable, en demandant le chemin du périphérique (PATH)
        result = subprocess.run(
            ['lsblk', '-J', '-o', 'NAME,MOUNTPOINT,TRAN,PATH'],
            capture_output=True, text=True, check=True, timeout=10
        )
        data = json.loads(result.stdout)
        
        for device in data.get('blockdevices', []):
            if device.get('tran') == 'usb':
                # Parcourir les partitions du périphérique
                for partition in device.get('children', []):
                    mountpoint = partition.get('mountpoint')
                    device_path = partition.get('path')

                    if not device_path:
                        continue

                    # Cas 1: Déjà monté par le système
                    if mountpoint:
                        print(f"Périphérique USB trouvé et déjà monté sur : {mountpoint}")
                        return Path(mountpoint), device_path, False

                    # Cas 2: Non monté, on le monte nous-mêmes
                    print(f"Périphérique USB non monté détecté : {device_path}. Tentative de montage...")
                    
                    # Créer un répertoire de montage temporaire
                    temp_mount_dir = tempfile.mkdtemp(prefix="pimmich_usb_")
                    
                    # Monter le périphérique avec les droits sudo
                    mount_cmd = ['sudo', 'mount', device_path, temp_mount_dir]
                    subprocess.run(mount_cmd, check=True, capture_output=True, text=True, timeout=15)
                    
                    print(f"Périphérique {device_path} monté avec succès sur {temp_mount_dir}")
                    return Path(temp_mount_dir), device_path, True

    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
        print(f"Erreur lors de la détection USB via lsblk : {e}. Assurez-vous que 'lsblk' est installé.")
    
    return None, None, False # Retourne None si rien n'est trouvé ou en cas d'erreur

def import_usb_photos():
    """Importe les photos depuis une clé USB, en la montant si nécessaire."""
    yield {"type": "progress", "stage": "SEARCHING", "percent": 5, "message": "Recherche de clés USB connectées..."}
    time.sleep(1)
    
    mount_path = None
    device_path = None
    mounted_by_script = False

    try:
        mount_path, device_path, mounted_by_script = find_and_mount_usb()
        
        if not mount_path:
            yield {"type": "error", "message": "Aucune clé USB détectée. Vérifiez la connexion et le format de la clé (ex: FAT32, exFAT)."}
            return

        yield {"type": "progress", "stage": "DETECTED", "percent": 10, "message": f"Clé USB détectée : {mount_path}"}

        # Vider le dossier de destination avant l'import pour éviter les mélanges.
        if TARGET_DIR.exists():
            shutil.rmtree(TARGET_DIR)
        TARGET_DIR.mkdir(parents=True, exist_ok=True)

        yield {"type": "progress", "stage": "SCANNING", "percent": 15, "message": "Analyse des images sur la clé USB..."}
        
        image_files = []
        for root, dirs, files in os.walk(mount_path):
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
                
                percent = 20 + int(((i + 1) / total) * 60)
                yield {
                    "type": "progress", "stage": "COPYING", "percent": percent,
                    "message": f"Copie en cours... ({i + 1}/{total})",
                    "current": i + 1, "total": total
                }
            except Exception as e:
                yield {"type": "warning", "message": f"Impossible de copier {file_path.name} : {str(e)}"}

        yield {"type": "done", "stage": "IMPORT_COMPLETE", "percent": 80, "message": f"{total} photos importées.", "total_imported": total}

    finally:
        # Cette section s'exécute toujours, même en cas d'erreur, pour nettoyer.
        if mounted_by_script and mount_path:
            yield {"type": "progress", "stage": "UNMOUNTING", "percent": 99, "message": "Démontage de la clé USB..."}
            time.sleep(1)
            try:
                umount_cmd = ['sudo', 'umount', str(mount_path)]
                subprocess.run(umount_cmd, check=True, capture_output=True, text=True, timeout=15)
                print(f"Démontage de {device_path} réussi.")
                # Supprimer le répertoire de montage temporaire
                shutil.rmtree(mount_path)
                print(f"Dossier de montage temporaire {mount_path} supprimé.")
            except Exception as e:
                yield {"type": "warning", "message": f"Avertissement : Impossible de démonter proprement la clé USB : {e}"}