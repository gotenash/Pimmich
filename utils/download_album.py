import os
import requests
import shutil
import time
import json
from pathlib import Path
from utils.archive_manager import download_album_archive, unzip_archive, clean_archive

# Définir le chemin du cache pour le mappage des descriptions
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)
DESCRIPTION_MAP_CACHE_FILE = CACHE_DIR / "immich_description_map.json"

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
    assets = album_data.get("assets", [])
    asset_ids = [asset["id"] for asset in assets]

    if not asset_ids:
        yield {"type": "error", "message": "L'album est vide ou ne contient aucune photo accessible."}
        return
    
    # Créer un mappage nom de fichier -> description
    filename_to_description_map = {}
    for asset in assets:
        original_filename = asset.get("originalFileName")
        # La description est dans exifInfo
        description = asset.get("exifInfo", {}).get("description")
        if original_filename and description:
            filename_to_description_map[original_filename] = description

    # Sauvegarder le mappage dans un fichier cache pour que l'étape de préparation puisse l'utiliser.
    try:
        with open(DESCRIPTION_MAP_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(filename_to_description_map, f, ensure_ascii=False, indent=2)
        print(f"[Immich Import] Mappage des descriptions sauvegardé dans {DESCRIPTION_MAP_CACHE_FILE}")
    except Exception as e:
        # On ne bloque pas le processus, on affiche juste un avertissement.
        yield {"type": "warning", "message": f"Avertissement : Impossible de sauvegarder le mappage des descriptions : {e}"}

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
    photos_folder = os.path.join("static", "photos", "immich")
    prepared_folder = os.path.join("static", "prepared", "immich")

    # Vider les dossiers de destination (source et préparé) avant l'import pour éviter les mélanges.
    if os.path.exists(photos_folder):
        shutil.rmtree(photos_folder)
    os.makedirs(photos_folder, exist_ok=True)

    if os.path.exists(prepared_folder):
        shutil.rmtree(prepared_folder)
    os.makedirs(prepared_folder, exist_ok=True)

    try:
        unzip_archive(zip_path, photos_folder)
        clean_archive(zip_path)
    except Exception as e:
        yield {"type": "error", "message": f"Erreur lors de l'extraction : {str(e)}"}
        return

    yield { "type": "done", "stage": "DOWNLOAD_COMPLETE", "percent": 80, "message": f"{nb_photos} photos prêtes pour préparation.", "total_downloaded": nb_photos }
