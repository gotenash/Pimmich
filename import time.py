import time
from datetime import datetime, timedelta
import threading
import os
import json
from utils.config import load_config
from utils.download_album import download_and_extract_album
from utils.prepare_all_photos import prepare_all_photos_with_progress

# Chemin vers un fichier pour stocker les horodatages des dernières mises à jour
LAST_UPDATE_FILE = os.path.join("config", "last_updates.json")

def read_last_updates():
    """Lit les horodatages des dernières mises à jour depuis un fichier JSON."""
    if not os.path.exists(LAST_UPDATE_FILE):
        return {}
    try:
        with open(LAST_UPDATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def write_last_update(source_name):
    """Écrit l'horodatage actuel pour une source donnée."""
    updates = read_last_updates()
    updates[source_name] = datetime.now().isoformat()
    try:
        with open(LAST_UPDATE_FILE, "w") as f:
            json.dump(updates, f, indent=2)
    except IOError as e:
        print(f"[Updater] Erreur lors de l'écriture de l'heure de mise à jour : {e}")

def immich_update_task():
    """Vérifie si une mise à jour Immich est nécessaire et la lance."""
    print("[Updater] Vérification des mises à jour Immich...")
    config = load_config()

    if not config.get("immich_auto_update", False):
        return

    interval_hours = int(config.get("immich_update_interval_hours", 24))
    last_updates = read_last_updates()
    last_update_str = last_updates.get("immich")
    
    if last_update_str:
        last_update_time = datetime.fromisoformat(last_update_str)
        if datetime.now() < last_update_time + timedelta(hours=interval_hours):
            return

    print("[Updater] Mise à jour pour Immich nécessaire. Lancement...")
    try:
        download_generator = download_and_extract_album(config)
        download_complete = False
        for update in download_generator:
            print(f"[Updater] Immich Download: {update.get('message')}")
            if update.get('type') == 'error':
                print(f"[Updater] Erreur pendant le téléchargement Immich : {update.get('message')}")
                return
            if update.get('stage') == 'DOWNLOAD_COMPLETE':
                download_complete = True

        if not download_complete:
            return

        print("[Updater] Lancement de la préparation des photos pour Immich...")
        prepare_generator = prepare_all_photos_with_progress(source_type="immich")
        for update in prepare_generator:
            print(f"[Updater] Préparation Photo: {update.get('message')}")
            if update.get('type') == 'error':
                print(f"[Updater] Erreur pendant la préparation des photos : {update.get('message')}")
                return

        print("[Updater] Mise à jour et préparation Immich terminées.")
        write_last_update("immich")

    except Exception as e:
        print(f"[Updater] Erreur inattendue pendant la mise à jour Immich : {e}")

def smb_update_task():
    """Placeholder pour la logique de mise à jour SMB."""
    config = load_config()
    if config.get("smb_auto_update", False):
        print("[Updater] La logique de mise à jour auto pour SMB n'est pas encore implémentée.")

def background_updater_loop():
    """Boucle principale pour le thread de mise à jour."""
    check_interval_seconds = 3600  # Vérifier toutes les heures

    while True:
        print("\n[Updater] Lancement des vérifications périodiques...")
        
        immich_update_task()
        smb_update_task()
        
        print(f"[Updater] Vérifications terminées. Prochaine vérification dans {check_interval_seconds / 3600} heure(s).")
        time.sleep(check_interval_seconds)

def start_background_updater():
    """Démarre le processus de mise à jour en arrière-plan dans un thread séparé."""
    updater_thread = threading.Thread(target=background_updater_loop, daemon=True)
    updater_thread.start()
    print("Le thread de mise à jour en arrière-plan a démarré.")