<<<<<<< HEAD
import os
import shutil
from pathlib import Path
from smbclient import register_session, listdir, open_file, remove_session, path as smb_path
from smbprotocol.exceptions import SMBException

# Destination folder for photos before preparation
PHOTOS_DIR = Path("static/photos")
# Supported image extensions
SUPPORTED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.heic', '.heif']

def import_samba_photos(config):
    """
    Connects to an SMB share, lists, and copies image files to a local directory.
    This is a generator function that yields progress updates.
    """
    host = config.get("smb_host")
    share = config.get("smb_share")
    user = config.get("smb_user")
    password = config.get("smb_password")
    remote_path_str = config.get("smb_path", "/").strip("/")

    if not all([host, share]):
        yield {"type": "error", "message": "Configuration SMB incomplète : Hôte ou Partage manquant."}
        return

    # Construct the full UNC path
    full_remote_path_unc = f"\\\\{host}\\{share}"
    if remote_path_str:
        full_remote_path_unc += f"\\{remote_path_str.replace('/', '\\')}"

    yield {"type": "progress", "stage": "CONNECTING", "percent": 5, "message": f"Connexion à {full_remote_path_unc}"}

    session_registered = False
    try:
        # Register session if credentials are provided
        if user and password:
            register_session(host, username=user, password=password)
            session_registered = True

        if not smb_path.exists(full_remote_path_unc):
            yield {"type": "error", "message": f"Le chemin distant est introuvable : {full_remote_path_unc}"}
            return

        yield {"type": "progress", "stage": "LISTING", "percent": 10, "message": "Liste des fichiers distants..."}
        
        remote_files = listdir(full_remote_path_unc)
        image_files = [f for f in remote_files if Path(f).suffix.lower() in SUPPORTED_EXTENSIONS and not smb_path.isdir(os.path.join(full_remote_path_unc, f))]
        
        if not image_files:
            yield {"type": "warning", "message": f"Aucune photo trouvée dans le dossier : {full_remote_path_unc}"}
            yield {"type": "done", "percent": 100, "message": "Aucune nouvelle photo à importer."}
            return

        total_files = len(image_files)
        yield {"type": "progress", "stage": "PREPARING_IMPORT", "percent": 20, "message": f"{total_files} photos trouvées. Nettoyage du dossier local..."}

        PHOTOS_DIR.mkdir(exist_ok=True)
        for f in PHOTOS_DIR.iterdir():
            if f.is_file():
                f.unlink()

        yield {"type": "progress", "stage": "COPYING", "percent": 20, "message": f"Début de la copie de {total_files} photos..."}
        for i, filename in enumerate(image_files, start=1):
            remote_file_path = os.path.join(full_remote_path_unc, filename)
            local_file_path = PHOTOS_DIR / filename
            percent = 20 + int((i / total_files) * 60)
            
            with open_file(remote_file_path, mode='rb') as remote_f, open(local_file_path, 'wb') as local_f:
                shutil.copyfileobj(remote_f, local_f)
            yield {"type": "progress", "stage": "COPYING", "percent": percent, "message": f"Copie de {filename} ({i}/{total_files})"}

        yield {"type": "done", "percent": 80, "message": f"Copie terminée. {total_files} photos importées."}

    except SMBException as e:
        yield {"type": "error", "message": f"Erreur SMB : {e}"}
    except Exception as e:
        yield {"type": "error", "message": f"Erreur inattendue : {e}"}
    finally:
        if session_registered:
            try:
                remove_session(host)
            except Exception:
=======
import os
import shutil
from pathlib import Path
from smbclient import register_session, listdir, open_file, remove_session, path as smb_path
from smbprotocol.exceptions import SMBException

# Destination folder for photos before preparation
PHOTOS_DIR = Path("static/photos")
# Supported image extensions
SUPPORTED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.heic', '.heif']

def import_samba_photos(config):
    """
    Connects to an SMB share, lists, and copies image files to a local directory.
    This is a generator function that yields progress updates.
    """
    host = config.get("smb_host")
    share = config.get("smb_share")
    user = config.get("smb_user")
    password = config.get("smb_password")
    remote_path_str = config.get("smb_path", "/").strip("/")

    if not all([host, share]):
        yield {"type": "error", "message": "Configuration SMB incomplète : Hôte ou Partage manquant."}
        return

    # Construct the full UNC path
    full_remote_path_unc = f"\\\\{host}\\{share}"
    if remote_path_str:
        full_remote_path_unc += f"\\{remote_path_str.replace('/', '\\')}"

    yield {"type": "progress", "stage": "CONNECTING", "percent": 5, "message": f"Connexion à {full_remote_path_unc}"}

    session_registered = False
    try:
        # Register session if credentials are provided
        if user and password:
            register_session(host, username=user, password=password)
            session_registered = True

        if not smb_path.exists(full_remote_path_unc):
            yield {"type": "error", "message": f"Le chemin distant est introuvable : {full_remote_path_unc}"}
            return

        yield {"type": "progress", "stage": "LISTING", "percent": 10, "message": "Liste des fichiers distants..."}
        
        remote_files = listdir(full_remote_path_unc)
        image_files = [f for f in remote_files if Path(f).suffix.lower() in SUPPORTED_EXTENSIONS and not smb_path.isdir(os.path.join(full_remote_path_unc, f))]
        
        if not image_files:
            yield {"type": "warning", "message": f"Aucune photo trouvée dans le dossier : {full_remote_path_unc}"}
            yield {"type": "done", "percent": 100, "message": "Aucune nouvelle photo à importer."}
            return

        total_files = len(image_files)
        yield {"type": "progress", "stage": "PREPARING_IMPORT", "percent": 20, "message": f"{total_files} photos trouvées. Nettoyage du dossier local..."}

        PHOTOS_DIR.mkdir(exist_ok=True)
        for f in PHOTOS_DIR.iterdir():
            if f.is_file():
                f.unlink()

        yield {"type": "progress", "stage": "COPYING", "percent": 20, "message": f"Début de la copie de {total_files} photos..."}
        for i, filename in enumerate(image_files, start=1):
            remote_file_path = os.path.join(full_remote_path_unc, filename)
            local_file_path = PHOTOS_DIR / filename
            percent = 20 + int((i / total_files) * 60)
            
            with open_file(remote_file_path, mode='rb') as remote_f, open(local_file_path, 'wb') as local_f:
                shutil.copyfileobj(remote_f, local_f)
            yield {"type": "progress", "stage": "COPYING", "percent": percent, "message": f"Copie de {filename} ({i}/{total_files})"}

        yield {"type": "done", "percent": 80, "message": f"Copie terminée. {total_files} photos importées."}

    except SMBException as e:
        yield {"type": "error", "message": f"Erreur SMB : {e}"}
    except Exception as e:
        yield {"type": "error", "message": f"Erreur inattendue : {e}"}
    finally:
        if session_registered:
            try:
                remove_session(host)
            except Exception:
>>>>>>> 3363f89ea41d3158a19361a4baae8bd99d8e9f99
                pass