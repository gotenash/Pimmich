import os
import requests
from utils.config import get_album_id_by_name
from utils.archive_manager import download_album_archive, unzip_archive, clean_archive
from utils.prepare_all_photos import prepare_all_photos


def download_and_extract_album(config):
    server_url = config.get("immich_url")
    api_key = config.get("immich_token")
    album_name = config.get("album_name")

    if not all([server_url, api_key, album_name]):
        raise ValueError("Configuration incomplète : serveur, token ou nom d'album manquant.")

    # Récupérer l'ID de l'album
    headers = {
        "x-api-key": api_key
    }
    album_list_url = f"{server_url}/api/albums"
    response = requests.get(album_list_url, headers=headers)

    if response.status_code != 200:
        raise ValueError(f"Impossible de récupérer les albums : {response.status_code} {response.text}")

    albums = response.json()
    album_id = next((album["id"] for album in albums if album["albumName"] == album_name), None)

    if not album_id:
        raise ValueError(f"Aucun album trouvé avec le nom : {album_name}")

    # Récupérer les assets de l'album
    assets_url = f"{server_url}/api/albums/{album_id}"
    response = requests.get(assets_url, headers=headers)

    if response.status_code != 200:
        raise ValueError(f"Impossible de récupérer les assets : {response.status_code} {response.text}")

    album_data = response.json()
    asset_ids = [asset["id"] for asset in album_data.get("assets", [])]

    if not asset_ids:
        raise ValueError("Aucun asset trouvé dans l'album.")

    # Télécharger l'archive ZIP des assets
    zip_path = "temp_album.zip"
    if not download_album_archive(server_url, api_key, asset_ids, zip_path):
        raise ValueError("Erreur lors du téléchargement de l'archive ZIP.")

    # Extraire l'archive dans static/photos
    photos_folder = os.path.join("static", "photos")
    if os.path.exists(photos_folder):
        for f in os.listdir(photos_folder):
            os.remove(os.path.join(photos_folder, f))

    unzip_archive(zip_path, photos_folder)
    clean_archive(zip_path)
    
    
    # Préparation des photos (centrage, fond flou, redimensionnement)
    try:
        from prepare_all_photos import prepare_all_photos
        print("[Préparation] Lancement de la préparation des photos…")
        prepare_all_photos()
        print("[Préparation] Terminé.")
    except Exception as e:
        print(f"[Erreur] lors de la préparation des photos : {e}")
