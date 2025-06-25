import os
from pathlib import Path
import smbclient
from smbprotocol.exceptions import SMBException

TARGET_DIR = Path("static/photos")
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.heic', '.heif'}

def is_image_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS

def import_samba_photos(config):
    """
    Importe les photos depuis un partage Samba et retourne des objets structurés pour le suivi.
    """
    server = config.get("smb_host")
    share = config.get("smb_share")
    path = config.get("smb_path", "")
    user = config.get("smb_user")
    password = config.get("smb_password")

    if not all([server, share]):
        yield {"type": "error", "message": "Configuration Samba incomplète : serveur ou nom de partage manquant."}
        return

    full_samba_path = f"\\\\{server}\\{share}\\{path}".replace('/', '\\')
    yield {"type": "progress", "stage": "CONNECTING", "percent": 5, "message": f"Connexion à {full_samba_path}..."}

    try:
        # Enregistre la session si un utilisateur/mot de passe est fourni
        if user and password:
            smbclient.register_session(server, username=user, password=password)

        if not smbclient.path.exists(full_samba_path):
            yield {"type": "error", "message": f"Le chemin Samba n'existe pas : {full_samba_path}"}
            return

        yield {"type": "progress", "stage": "SCANNING", "percent": 15, "message": "Analyse des images sur le partage..."}
        
        all_files = smbclient.listdir(full_samba_path)
        image_files = [f for f in all_files if is_image_file(f) and smbclient.path.isfile(os.path.join(full_samba_path, f))]
        total = len(image_files)

        if total == 0:
            yield {"type": "warning", "message": "Aucune image compatible trouvée sur le partage Samba."}
            return

        yield {"type": "stats", "stage": "STATS", "percent": 25, "message": f"{total} images trouvées, début de l'import...", "total": total}

        # Nettoyage du dossier de destination
        if TARGET_DIR.exists():
            for f in TARGET_DIR.glob('*'):
                f.unlink()
        TARGET_DIR.mkdir(parents=True, exist_ok=True)

        for i, filename in enumerate(image_files, 1):
            source_file = os.path.join(full_samba_path, filename)
            dest_file = TARGET_DIR / filename
            
            try:
                with smbclient.open_file(source_file, mode='rb') as remote_f:
                    with open(dest_file, 'wb') as local_f:
                        local_f.write(remote_f.read())
                
                percent = 25 + int((i / total) * 55) # La copie représente 55% de la barre (de 25% à 80%)
                yield {
                    "type": "progress", "stage": "COPYING", "percent": percent,
                    "message": f"Copie en cours... ({i}/{total})",
                    "current": i, "total": total
                }
            except Exception as e:
                yield {"type": "warning", "message": f"Impossible de copier {filename}: {str(e)}"}

        yield {"type": "done", "stage": "IMPORT_COMPLETE", "percent": 80, "message": f"{total} photos importées.", "total_imported": total}

    except SMBException as e:
        yield {"type": "error", "message": f"Erreur Samba : {str(e)}"}
    except Exception as e:
        yield {"type": "error", "message": f"Erreur inattendue : {str(e)}"}