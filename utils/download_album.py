import os
import requests
from utils.config import get_album_id_by_name
from utils.archive_manager import download_album_archive, unzip_archive, clean_archive
from utils.prepare_all_photos import prepare_all_photos

def download_and_extract_album(config, status_callback=None):
    import requests
    import time

    def update_status(message):
        if status_callback:
            status_callback(message)

    server_url = config.get("immich_url")
    api_key = config.get("immich_token")
    album_name = config.get("album_name")

    if not all([server_url, api_key, album_name]):
        raise ValueError("[ERREUR] Configuration incomplète : serveur, token ou nom d'album manquant.")

    update_status("5% [CONNEXION] Connexion à Immich...")
    time.sleep(0.5)

    headers = { "x-api-key": api_key }
    album_list_url = f"{server_url}/api/albums"
    
    try:
        response = requests.get(album_list_url, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
        raise ValueError(f"[ERREUR] Impossible de se connecter au serveur Immich : {str(e)}")

    if response.status_code != 200:
        raise ValueError(f"[ERREUR] Erreur serveur Immich : {response.status_code} {response.text}")

    update_status("10% [RECHERCHE] Recherche de l'album...")
    
    albums = response.json()
    album_id = next((album["id"] for album in albums if album["albumName"] == album_name), None)
    if not album_id:
        available_albums = [album["albumName"] for album in albums[:5]]  # Limiter à 5 pour l'affichage
        raise ValueError(f"[ERREUR] Album '{album_name}' introuvable. Albums disponibles : {', '.join(available_albums)}")

    update_status("15% [LISTE] Récupération de la liste des photos...")

    assets_url = f"{server_url}/api/albums/{album_id}"
    response = requests.get(assets_url, headers=headers, timeout=30)
    if response.status_code != 200:
        raise ValueError(f"[ERREUR] Impossible de récupérer les photos : {response.status_code} {response.text}")

    album_data = response.json()
    asset_ids = [asset["id"] for asset in album_data.get("assets", [])]

    if not asset_ids:
        raise ValueError("[ERREUR] L'album est vide ou ne contient aucune photo accessible.")
    
    nb_photos = len(asset_ids)
    update_status(f"25% [ARCHIVE] Téléchargement de l'archive ({nb_photos} photos)...")

    from utils.archive_manager import download_album_archive, unzip_archive, clean_archive
    zip_path = "temp_album.zip"
    
    # Téléchargement avec retry
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if download_album_archive(server_url, api_key, asset_ids, zip_path):
                break
            else:
                if attempt == max_retries - 1:
                    raise ValueError("[ERREUR] Échec du téléchargement après plusieurs tentatives.")
                update_status(f"[RETRY] Tentative {attempt + 1}/{max_retries} échouée, nouvel essai...")
                time.sleep(2)
        except Exception as e:
            if attempt == max_retries - 1:
                raise ValueError(f"[ERREUR] Erreur lors du téléchargement : {str(e)}")
            time.sleep(2)

    update_status("60% [EXTRACTION] Extraction des photos...")
    photos_folder = os.path.join("static", "photos")
    
    # Nettoyage avec feedback
    if os.path.exists(photos_folder):
        for f in os.listdir(photos_folder):
            os.remove(os.path.join(photos_folder, f))
    
    try:
        unzip_archive(zip_path, photos_folder)
        clean_archive(zip_path)
    except Exception as e:
        raise ValueError(f"[ERREUR] Erreur lors de l'extraction : {str(e)}")

    update_status(f"80% [PRET] {nb_photos} photos prêtes pour préparation.")

    return nb_photos
