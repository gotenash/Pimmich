import os
import shutil
from pathlib import Path
import smbclient
from smbprotocol.exceptions import SMBException

TARGET_DIR = Path("static/photos")
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.heic', '.heif'}

def is_image_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS

def import_samba_photos(config):
    """
    Synchronise les photos depuis un partage Samba et retourne des objets structurés pour le suivi.
    Copie uniquement les fichiers nouveaux ou modifiés et supprime les fichiers locaux obsolètes.
    """
    server = config.get("smb_host")
    share = config.get("smb_share")
    path = config.get("smb_path", "")
    user = config.get("smb_user")
    password = config.get("smb_password")

    if not all([server, share]):
        yield {"type": "error", "message": "Configuration Samba incomplète : serveur ou nom de partage manquant."}
        return

    # Construction robuste du chemin UNC pour éviter les problèmes de slashs finaux.
    path_in_share = path.strip('/')
    if path_in_share:
        full_samba_path = f"//{server}/{share}/{path_in_share}"
    else:
        full_samba_path = f"//{server}/{share}"
    yield {"type": "progress", "stage": "CONNECTING", "percent": 5, "message": f"Connexion à {full_samba_path}..."}

    try:
        # On ne gère plus les sessions manuellement pour être compatible avec d'anciennes versions de smbclient.
        # Les identifiants sont passés directement aux fonctions.
        if not smbclient.path.exists(full_samba_path, username=user, password=password, connection_timeout=15):
            yield {"type": "error", "message": f"Le chemin Samba est introuvable : {full_samba_path}"}
            return

        # --- Phase 1: Lister les fichiers distants et locaux ---
        yield {"type": "progress", "stage": "SCANNING", "percent": 10, "message": "Analyse des fichiers distants et locaux..."}
        
        # Récupérer les fichiers distants avec leur date de modification
        remote_files = {}
        for filename in smbclient.listdir(full_samba_path, username=user, password=password):
            if is_image_file(filename):
                try:
                    remote_file_path = os.path.join(full_samba_path, filename)
                    if smbclient.path.isfile(remote_file_path, username=user, password=password):
                        stat_info = smbclient.stat(remote_file_path, username=user, password=password)
                        remote_files[filename] = stat_info.st_mtime
                except Exception as e:
                    yield {"type": "warning", "message": f"Impossible d'accéder aux informations de {filename}: {e}"}

        # Récupérer les fichiers locaux avec leur date de modification
        TARGET_DIR.mkdir(parents=True, exist_ok=True)
        local_files = {f.name: f.stat().st_mtime for f in TARGET_DIR.iterdir() if f.is_file()}

        # --- Phase 2: Déterminer les actions à effectuer ---
        files_to_copy = {f for f, mtime in remote_files.items() if f not in local_files or mtime > local_files.get(f, 0)}
        files_to_delete = {f for f in local_files if f not in remote_files}

        # --- Phase 3: Supprimer les fichiers locaux obsolètes ---
        if files_to_delete:
            yield {"type": "progress", "stage": "CLEANING", "percent": 15, "message": f"Suppression de {len(files_to_delete)} photos obsolètes..."}
            for filename in files_to_delete:
                try:
                    (TARGET_DIR / filename).unlink()
                except OSError as e:
                    yield {"type": "warning", "message": f"Impossible de supprimer {filename}: {e}"}

        # --- Phase 4: Copier les fichiers nouveaux ou modifiés ---
        total_to_copy = len(files_to_copy)
        if total_to_copy == 0:
            yield {"type": "info", "message": "Aucune nouvelle photo à importer. Le dossier est à jour."}
            yield {"type": "done", "stage": "IMPORT_COMPLETE", "percent": 100, "message": "Synchronisation terminée. Aucune nouvelle photo."}
            return

        yield {"type": "stats", "stage": "COPYING", "percent": 20, "message": f"Début de la copie de {total_to_copy} photos...", "total": total_to_copy}

        for i, filename in enumerate(sorted(list(files_to_copy)), 1):
            source_file = os.path.join(full_samba_path, filename)
            dest_file = TARGET_DIR / filename
            
            try:
                with smbclient.open_file(source_file, mode='rb', username=user, password=password) as remote_f:
                    with open(dest_file, 'wb') as local_f:
                        shutil.copyfileobj(remote_f, local_f)
                
                # Mettre à jour la date de modification du fichier local pour correspondre au distant
                os.utime(dest_file, (remote_files[filename], remote_files[filename]))

                percent = 20 + int((i / total_to_copy) * 60) # La copie représente 60% de la barre (de 20% à 80%)
                yield {
                    "type": "progress", "stage": "COPYING", "percent": percent,
                    "message": f"Copie en cours... ({i}/{total_to_copy})",
                    "current": i, "total": total_to_copy
                }
            except Exception as e:
                yield {"type": "warning", "message": f"Impossible de copier {filename}: {str(e)}"}

        yield {"type": "done", "stage": "IMPORT_COMPLETE", "percent": 80, "message": f"{total_to_copy} photos synchronisées.", "total_imported": total_to_copy}

    except SMBException as e:
        yield {"type": "error", "message": f"Erreur Samba : {str(e)}"}
    except Exception as e:
        yield {"type": "error", "message": f"Erreur inattendue : {str(e)}"}