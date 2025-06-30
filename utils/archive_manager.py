import os
import zipfile
import requests

def download_album_archive(server_url, api_key, asset_ids, zip_path):
    url = f"{server_url}/api/download/archive"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    data = {"assetIds": asset_ids}

    # Utilisation du streaming pour éviter de charger toute l'archive en mémoire.
    # Ajout d'un timeout généreux car la création de l'archive peut être longue.
    try:
        response = requests.post(url, json=data, headers=headers, stream=True, timeout=(10, 300)) # 10s connect, 5min read

        if response.status_code != 200:
            print(f"Erreur Immich API: {response.status_code} - {response.text}")
            return False

        # Écrire le contenu dans le fichier par morceaux (chunks)
        with open(zip_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except requests.exceptions.RequestException as e:
        print(f"Erreur réseau lors du téléchargement de l'archive : {e}")
        return False

def unzip_archive(zip_path, extract_to):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print("Archive extraite avec succes.")
    except Exception as e:
        print(f"Erreur lors de l'extraction : {e}")

def clean_archive(zip_path):
    try:
        if os.path.exists(zip_path):
            os.remove(zip_path)
            print("Archive supprimee apres extraction.")
    except Exception as e:
        print(f"Erreur lors de la suppression de l'archive : {e}")
