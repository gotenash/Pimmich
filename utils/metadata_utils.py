import json
from pathlib import Path
import re
import logging
import os

# Définition des chemins
BASE_DIR = Path(__file__).resolve().parent.parent
_photo_metadata_cache = None
_photo_metadata_last_load = None
DESCRIPTION_MAP_CACHE_FILE = BASE_DIR / 'cache' / 'immich_description_map.json'

logger = logging.getLogger(__name__)

def load_photo_metadata_cache():
    """
    Charge le cache des métadonnées photos depuis le fichier JSON créé lors du téléchargement.
    Ce fichier contient les informations EXIF de chaque photo (date, ville, pays, coordonnées GPS).
    """
    global _photo_metadata_cache, _photo_metadata_last_load

    if not DESCRIPTION_MAP_CACHE_FILE.exists():
        return {}

    try:
        file_mtime = DESCRIPTION_MAP_CACHE_FILE.stat().st_mtime

        if _photo_metadata_last_load is None or file_mtime > _photo_metadata_last_load:
            with open(DESCRIPTION_MAP_CACHE_FILE, 'r', encoding='utf-8') as f:
                _photo_metadata_cache = json.load(f)
            _photo_metadata_last_load = file_mtime

        return _photo_metadata_cache

    except Exception as e:
        logger.error(f"[Metadata] Erreur chargement cache : {e}")
        return {}

def get_photo_metadata(photo_path):
    """
    Récupère les métadonnées d'une photo depuis le cache.
    Retourne un dictionnaire avec : date_taken, city, country, location, latitude, longitude
    """
    try:
        metadata_map = load_photo_metadata_cache()
        if not metadata_map:
            return {}
        filename = Path(photo_path).name
        filename_lower = filename.lower()
        for cached_filename, metadata in metadata_map.items():
            if cached_filename.lower() == filename_lower:
                return metadata
        base_filename = re.sub(r'(_polaroid|_postcard)\.(jpg|jpeg|png|JPG|JPEG|PNG)$', r'.\2', filename, flags=re.IGNORECASE)
        base_filename_lower = base_filename.lower()
        for cached_filename, metadata in metadata_map.items():
            if cached_filename.lower() == base_filename_lower:
                return metadata
        return {}
    except Exception as e:
        logger.error(f"[Metadata] Erreur extraction métadonnées pour {photo_path}: {e}")
        return {}