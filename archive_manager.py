import os
import requests
import zipfile
import shutil

def download_album_archive(server_url, api_key, asset_ids, output_zip_path):
    """
    Télécharge une archive ZIP contenant les assets donnés (par leurs IDs) depuis l'API Immich.
    """
    url = f"{server_url}/api/download/archive"
    payload = {
        "assetIds": asset_ids
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "Accept": "application/octet-stream"
    }

    response = requests.post(url, json=payload, headers=headers, stream=True)
    if response.status_code == 200:
        with open(output_zip_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    else:
        print(f"Erreur téléchargement archive: {response.status_code} {response.text}")
        return False


def unzip_archive(zip_path, extract_to_folder):
    """
    Extrait le contenu de l'archive ZIP dans un dossier donné.
    """
    if not os.path.exists(extract_to_folder):
        os.makedirs(extract_to_folder)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to_folder)


def clean_archive(zip_path):
    """
    Supprime l'archive ZIP une fois extraite.
    """
    if os.path.exists(zip_path):
        os.remove(zip_path)
