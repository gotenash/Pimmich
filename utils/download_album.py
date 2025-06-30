import os
import requests
import time
from utils.config import get_album_id_by_name
from utils.archive_manager import download_album_archive, unzip_archive, clean_archive
from utils.prepare_all_photos import prepare_all_photos

def download_and_extract_album(config):
    server_url = config.get("immich_url")
    api_key = config.get("immich_token")
    album_name = config.get("album_name")

    if not all([server_url, api_key, album_name]):
        yield {"type": "error", "message": "Configuration incomplète : serveur, token ou nom d'album manquant."}
        return

    yield {"type": "progress", "stage": "CONNECTING", "percent": 5, "message": "Connexion à Immich..."}
    time.sleep(0.5)

    headers = { "x-api-key": api_key }
    album_list_url = f"{server_url}/api/albums"
    
    try:
        response = requests.get(album_list_url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        yield {"type": "error", "message": f"Impossible de se connecter au serveur Immich : {str(e)}"}
        return

    yield {"type": "progress", "stage": "SEARCHING", "percent": 10, "message": "Recherche de l'album..."}
    
    albums = response.json()
    album_id = next((album["id"] for album in albums if album["albumName"] == album_name), None)
    if not album_id:
        available_albums = [album["albumName"] for album in albums[:5]]  # Limiter à 5 pour l'affichage
        yield {"type": "error", "message": f"Album '{album_name}' introuvable. Albums disponibles : {', '.join(available_albums)}"}
        return

    yield {"type": "progress", "stage": "FETCHING_ASSETS", "percent": 15, "message": "Récupération de la liste des photos..."}

    assets_url = f"{server_url}/api/albums/{album_id}"
    response = requests.get(assets_url, headers=headers, timeout=30)
    response.raise_for_status()

    album_data = response.json()
    asset_ids = [asset["id"] for asset in album_data.get("assets", [])]

    if not asset_ids:
        yield {"type": "error", "message": "L'album est vide ou ne contient aucune photo accessible."}
        return
    
    nb_photos = len(asset_ids)
    yield {"type": "progress", "stage": "DOWNLOADING", "percent": 25, "message": f"Téléchargement de l'archive ({nb_photos} photos)..."}

    zip_path = "temp_album.zip"
    
    try:
        if not download_album_archive(server_url, api_key, asset_ids, zip_path):
            yield {"type": "error", "message": "Échec du téléchargement de l'archive."}
            return
    except Exception as e:
        yield {"type": "error", "message": f"Erreur critique lors du téléchargement : {str(e)}"}
        return

    yield {"type": "progress", "stage": "EXTRACTING", "percent": 60, "message": "Extraction des photos..."}
    photos_folder = os.path.join("static", "photos")
    # S'assurer que le dossier existe sans le vider, pour permettre plusieurs sources.
    os.makedirs(photos_folder, exist_ok=True)
    try:
        unzip_archive(zip_path, photos_folder)
        clean_archive(zip_path)
    except Exception as e:
        yield {"type": "error", "message": f"Erreur lors de l'extraction : {str(e)}"}
        return

    yield {"type": "done", "stage": "DOWNLOAD_COMPLETE", "percent": 80, "message": f"{nb_photos} photos prêtes pour préparation.", "total_downloaded": nb_photos}
