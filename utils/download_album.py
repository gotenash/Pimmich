import os
import random
import requests
import shutil
import time
import json
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

from utils.archive_manager import unzip_archive, clean_archive
from .config_manager import load_config

# Définir le chemin du cache pour le mappage des descriptions
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)
DESCRIPTION_MAP_CACHE_FILE = CACHE_DIR / "immich_description_map.json"

# ============================================================
# Configuration du logging avec émojis
# ============================================================

LOGSDIR = Path(__file__).resolve().parent.parent / "logs"
LOGSDIR.mkdir(exist_ok=True)


class EmojiFormatter(logging.Formatter):
    """Formatter personnalisé avec émojis selon le niveau."""

    EMOJI_MAP = {
        "DEBUG": "🔍",
        "INFO": "ℹ️",
        "WARNING": "😒",
        "ERROR": "❌",
        "CRITICAL": "🔥",
    }

    def format(self, record):
        emoji = self.EMOJI_MAP.get(record.levelname, "")
        record.emoji = emoji
        return super().format(record)


# Charger la configuration
config = load_config()

# Créer un logger spécifique pour ce module
logger = logging.getLogger("pimmich.download_album")

# Récupérer le niveau de log depuis la configuration
level_name = config.get("level_log", "INFO")
level = getattr(logging, level_name.upper(), logging.INFO)
logger.setLevel(level)
logger.propagate = False
# Handler fichier avec rotation (10 Mo max, 3 backups)
file_handler = RotatingFileHandler(
    LOGSDIR / "pimmich.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
file_handler.setLevel(level)

# Format modernisé avec emoji en début de ligne
file_formatter = EmojiFormatter(
    "%(emoji)s📥️%(asctime)s 📥️%(message)s",
    datefmt="%d-%m %H:%M:%S",
)
file_handler.setFormatter(file_formatter)

# Ajouter les handlers (éviter doublons si module réimporté)
if not logger.handlers:
    logger.addHandler(file_handler)

# Messages de démarrage
logger.debug("----------------Initialisation Download Album----------------")

# ============================================================
# Helper yield + log
# ============================================================

TYPE_TO_LOGGER = {
    "progress": logger.info,
    "info": logger.info,
    "warning": logger.warning,
    "error": logger.error,
    "done": logger.info,
}


def yield_and_log(
    msg_type: str,
    message: str,
    stage: str | None = None,
    percent: int | None = None,
    extra: dict | None = None,
):
    """
    Construit un dict pour yield + écrit dans les logs.
    - msg_type : "progress" | "info" | "warning" | "error" | "done" ...
    """
    data = {"type": msg_type, "message": message}
    if stage is not None:
        data["stage"] = stage
    if percent is not None:
        data["percent"] = str(percent)
    if extra:
        data.update(extra)

    log_func = TYPE_TO_LOGGER.get(msg_type, logger.info)
    log_func(message)

    return data


def download_album_archive_local(server_url, api_key, asset_ids, zip_path):
    """
    Télécharge l'archive ZIP contenant les assets demandés.
    Remplace la fonction de utils.archive_manager pour plus de contrôle et de logs.
    """
    # Endpoint standard pour les versions récentes d'Immich
    url = f"{server_url}/api/download/archive"
    
    headers = {
        'Accept': 'application/octet-stream',
        'Content-Type': 'application/json',
        'x-api-key': api_key
    }
    
    payload = {
        "assetIds": asset_ids
    }
    
    try:
        # On augmente le timeout à 60s pour la connexion et 300s (5min) pour la lecture
        # car la génération du zip côté serveur peut être longue pour beaucoup de photos
        with requests.post(url, json=payload, headers=headers, stream=True, timeout=(60, 300)) as response:
            if response.status_code != 200:
                logger.error(f"Erreur API Immich ({response.status_code}): {response.text}")
                return False, f"Erreur API: {response.status_code}"
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192): 
                    f.write(chunk)
        
        return True, "OK"
        
    except requests.exceptions.Timeout:
        logger.error("Timeout lors du téléchargement de l'archive Immich.")
        return False, "Timeout serveur (trop long)"
    except Exception as e:
        logger.error(f"Exception lors du téléchargement: {e}")
        return False, str(e)


def download_and_extract_album(config):
    server_url = config.get("immich_url")
    api_key = config.get("immich_token")
    album_name = config.get("album_name")

    # Récupération de max_photos_to_download depuis la configuration
    max_photos_config = config.get("max_photos_to_download", {"immich": 10})

    random_content_in_album = config.get("random_content_in_album", True)

    # Gérer les deux formats possibles (dict ou int)
    if isinstance(max_photos_config, dict):
        raw_max_photos = max_photos_config.get("immich", 10)
    else:
        raw_max_photos = max_photos_config

    # Normaliser et gérer les valeurs "illimitées"
    try:
        if raw_max_photos in (None, "", "0", "-1", 0, -1):
            max_photos_to_download = None  # None = illimité
        else:
            max_photos_to_download = int(raw_max_photos)
    except (ValueError, TypeError):
        # En cas de valeur non convertible, on garde la valeur par défaut
        max_photos_to_download = 10

    if not all([server_url, api_key]):
        yield yield_and_log(
            msg_type="error",
            message="Configuration incomplète : url du serveur ou clé API manquant.",
        )
        return

    yield yield_and_log(
        msg_type="progress",
        stage="CONNECTING",
        percent=2,
        message="Connexion à Immich...",
    )
    time.sleep(0.5)

    headers = {"x-api-key": api_key}

    # Modification Sigalou 25/01/2026 - Gestion mode album OU mode aléatoire
    if album_name and album_name.strip():
        # MODE ALBUM : Récupérer les photos d'un album spécifique
        yield yield_and_log(
            msg_type="progress",
            stage="SEARCHING",
            percent=4,
            message=f"Recherche de l'album '{album_name}'...",
        )

        album_list_url = f"{server_url}/api/albums"

        try:
            response = requests.get(album_list_url, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            yield yield_and_log(
                msg_type="error",
                message=f"Impossible de se connecter au serveur Immich : {str(e)}",
            )
            return

        albums = response.json()
        album_id = next(
            (album["id"] for album in albums if album["albumName"] == album_name), None
        )

        if not album_id:
            available_albums = [album["albumName"] for album in albums[:5]]  # Limiter à 5 pour l'affichage
            yield yield_and_log(
                msg_type="error",
                message=(
                    f"Album '{album_name}' introuvable. "
                    f"Albums disponibles : {', '.join(available_albums)}"
                ),
            )
            return

        # yield {"type": "progress", "stage": "FETCHING_ASSETS", "percent": 15, "message": "Récupération de la liste des photos..."}

        assets_url = f"{server_url}/api/albums/{album_id}"
        response = requests.get(assets_url, headers=headers, timeout=30)
        response.raise_for_status()
        album_data = response.json()
        assets = album_data.get("assets", [])

        # Application de la limite max_photos_to_download
        total_assets = len(assets)
        if max_photos_to_download is not None and total_assets > max_photos_to_download:
            yield yield_and_log(
                msg_type="info",
                message=(
                    f"L'album contient {total_assets} photos. "
                    f"Limitation à {max_photos_to_download} photos."
                ),
            )
            if random_content_in_album:
                assets = random.choices(assets, k=max_photos_to_download)
            else:
                assets = assets[:max_photos_to_download]

    else:
        # MODE ALÉATOIRE : Récupérer des photos aléatoires avec leurs métadonnées complètes
        size = max_photos_to_download if max_photos_to_download is not None else 500

        yield yield_and_log(
            msg_type="progress",
            stage="FETCHING_RANDOM",
            percent=4,
            message=f"Récupération de {size} photos aléatoires...",
        )

        random_url = f"{server_url}/api/search/random"
        payload = {"size": size}

        try:
            response = requests.post(
                random_url, headers=headers, json=payload, timeout=30
            )
            response.raise_for_status()
            assets_light = response.json()

            # yield {"type": "progress", "stage": "FETCHING_ASSETS", "percent": 12, "message": "Récupération de la liste des photos..."}

            # Modification Sigalou 25/01/2026 - Enrichir avec les détails complets via API asset
            # L'API /search/random ne renvoie pas les exifInfo, donc on appelle /assets/{id} pour chaque photo
            assets = []
            for i, asset_light in enumerate(assets_light):
                asset_id = asset_light.get("id")
                if asset_id:
                    try:
                        asset_detail_url = f"{server_url}/api/assets/{asset_id}"
                        detail_response = requests.get(
                            asset_detail_url, headers=headers, timeout=10
                        )
                        if detail_response.status_code == 200:
                            assets.append(detail_response.json())
                        else:
                            assets.append(asset_light)  # Fallback si l'API échoue
                    except Exception:
                        assets.append(asset_light)  # Fallback en cas d'erreur
            # Fin Modification Sigalou 25/01/2026

        except requests.exceptions.RequestException as e:
            yield yield_and_log(
                msg_type="error",
                message=f"Impossible de récupérer les photos aléatoires : {str(e)}",
            )
            return

    # Fin Modification Sigalou 25/01/2026

    # Modification Sigalou 26/01/2026 - Cache COMPLET exifInfo (RAW)
    filename_to_metadata_map = {}
    total_assets = 0
    photos_with_metadata = 0

    for asset in assets:
        total_assets += 1
        original_filename = asset.get("originalFileName")
        if not original_filename:
            continue

        # ⚡ STOCKE TOUT exifInfo brut (sans filtrage)
        exif_info = asset.get("exifInfo", {})

        # Compte seulement si exifInfo n'est pas vide
        if exif_info:
            photos_with_metadata += 1

        filename_to_metadata_map[original_filename] = exif_info  # ← SIMPLE !

    # Sauvegarde
    try:
        with open(DESCRIPTION_MAP_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(filename_to_metadata_map, f, ensure_ascii=False, indent=2)

        yield yield_and_log(
            msg_type="progress",
            stage="FETCHING_ASSETS",
            percent=12,
            message=(
                f"Metadonnées sauvées pour {photos_with_metadata} "
                f"photos sur {total_assets}"
            ),
        )

    except Exception as e:
        yield yield_and_log(
            msg_type="warning",
            message=f"Erreur sauvegarde Metadonnées : {e}",
        )
    # Fin Modification Sigalou 26/01/2026

    asset_ids = [asset["id"] for asset in assets]
    if not asset_ids:
        yield yield_and_log(
            msg_type="error",
            message="Aucune photo accessible.",
        )
        return

    nb_photos = len(asset_ids)
    yield yield_and_log(
        msg_type="progress",
        stage="DOWNLOADING",
        percent=16,
        message=f"Téléchargement de l'archive ({nb_photos} photos)...",
    )

    zip_path = "temp_album.zip"

    try:
        success, error_msg = download_album_archive_local(server_url, api_key, asset_ids, zip_path)
        if not success:
            yield yield_and_log(
                msg_type="error",
                message=f"Échec du téléchargement de l'archive : {error_msg}",
            )
            return

    except Exception as e:
        yield yield_and_log(
            msg_type="error",
            message=f"Erreur critique lors du téléchargement : {str(e)}",
        )
        return

    # yield {"type": "progress", "stage": "EXTRACTING", "percent": 20, "message": "Extraction des photos..."}

    photos_folder = os.path.join("static", "photos", "immich")
    prepared_folder = os.path.join("static", "prepared", "immich")

    # Vider les dossiers de destination avant l'import
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
        yield yield_and_log(
            msg_type="error",
            message=f"Erreur lors de l'extraction : {str(e)}",
        )
        return

    yield yield_and_log(
        msg_type="done",
        stage="DOWNLOAD_COMPLETE",
        percent=24,
        message=f"{nb_photos} photos prêtes pour préparation.",
        extra={"total_downloaded": nb_photos},
    )
