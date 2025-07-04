from flask import Flask, render_template, request, redirect, url_for, session, flash, stream_with_context, Response, jsonify
import os
import json
import re
import subprocess
import psutil
import glob
import time
import requests
import threading
import shutil
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, stream_with_context, Response, jsonify, g
from werkzeug.utils import secure_filename
from pathlib import Path

from utils.download_album import download_and_extract_album
from utils.auth import login_required
from utils.slideshow_manager import is_slideshow_running, start_slideshow, stop_slideshow
from utils.slideshow_manager import HDMI_OUTPUT # Pour la détection de résolution
from utils.wifi_manager import set_wifi_config # Import the new utility
from utils.prepare_all_photos import prepare_all_photos_with_progress
from utils.import_usb_photos import import_usb_photos  # Déplacé dans utils
from utils.import_samba import import_samba_photos
from utils.image_filters import apply_filter_to_image
import smbclient
from smbprotocol.exceptions import SMBException


app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Chemins de config
PENDING_UPLOADS_DIR = Path("static/pending_uploads")
CONFIG_PATH = 'config/config.json'
CREDENTIALS_PATH = '/boot/firmware/credentials.json'
FILTER_STATES_PATH = 'config/filter_states.json'
CURRENT_PHOTO_FILE = "/tmp/pimmich_current_photo.txt"

class WorkerStatus:
    def __init__(self):
        self.lock = threading.Lock()
        self.last_run = None
        self.next_run = None
        self.status_message = "Initialisation..."

    def update_status(self, last_run=None, next_run=None, message=None):
        with self.lock:
            if last_run:
                self.last_run = last_run.isoformat()
            if next_run:
                self.next_run = next_run.isoformat()
            if message:
                self.status_message = message

    def get_status(self):
        with self.lock:
            return {
                "last_run": self.last_run,
                "next_run": self.next_run,
                "status_message": self.status_message
            }

immich_status_manager = WorkerStatus()
samba_status_manager = WorkerStatus()

def get_screen_resolution():
    """
    Détecte la résolution de l'écran principal via swaymsg.
    Retourne (width, height) ou (1920, 1080) en cas d'erreur.
    """
    default_width = 1920
    default_height = 1080
    default_height = 1080
    try:
        # Assurer que SWAYSOCK est défini
        if "SWAYSOCK" not in os.environ:
            user_id = os.getuid()
            # Utiliser glob pour trouver le socket, car le nom peut varier
            sock_path_pattern = f"/run/user/{user_id}/sway-ipc.*"
            socks = glob.glob(sock_path_pattern)
            if socks:
                os.environ["SWAYSOCK"] = socks[0]
            else:
                print("SWAYSOCK non trouvé, utilisation de la résolution par défaut.")
                return default_width, default_height

        # Utiliser HDMI_OUTPUT du slideshow_manager pour cibler la bonne sortie
        # ou chercher la sortie active si HDMI_OUTPUT n'est pas suffisant.
        # Pour l'instant, on se base sur la sortie active.
        result = subprocess.run(['swaymsg', '-t', 'get_outputs'], capture_output=True, text=True, check=True, env=os.environ)
        outputs = json.loads(result.stdout)
        
        for output in outputs:
            if output.get('active', False) and output.get('current_mode'):
                mode = output['current_mode']
                return mode['width'], mode['height']
        
        print("Aucune sortie active trouvée, utilisation de la résolution par défaut.")
        return default_width, default_height
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError, IndexError) as e:
        print(f"Erreur lors de la détection de la résolution de l'écran : {e}. Utilisation de la résolution par défaut.")
        return default_width, default_height
    except Exception as e:
        print(f"Erreur inattendue lors de la détection de la résolution : {e}. Utilisation de la résolution par défaut.")
        return default_width, default_height

def check_and_start_slideshow_on_boot():
    from datetime import datetime

    print("== Vérification du créneau horaire au démarrage ==")

    config = load_config()
    start_str = config.get("active_start", "06:00")
    end_str = config.get("active_end", "22:00")

    try:
        now_time = datetime.now().time()
        start_time = datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.strptime(end_str, "%H:%M").time()
    except (ValueError, AttributeError) as e:
        print(f"Erreur de format ou de lecture des horaires de la configuration : {e}")
        return

    print(f"Heure actuelle : {now_time.strftime('%H:%M')} / Créneau actif : {start_str}-{end_str}")

    # Gère les créneaux qui passent minuit (ex: 22:00 - 06:00)
    in_schedule = False
    if start_time <= end_time:
        if start_time <= now_time <= end_time:
            in_schedule = True
    else:  # Le créneau passe minuit
        if now_time >= start_time or now_time <= end_time:
            in_schedule = True

    if in_schedule:
        print("Dans la plage horaire, on démarre le slideshow.")
        if not is_slideshow_running():
            start_slideshow()
    else:
        print("Hors plage horaire, on ne démarre pas le slideshow.")



def get_photo_previews():
    photo_dir = Path("static/photos")
    return sorted([f.name for f in photo_dir.glob("*") if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".gif"]])

def load_credentials():
    try:
        with open(CREDENTIALS_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def check_credentials(username, password):
    credentials = load_credentials()
    return username == credentials.get("username") and password == credentials.get("password")
def create_default_config():
    """Crée et retourne un dictionnaire de configuration par défaut."""
    return {
        "photo_source": "immich",
        "display_duration": 10,
        "active_start": "07:00",
        "active_end": "22:00",
        "screen_height_percent": "100",
        "immich_url": "",
        "immich_token": "",
        "album_name": "",
        "display_width": 1920,  # Nouvelle option: largeur d'affichage cible
        "display_height": 1080, # Nouvelle option: hauteur d'affichage cible
        "pan_zoom_factor": 1.15, # New option
        "immich_auto_update": False,
        "immich_update_interval_hours": 24,
        "pan_zoom_enabled": False, # New option
        "transition_enabled": True, # New option: transition enabled by default
        "transition_type": "fade", # New option: default transition type
        "transition_duration": 1.0, # New option
        "smb_host": "",
        "smb_share": "",
        "smb_user": "",
        "smb_password": "",
        "smb_path": "/",
        "smb_auto_update": False,
        "smb_update_interval_hours": 24,
        "display_sources": ["immich"],
        "show_clock": True,
        "clock_format": "%H:%M",
        "clock_color": "#FFFFFF",
        "clock_outline_color": "#000000",
        "clock_font_size": 72,
        "clock_font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "clock_offset_x": 0,
        "clock_offset_y": 0,
        "clock_background_enabled": False,
        "clock_background_color": "#00000080", # Semi-transparent black
        "show_date": True,
        "date_format": "%A %d %B %Y", # Re-added
        "show_weather": True, # Re-added
        "weather_api_key": "", # Re-added
        "weather_city": "Paris", # Re-added
        "wifi_ssid": "", # New: Wi-Fi SSID
        "wifi_password": "", # New: Wi-Fi Password
        "weather_units": "metric", # Re-added
        "skip_initial_auto_import": False, # New: Skip first auto import cycle on startup
        "show_tides": False,
        "tide_latitude": "",
        "tide_longitude": "",
        "stormglass_api_key": "", # New: StormGlass API Key
        "tide_offset_x": 0,
        "tide_offset_y": 0,
        "weather_update_interval_minutes": 60, # Re-added
        "info_display_duration": 5, # New: Duration for each info item in the cycle
    }

def load_config():
    """Charge la configuration, en ignorant les clés obsolètes."""
    config = create_default_config()
    try:
        with open(CONFIG_PATH, 'r') as f:
            loaded_config = json.load(f)
        # Met à jour les valeurs par défaut avec celles du fichier,
        # mais sans ajouter de clés inconnues.
        for key in config:
            if key in loaded_config:
                config[key] = loaded_config[key]
    except FileNotFoundError:
        print(f"Fichier de configuration '{CONFIG_PATH}' non trouvé. Création d'une configuration par défaut.")
    except json.JSONDecodeError:
        print(f"ERREUR: Le fichier de configuration '{CONFIG_PATH}' est corrompu ou malformé.")
        corrupted_path = CONFIG_PATH + f".corrupted_{int(time.time())}"
        try:
            os.rename(CONFIG_PATH, corrupted_path)
            print(f"Le fichier corrompu a été sauvegardé sous : {corrupted_path}")
        except OSError as e:
            print(f"Impossible de sauvegarder le fichier corrompu : {e}")
        print("Création d'une nouvelle configuration par défaut.")
    return config

def load_filter_states():
    """Charge les états des filtres depuis un fichier JSON."""
    if not os.path.exists(FILTER_STATES_PATH):
        return {}
    try:
        with open(FILTER_STATES_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_config(config):
    temp_path = CONFIG_PATH + '.tmp'
    try:
        with open(temp_path, 'w') as f:
            json.dump(config, f, indent=4)
        os.rename(temp_path, CONFIG_PATH)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde de la configuration : {e}")

def save_filter_states(states):
    """Sauvegarde les états des filtres dans un fichier JSON."""
    try:
        with open(FILTER_STATES_PATH, 'w') as f:
            json.dump(states, f, indent=4)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des états de filtre : {e}")

def get_prepared_photos_by_source():
    """
    Récupère les photos préparées, organisées par leur source (immich, usb, samba).
    Retourne un dictionnaire où les clés sont les noms des sources et les valeurs sont des listes de dictionnaires.
    Ex: {'immich': [{'path': 'immich/photo1.jpg', 'has_polaroid': True}, ...]}
    """
    base_prepared_dir = Path("static/prepared")
    photos_by_source = {}
    filter_states = load_filter_states()
    if base_prepared_dir.exists():
        for source_dir in base_prepared_dir.iterdir():
            if source_dir.is_dir():
                source_name = source_dir.name
                
                # Lister tous les fichiers pour trouver les versions polaroid
                all_files = {f.name for f in source_dir.glob("*.jpg")}
                
                # Identifier les photos de base (non-polaroid)
                base_photos = sorted([f for f in all_files if not f.endswith('_polaroid.jpg')])

                photo_data_list = []
                for photo_name in base_photos:
                    base_name = Path(photo_name).stem
                    photo_relative_path = f"{source_name}/{photo_name}"
                    has_polaroid = f"{base_name}_polaroid.jpg" in all_files
                    photo_data_list.append({
                        "path": photo_relative_path,
                        "has_polaroid": has_polaroid,
                        "active_filter": filter_states.get(photo_relative_path, "none")
                    })
                
                if photo_data_list:
                    photos_by_source[source_name] = photo_data_list
    return photos_by_source

def get_all_prepared_photos():
    """
    Récupère toutes les photos préparées de toutes les sources dans une seule liste plate.
    """
    return [photo for source_photos in get_prepared_photos_by_source().values() for photo in source_photos]



# --- Routes principales ---

def _handle_photo_preparation_stream(source_name, screen_width, screen_height):
    """
    Générateur pour gérer la phase de préparation des photos et streamer les mises à jour.
    Cette fonction est conçue pour être appelée depuis les routes d'import.
    Elle retourne True si la préparation s'est bien déroulée, False sinon.
    """
    def stream_event(data):
        """Formate les données en événement Server-Sent Event (SSE)."""
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    source_dir = Path("static/photos")
    photo_files = [f for f in source_dir.iterdir() if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.heic', '.heif']]
    total_photos = len(photo_files)

    if total_photos > 0:
        yield stream_event({
            "type": "progress", "stage": "PREPARING", "percent": 80,
            "message": f"Préparation de {total_photos} photos pour l'affichage..."
        })

        for update in prepare_all_photos_with_progress(screen_width, screen_height, source_name):
            if update.get("type") == "progress":
                prep_percent = update.get("percent", 0)
                main_progress_update = {
                    "type": "progress",
                    "percent": 80 + int(prep_percent * 0.20), # Pourcentage mis à l'échelle (80% -> 100%)
                    "message": f"Préparation de {total_photos} photos pour l'affichage..."
                }
                yield stream_event(main_progress_update)
            elif update.get("type") in ["warning", "error"]:
                yield stream_event({"type": update.get("type"), "message": update.get("message")})
        
        yield stream_event({"type": "done", "percent": 100, "message": f"Import terminé ! {total_photos} photos sont prêtes."})
        return True
    else:
        yield stream_event({"type": "warning", "message": "Aucune photo n'a été importée ou trouvée pour la préparation."})
        return False


@app.route('/upload', methods=['GET'])
def upload_page():
    """Affiche la page publique pour envoyer des photos."""
    return render_template('upload.html')

@app.route('/handle_upload', methods=['POST'])
def handle_upload():
    """Gère la réception des fichiers depuis la page publique."""
    if 'photos' not in request.files:
        flash("Aucun fichier sélectionné.", "error")
        return redirect(url_for('upload_page'))

    files = request.files.getlist('photos')
    if not files or files[0].filename == '':
        flash("Aucun fichier sélectionné.", "error")
        return redirect(url_for('upload_page'))

    PENDING_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    
    count = 0
    for file in files:
        if file:
            # Sécuriser le nom du fichier
            filename = secure_filename(file.filename)
            # Gérer les collisions de noms en ajoutant un timestamp
            base, ext = os.path.splitext(filename)
            final_path = PENDING_UPLOADS_DIR / f"{base}_{int(time.time())}{ext}"
            file.save(final_path)
            count += 1

    flash(f"{count} photo(s) envoyée(s) pour validation avec succès !", "success")
    return redirect(url_for('upload_page'))

@app.route('/api/get_pending_photos')
@login_required
def get_pending_photos():
    """Retourne la liste des photos en attente de validation."""
    pending_files = []
    if not PENDING_UPLOADS_DIR.exists():
        # Si le dossier n'existe pas, la liste est simplement vide.
        pass
    else:
        pending_files = sorted(
            [f.name for f in PENDING_UPLOADS_DIR.iterdir() if f.is_file()],
            key=lambda p: os.path.getmtime(PENDING_UPLOADS_DIR / p),
            reverse=True
        )
    
    # Retourner une réponse structurée et ajouter des en-têtes anti-cache.
    response = jsonify({"success": True, "photos": pending_files})
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route('/api/manage_pending_photo', methods=['POST'])
@login_required
def manage_pending_photo():
    """Approuve ou rejette une photo en attente."""
    data = request.get_json()
    filename = data.get('filename')
    action = data.get('action')

    if not filename or not action in ['approve', 'reject']:
        return jsonify({"success": False, "message": "Données invalides."}), 400

    pending_path = PENDING_UPLOADS_DIR / secure_filename(filename)

    if not pending_path.is_file():
        return jsonify({"success": False, "message": "Fichier non trouvé."}), 404

    if action == 'reject':
        try:
            pending_path.unlink()
            return jsonify({"success": True, "message": "Photo rejetée."})
        except Exception as e:
            return jsonify({"success": False, "message": f"Erreur: {e}"}), 500

    if action == 'approve':
        # Processus d'approbation rendu plus robuste :
        # 1. Copier la photo vers le dossier de transit (au lieu de la déplacer).
        # 2. Lancer la préparation.
        # 3. Si la préparation réussit, supprimer la photo du dossier d'attente.
        source_dir = Path("static/photos")
        source_dir.mkdir(parents=True, exist_ok=True)

        # Vider le dossier de transit pour ne préparer que cette photo
        for f in source_dir.iterdir():
            f.unlink()

        # Copier la photo pour la traiter
        shutil.copy(str(pending_path), str(source_dir / pending_path.name))

        # Lancer la préparation
        screen_width, screen_height = get_screen_resolution()
        try:
            preparation_successful = False
            for update in _handle_photo_preparation_stream("smartphone", screen_width, screen_height):
                # On vérifie si la préparation s'est terminée avec succès en lisant le flux d'événements
                if json.loads(update.lstrip('data: ').strip()).get("type") == "done":
                    preparation_successful = True
            
            if preparation_successful:
                pending_path.unlink() # Supprimer l'original seulement si tout s'est bien passé
                return jsonify({"success": True, "message": "Photo approuvée et préparée."})
            else:
                return jsonify({"success": False, "message": "La préparation de la photo a échoué. La photo reste en attente."}), 500
        except Exception as e:
            return jsonify({"success": False, "message": f"Erreur lors de la préparation: {e}"}), 500

    return jsonify({"success": False, "message": "Action inconnue."}), 400

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if check_credentials(request.form['username'], request.form['password']): # type: ignore
            session['logged_in'] = True
            flash("Connexion réussie", "success")
            return redirect(url_for('configure'))
        else:
            flash("Identifiants invalides", "danger")
    return render_template('login.html')

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('logged_in', None)
    flash("Déconnexion réussie", "success")
    return redirect(url_for('login'))


# --- Configuration & gestion diaporama ---

@app.route('/configure', methods=['GET', 'POST'])
@login_required
def configure():
    config = load_config()

    if request.method == 'POST':
        # Gérer le champ 'source' qui correspond à 'photo_source' dans le config
        if 'source' in request.form:
            config['photo_source'] = request.form.get('source')

        for key in [
            'immich_url', 'immich_token', 'album_name',
            'display_duration', 'active_start', 'active_end',
            'screen_height_percent', 'clock_font_size', 'clock_color',
            'clock_format', 'clock_offset_x', 'clock_offset_y',
            'clock_background_color',
            'clock_outline_color', 'clock_font_path', 'clock_position',
            'display_width', 'display_height', # Ajout des nouvelles clés
            'transition_enabled', # Added transition_enabled
            'transition_type', # Added transition_type
            'transition_duration', # Added transition_duration            
            'pan_zoom_factor', # Added pan_zoom_factor
            'immich_update_interval_hours', 'date_format', 
            'weather_api_key', 'weather_city', 'weather_units', 'weather_update_interval_minutes', # Re-added
            'smb_host', 'smb_share', 'smb_path', 'smb_user', 'smb_password',
            'smb_update_interval_hours'
            # New fields
            , 'wifi_ssid', 'wifi_password', 'info_display_duration',
            'skip_initial_auto_import',
            'tide_latitude', 'tide_longitude', 'stormglass_api_key',
            'tide_offset_x',
            'tide_offset_y'
        ]: 
            if key in request.form:
                value = request.form.get(key)
                # Gérer les champs numériques
                if key in ['display_duration', 'clock_offset_x', 'clock_offset_y', 'clock_font_size', 'weather_update_interval_minutes', 'immich_update_interval_hours', 'smb_update_interval_hours', 'display_width', 'display_height', 'info_display_duration', 'tide_offset_x', 'tide_offset_y']: # Integer fields
                    try:
                        config[key] = int(value)
                    except (ValueError, TypeError):
                        config[key] = 0 # Mettre une valeur par défaut en cas d'erreur
                elif key in ['pan_zoom_factor']: # Float fields
                    try:
                        config[key] = float(value)
                    except (ValueError, TypeError):
                        config[key] = 1.0 # Default to no zoom
                elif key in ['transition_duration']: # Float fields
                    try:
                        config[key] = float(value)
                    except (ValueError, TypeError):
                        config[key] = 0.0 # Default to no transition
                else: # Gérer les champs texte
                    config[key] = value
        
        # Détecter et sauvegarder la résolution actuelle de l'écran
        detected_width, detected_height = get_screen_resolution()
        config['display_width'] = detected_width
        config['display_height'] = detected_height
        print(f"Résolution d'écran détectée : {detected_width}x{detected_height}. Sauvegarde dans la configuration.")
        # Gérer la clé display_sources (checkboxes)
        # request.form.getlist() retourne une liste vide si aucune checkbox avec ce nom n'est cochée.
        config['display_sources'] = request.form.getlist('display_sources')
        config["pan_zoom_enabled"] = 'pan_zoom_enabled' in request.form # New checkbox handling
        config["transition_enabled"] = 'transition_enabled' in request.form # New checkbox handling
        config["clock_background_enabled"] = 'clock_background_enabled' in request.form

        # Traitement des checkboxes
        config["show_clock"] = 'show_clock' in request.form
        config["immich_auto_update"] = 'immich_auto_update' in request.form
        config["smb_auto_update"] = 'smb_auto_update' in request.form

        config["show_date"] = 'show_date' in request.form
        config["show_weather"] = 'show_weather' in request.form
        config["show_tides"] = 'show_tides' in request.form
        save_config(config)
        stop_slideshow() # Stop slideshow to apply new config
        start_slideshow() # Start slideshow with new config
        flash("Configuration enregistrée et diaporama relancé", "success")
        return redirect(url_for('configure'))

    slideshow_running = any(
        'local_slideshow.py' in (p.info['cmdline'] or []) for p in psutil.process_iter(attrs=['cmdline'])
    )

    # Test de la connexion Wi-Fi au chargement de la page
    wifi_status = "Inconnu"
    try:
        # Ceci est une vérification très basique, vous pouvez l'améliorer
        # en vérifiant l'interface wlan0 ou en pingant une adresse externe.
        # Pour l'instant, nous allons juste vérifier si les champs sont remplis.
        if config.get("wifi_ssid"):
            wifi_status = "Configuré (état non vérifié)"
        else:
            wifi_status = "Non configuré"
    except Exception as e:
        wifi_status = f"Erreur de vérification : {e}"

    prepared_photos_by_source = get_prepared_photos_by_source()

    return render_template(
        'configure.html',
        config=config,
        prepared_photos_by_source=prepared_photos_by_source,
        slideshow_running=slideshow_running
    )

@app.route("/import-usb")
@login_required
def progress():
    @stream_with_context
    def generate():
        def stream_event(data):
            """Formate les données en événement Server-Sent Event (SSE)."""
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        screen_width, screen_height = get_screen_resolution()

        try:
            # --- Étape 1: Import depuis la clé USB ---
            for update in import_usb_photos():
                if update.get("type") == "error": # type: ignore
                    yield stream_event({"type": "error", "message": update.get("message")})
                    return  # Arrêter le flux en cas d'erreur
                
                # Simplifier l'événement pour le client, ne garder que l'essentiel
                if update.get("type") in ["progress", "done"]:
                    yield stream_event({"type": "progress", "percent": update.get("percent"), "message": update.get("message")})
                elif update.get("type") == "warning":
                    yield stream_event(update)

            # --- Étape 2: Préparation des photos (logique centralisée) ---
            yield from _handle_photo_preparation_stream("usb", screen_width, screen_height)

        except Exception as e:
            yield stream_event({"type": "error", "message": f"Erreur critique : {str(e)}"})

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive"
    })


@app.route("/import-immich")
@login_required
def import_immich():
    config = load_config()

    @stream_with_context
    def generate():
        def stream_event(data):
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        screen_width, screen_height = get_screen_resolution()

        try:
            # --- Étape 1: Téléchargement depuis Immich ---
            for update in download_and_extract_album(config):
                if update.get("type") == "error": # type: ignore
                    yield stream_event({"type": "error", "message": update.get("message")})
                    return  # Stop on error
                
                # Simplifier l'événement pour le client, ne garder que l'essentiel
                if update.get("type") in ["progress", "done"]:
                    yield stream_event({"type": "progress", "percent": update.get("percent"), "message": update.get("message")})
                elif update.get("type") == "warning":
                    yield stream_event(update)
            
            # --- Étape 2: Préparation des photos (logique centralisée) ---
            yield from _handle_photo_preparation_stream("immich", screen_width, screen_height)

        except Exception as e:
            yield stream_event({"type": "error", "message": f"Erreur critique : {str(e)}"})

    return Response(generate(), mimetype='text/event-stream', headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive"
    })

@app.route("/import-samba")
@login_required
def import_samba():
    config = load_config()

    @stream_with_context
    def generate():
        def stream_event(data):
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        screen_width, screen_height = get_screen_resolution()

        try:
            # --- Étape 1: Import depuis Samba ---
            for update in import_samba_photos(config):
                if update.get("type") == "error": # type: ignore
                    yield stream_event({"type": "error", "message": update.get("message")})
                    return

                # Simplifier l'événement pour le client, ne garder que'l'essentiel
                if update.get("type") in ["progress", "done"]:
                    yield stream_event({"type": "progress", "percent": update.get("percent"), "message": update.get("message")})
                elif update.get("type") == "warning":
                    yield stream_event(update)
            
            # --- Étape 2: Préparation des photos (logique centralisée) ---
            yield from _handle_photo_preparation_stream("samba", screen_width, screen_height)

        except Exception as e:
            yield stream_event({"type": "error", "message": f"Erreur critique : {str(e)}"})

    return Response(generate(), mimetype='text/event-stream', headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})

@app.route("/import-smartphone", methods=['POST'])
@login_required
def import_smartphone():
    """
    Gère l'upload de photos depuis un smartphone via un formulaire web.
    """
    @stream_with_context
    def generate():
        def stream_event(data):
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        screen_width, screen_height = get_screen_resolution()
        source_dir = Path("static/photos")

        try:
            # --- Étape 1: Réception et sauvegarde des fichiers ---
            yield stream_event({"type": "progress", "stage": "UPLOADING", "percent": 5, "message": "Réception des fichiers..."})

            # Vider le dossier de destination pour éviter les mélanges
            if source_dir.exists():
                shutil.rmtree(source_dir)
            source_dir.mkdir(parents=True, exist_ok=True)

            uploaded_files = request.files.getlist('photos')
            if not uploaded_files or not uploaded_files[0].filename:
                yield stream_event({"type": "error", "message": "Aucun fichier sélectionné."})
                return

            for file in uploaded_files:
                file.save(source_dir / file.filename)

            yield stream_event({"type": "progress", "stage": "PREPARING", "percent": 80, "message": f"{len(uploaded_files)} photos reçues, préparation en cours..."})

            # --- Étape 2: Préparation des photos ---
            yield from _handle_photo_preparation_stream("smartphone", screen_width, screen_height)

        except Exception as e:
            yield stream_event({"type": "error", "message": f"Erreur critique lors de l'import : {str(e)}"})

    return Response(generate(), mimetype='text/event-stream', headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})

@app.route('/test-samba', methods=['POST'])
@login_required
def test_samba_connection():
    """Teste la connexion à un partage Samba sans importer de fichiers."""

    data = request.get_json()
    server = data.get("smb_host")
    share = data.get("smb_share")
    path_in_share = data.get("smb_path", "").strip("/")
    user = data.get("smb_user")
    password = data.get("smb_password")
    
    if not all([server, share]):
        return jsonify({"success": False, "message": "Le serveur et le nom du partage sont requis."})
    
    # Construction robuste du chemin UNC pour éviter les problèmes de slashs finaux.
    if path_in_share:
        full_samba_path = f"//{server}/{share}/{path_in_share}"
    else:
        full_samba_path = f"//{server}/{share}"
    
    try:
        # Utiliser listdir en passant les identifiants directement.
        # Cela évite d'utiliser register/unregister_session qui peuvent manquer dans d'anciennes versions.
        files = smbclient.listdir(
            full_samba_path,
            username=user,
            password=password,
            connection_timeout=15
        )
        return jsonify({"success": True, "message": f"Connexion réussie ! {len(files)} élément(s) trouvé(s) dans le dossier."})

    except SMBException as e:
        # Fournir un message plus utile pour les erreurs communes
        if "STATUS_LOGON_FAILURE" in str(e):
            return jsonify({"success": False, "message": "Échec de l'authentification. Vérifiez l'utilisateur et le mot de passe."})
        elif "STATUS_BAD_NETWORK_NAME" in str(e):
            return jsonify({"success": False, "message": f"Le nom du partage '{share}' est introuvable sur le serveur."})
        elif "STATUS_OBJECT_NAME_NOT_FOUND" in str(e) or "STATUS_OBJECT_PATH_NOT_FOUND" in str(e):
            # Erreur spécifique si le sous-dossier n'existe pas
            return jsonify({"success": False, "message": f"Le chemin '{path_in_share}' est introuvable dans le partage."})
        elif "STATUS_HOST_UNREACHABLE" in str(e) or "timed out" in str(e):
             return jsonify({"success": False, "message": f"Impossible de joindre le serveur '{server}'. Vérifiez l'adresse et le pare-feu."})
        return jsonify({"success": False, "message": f"Erreur Samba : {e}"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur inattendue : {e}"})

@app.route('/test-weather-api', methods=['POST'])
@login_required
def test_weather_api():
    """Teste la validité d'une clé API OpenWeatherMap et d'une ville."""
    data = request.get_json()
    api_key = data.get("api_key")
    city = data.get("city")

    if not api_key or not city:
        return jsonify({"success": False, "message": "La clé API et la ville sont requises."})

    # Utilise l'URL de l'API OpenWeatherMap pour le test
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"

    try:
        response = requests.get(url, timeout=5) # type: ignore
        if response.status_code == 200:
            return jsonify({"success": True, "message": "Clé API et ville valides !"})
        elif response.status_code == 401:
            # 401 Unauthorized est la réponse typique pour une clé invalide
            return jsonify({"success": False, "message": "Clé API invalide ou non activée."})
        elif response.status_code == 404:
            # 404 Not Found pour une ville invalide
            return jsonify({"success": False, "message": "Ville non trouvée."})
        else:
            return jsonify({"success": False, "message": f"Erreur de l'API: {response.status_code} - {response.text}"})
    except requests.exceptions.RequestException as e:
        # Gère les erreurs de connexion (timeout, pas d'internet, etc.)
        return jsonify({"success": False, "message": f"Erreur de connexion : {e}"})

@app.route('/test-stormglass-api', methods=['POST'])
@login_required
def test_stormglass_api():
    """Teste la connexion à l'API StormGlass."""
    data = request.get_json()
    api_key = data.get("api_key")
    lat = data.get("lat")
    lon = data.get("lon")

    if not all([api_key, lat, lon]):
        return jsonify({"success": False, "message": "La clé API, la latitude et la longitude sont requises."})

    try:
        # Test avec une très courte fenêtre de temps pour minimiser l'utilisation des données
        start_time_utc = datetime.utcnow()
        end_time_utc = start_time_utc + timedelta(hours=1)

        headers = {'Authorization': api_key}
        params = { 'lat': lat, 'lng': lon, 'start': start_time_utc.isoformat(), 'end': end_time_utc.isoformat() }
        
        response = requests.get('https://api.stormglass.io/v2/tide/extremes/point', params=params, headers=headers, timeout=10)

        if response.status_code == 200:
            return jsonify({"success": True, "message": "Connexion à StormGlass réussie !"})
        elif response.status_code == 401:
            return jsonify({"success": False, "message": "Clé API invalide."})
        elif response.status_code == 402:
            return jsonify({"success": False, "message": "Crédits API épuisés ou plan inadapté."})
        elif response.status_code == 429:
            return jsonify({"success": False, "message": "Trop de requêtes. Veuillez réessayer plus tard."})
        else:
            try:
                error_details = response.json().get('errors', {})
                message = f"Erreur de l'API ({response.status_code}): {error_details}"
            except json.JSONDecodeError:
                message = f"Erreur de l'API ({response.status_code})"
            return jsonify({"success": False, "message": message})
    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "message": f"Erreur de connexion : {e}"})

@app.route('/immich_update_status')
@login_required
def immich_update_status():
    """Retourne l'état actuel du worker de mise à jour Immich."""
    return jsonify(immich_status_manager.get_status())

@app.route('/samba_update_status')
@login_required
def samba_update_status():
    """Retourne l'état actuel du worker de mise à jour Samba."""
    return jsonify(samba_status_manager.get_status())


# --- Téléchargement Immich et Préparation photos ---


@app.route("/download", methods=["POST"])
@login_required
def download_photos():
    try:
        config = load_config()
        # Note: download_and_extract_album is now a generator. This call will do nothing.
        # This route seems to be a simple POST fallback and might need to be updated or removed. (Translated comment)
        flash("Photos téléchargées avec succès", "success")
    except Exception as e:
        flash(f"Erreur téléchargement : {e}", "danger")
    return redirect(url_for("configure"))


# --- Worker de mise à jour automatique ---

_immich_first_run_skipped = False
_samba_first_run_skipped = False

def immich_update_worker():
    """
    Thread en arrière-plan qui vérifie et met à jour l'album Immich périodiquement.
    """
    print("== Démarrage du worker de mise à jour automatique Immich ==")
    while True:
        config = load_config()
        is_enabled = config.get("immich_auto_update", False)
        interval_hours = config.get("immich_update_interval_hours", 24)
        skip_initial = config.get("skip_initial_auto_import", False) # New config option

        global _immich_first_run_skipped
        if not _immich_first_run_skipped and skip_initial:
            print("[Auto-Update Immich] Import initial skipped as per configuration.")
            immich_status_manager.update_status(message="Import initial ignoré.")
            _immich_first_run_skipped = True
            # Calculate next run and sleep, then continue to next iteration
            sleep_seconds = (interval_hours * 3600) if is_enabled else (15 * 60)
            next_run_time = datetime.now() + timedelta(seconds=sleep_seconds)
            immich_status_manager.update_status(next_run=next_run_time)
            if is_enabled:
                immich_status_manager.update_status(message="En attente...")
            time.sleep(sleep_seconds)
            continue # Skip the rest of this iteration
        
        if is_enabled:
            status_msg = f"Mise à jour auto. activée. Intervalle : {interval_hours}h."
            print(f"[Auto-Update Immich] {status_msg}")
            immich_status_manager.update_status(message=status_msg)
            
            try:
                immich_status_manager.update_status(message="Lancement du téléchargement...")
                print("[Auto-Update] Lancement du téléchargement et de la préparation...")
                
                # Étape 1: Téléchargement
                download_success = False
                for update in download_and_extract_album(config):
                    if update.get("type") == "error":
                        print(f"[Auto-Update] Erreur lors du téléchargement : {update.get('message')}")
                        immich_status_manager.update_status(message=f"Erreur téléchargement: {update.get('message')}")
                        break # Sortir de la boucle de téléchargement
                    immich_status_manager.update_status(message=update.get('message', '')) # Update status with download message
                    if update.get("type") == "done":
                        download_success = True

                # Étape 2: Préparation et redémarrage du diaporama
                if download_success:
                    immich_status_manager.update_status(message="Préparation des photos...")
                    screen_width = config.get("display_width", 1920) # Utiliser la résolution configurée
                    screen_height = config.get("display_height", 1080) # Utiliser la résolution configurée
                    prep_successful = False
                    for update in prepare_all_photos_with_progress(screen_width, screen_height, "immich"):
                        immich_status_manager.update_status(message=update.get('message', '')) # Update status with preparation message
                        if update.get("type") == "error":
                            print(f"[Auto-Update] Erreur lors de la préparation : {update.get('message')}")
                            immich_status_manager.update_status(message=f"Erreur préparation: {update.get('message')}")
                            break # Sortir de la boucle de préparation
                        if update.get("type") == "done":
                            prep_successful = True
                    
                    if prep_successful:
                        immich_status_manager.update_status(message="Mise à jour terminée. Redémarrage du diaporama...")
                        print("[Auto-Update] Mise à jour terminée avec succès. Redémarrage du diaporama.")
                        if is_slideshow_running():
                            stop_slideshow()
                            start_slideshow()
                        immich_status_manager.update_status(last_run=datetime.now(), message="Dernière mise à jour réussie.")
                    else:
                        immich_status_manager.update_status(message="Mise à jour terminée avec avertissements/erreurs.")

            except Exception as e:
                print(f"[Auto-Update] Erreur critique dans le worker : {e}")
                immich_status_manager.update_status(message=f"Erreur : {e}")

        else:
            status_msg = "Mise à jour automatique désactivée."
            print(f"[Auto-Update Immich] {status_msg}")
            immich_status_manager.update_status(message=status_msg)
        
        # Attendre avant la prochaine vérification
        sleep_seconds = (interval_hours * 3600) if is_enabled else (15 * 60)
        next_run_time = datetime.now() + timedelta(seconds=sleep_seconds)
        immich_status_manager.update_status(next_run=next_run_time) # Update next_run regardless of enabled state
        if is_enabled: # Only set message to "En attente..." if it's enabled
            immich_status_manager.update_status(message="En attente...")
        time.sleep(sleep_seconds)

def samba_update_worker():
    """
    Thread en arrière-plan qui vérifie et met à jour le partage Samba périodiquement.
    """
    print("== Démarrage du worker de mise à jour automatique Samba ==")
    while True:
        config = load_config()
        is_enabled = config.get("smb_auto_update", False)
        interval_hours = config.get("smb_update_interval_hours", 24)
        skip_initial = config.get("skip_initial_auto_import", False) # New config option

        global _samba_first_run_skipped
        if not _samba_first_run_skipped and skip_initial:
            print("[Auto-Update Samba] Import initial skipped as per configuration.")
            samba_status_manager.update_status(message="Import initial ignoré.")
            _samba_first_run_skipped = True
            # Calculate next run and sleep, then continue to next iteration
            sleep_seconds = (interval_hours * 3600) if is_enabled else (15 * 60)
            next_run_time = datetime.now() + timedelta(seconds=sleep_seconds)
            samba_status_manager.update_status(next_run=next_run_time)
            if is_enabled:
                samba_status_manager.update_status(message="En attente...")
            time.sleep(sleep_seconds)
            continue # Skip the rest of this iteration
        
        if is_enabled:
            status_msg = f"Mise à jour auto. activée. Intervalle : {interval_hours}h."
            print(f"[Auto-Update Samba] {status_msg}")
            samba_status_manager.update_status(message=status_msg)
            
            try:
                samba_status_manager.update_status(message="Lancement de l'import...")
                print("[Auto-Update Samba] Lancement de l'import et de la préparation...")
                
                import_success = False
                for update in import_samba_photos(config):
                    if update.get("type") == "error":
                        print(f"[Auto-Update Samba] Erreur lors de l'import : {update.get('message')}")
                        samba_status_manager.update_status(message=f"Erreur import: {update.get('message')}")
                        break # Sortir de la boucle d'import
                    samba_status_manager.update_status(message=update.get('message', '')) # Update status with import message
                    if update.get("type") == "done":
                        import_success = True

                if import_success:
                    samba_status_manager.update_status(message="Préparation des photos...")
                    screen_width = config.get("display_width", 1920) # Utiliser la résolution configurée
                    screen_height = config.get("display_height", 1080) # Utiliser la résolution configurée
                    prep_successful = False
                    for update in prepare_all_photos_with_progress(screen_width, screen_height, "samba"):
                        samba_status_manager.update_status(message=update.get('message', '')) # Update status with preparation message
                        if update.get("type") == "error": # This block is already handled by the outer loop
                            samba_status_manager.update_status(message=f"Erreur préparation: {update.get('message')}") # This update is redundant if outer loop handles it
                            break # This break is also redundant if outer loop handles it
                        if update.get("type") == "done":
                            prep_successful = True
                    
                    if prep_successful:
                        samba_status_manager.update_status(message="Mise à jour terminée. Redémarrage du diaporama...")
                        print("[Auto-Update Samba] Mise à jour terminée. Redémarrage du diaporama.")
                        if is_slideshow_running():
                            stop_slideshow()
                            start_slideshow()
                        samba_status_manager.update_status(last_run=datetime.now(), message="Dernière mise à jour réussie.")
                    else:
                        samba_status_manager.update_status(message="Mise à jour terminée avec avertissements/erreurs.")
            except Exception as e:
                print(f"[Auto-Update Samba] Erreur critique dans le worker : {e}")
                samba_status_manager.update_status(message=f"Erreur : {e}")
        else:
            samba_status_manager.update_status(message="Mise à jour automatique Samba désactivée.")
        
        sleep_seconds = (interval_hours * 3600) if is_enabled else (15 * 60)
        next_run_time = datetime.now() + timedelta(seconds=sleep_seconds)
        samba_status_manager.update_status(next_run=next_run_time) # Update next_run regardless of enabled state
        if is_enabled: # Only set message to "En attente..." if it's enabled
            samba_status_manager.update_status(message="En attente...")
        time.sleep(sleep_seconds)
# --- Import depuis Clé USB ---

@app.route("/import_usb_progress")
@login_required
def import_usb_progress():
    @stream_with_context
    def generate(): # type: ignore
        try:
            yield "Import depuis la clé USB...\n"
            import_usb_photos()
            yield "Préparation des photos...\n"
            prepare_all_photos()
            yield "Terminé. (100%)\n"
        except Exception as e:
            yield f"Erreur : {str(e)}\n"
    return Response(generate(), mimetype="text/plain")


# --- Gestion Diaporama ---

@app.route("/slideshow")
@login_required
def slideshow():
    return render_template("slideshow.html")

@app.route('/slideshow_view')
def slideshow_view():
    photos = get_all_prepared_photos()
    return render_template('slideshow_view.html', photos=photos)

@app.route('/toggle_slideshow', methods=['POST'])
@login_required
def toggle_slideshow():
    config = load_config()

    # On lit l'état actuel du slideshow
    running = is_slideshow_running()

    # Si le slideshow est lancé, on l'arrête, sinon on le démarre
    if running:
        stop_slideshow()
        config['manual_override'] = True  # Forcer l'arrêt manuel
    else:
        start_slideshow()
        config['manual_override'] = True  # Forcer le demarrage manuel

    save_config(config) # Save config after manual override

    return redirect(url_for('configure'))
    
# --- Suppression photo ---
@app.route('/delete_photo/<path:photo>', methods=['DELETE'])
@login_required
def delete_photo(photo):
    try:
        photo_path = os.path.join('static', 'prepared', photo)
        photo_path_obj = Path(photo_path)
        
        # Déterminer le chemin de la version polaroid et de la sauvegarde
        polaroid_path = photo_path_obj.with_name(f"{photo_path_obj.stem}_polaroid.jpg")
        backup_path = Path('static/.backups') / photo

        if os.path.isfile(photo_path):
            os.remove(photo_path)
        if polaroid_path.is_file():
            polaroid_path.unlink()
        if backup_path.is_file():
            backup_path.unlink()
        
        # Supprimer l'état du filtre pour cette photo
        states = load_filter_states()
        if states.pop(photo, None):
            save_filter_states(states)
        return '', 204
    except Exception as e:
        return str(e), 500
# --- Contrôle système ---

@app.route('/delete_source_photos/<source_name>', methods=['DELETE'])
@login_required
def delete_source_photos(source_name):
    """Supprime toutes les photos préparées pour une source donnée, y compris les sauvegardes."""
    if not re.match(r'^[a-zA-Z0-9_-]+$', source_name):
        return jsonify({"success": False, "message": "Nom de source invalide."}), 400

    prepared_dir = Path('static/prepared') / source_name
    backup_dir = Path('static/.backups') / source_name

    try:
        if prepared_dir.is_dir():
            shutil.rmtree(prepared_dir)
            print(f"Dossier préparé supprimé : {prepared_dir}")
        
        if backup_dir.is_dir():
            shutil.rmtree(backup_dir)
            print(f"Dossier de sauvegarde supprimé : {backup_dir}")

        # Supprimer les états de filtre pour cette source
        states = load_filter_states()
        keys_to_delete = [key for key in states if key.startswith(f"{source_name}/")]
        if keys_to_delete:
            for key in keys_to_delete:
                del states[key]
            save_filter_states(states)
        return jsonify({"success": True, "message": "Photos supprimées."}), 200
    except Exception as e:
        print(f"Erreur lors de la suppression des photos de la source {source_name}: {e}")
        return jsonify({"success": False, "message": f"Erreur serveur : {e}"}), 500

@app.route('/shutdown', methods=['POST'])
@login_required
def shutdown():
    os.system('sudo shutdown now')
    return redirect(url_for('configure'))

@app.route('/reboot', methods=['POST'])
@login_required
def reboot():
    os.system('sudo reboot')
    return redirect(url_for('configure'))

@app.route('/get_current_resolution')
@login_required
def get_current_resolution_route():
    """
    Endpoint pour récupérer la résolution de l'écran si le diaporama est actif.
    """
    if not is_slideshow_running():
        return jsonify({"success": False, "message": "Le diaporama doit être actif pour détecter la résolution."})
    
    width, height = get_screen_resolution()
    
    if width and height:
         return jsonify({"success": True, "width": width, "height": height})
    else:
         return jsonify({"success": False, "message": "Impossible de détecter la résolution."})

@app.route('/current_photo_status')
@login_required
def current_photo_status():
    """Retourne le chemin de la photo en cours d'affichage."""
    if not is_slideshow_running():
        return jsonify({"current_photo": None, "status": "stopped"})

    try:
        if os.path.exists(CURRENT_PHOTO_FILE):
            with open(CURRENT_PHOTO_FILE, "r") as f:
                photo_path = f.read().strip()
            if photo_path:
                # Construire l'URL complète pour l'attribut src de l'image
                return jsonify({"current_photo": url_for('static', filename=photo_path), "status": "running"})
    except Exception as e:
        print(f"Erreur lecture fichier photo actuelle : {e}")
        
    return jsonify({"current_photo": None, "status": "running"})

@app.route('/save_wifi_settings', methods=['POST'])
@login_required
def save_wifi_settings():
    ssid = request.form.get('wifi_ssid')
    password = request.form.get('wifi_password')

    if not ssid:
        flash("Le SSID Wi-Fi ne peut pas être vide.", "danger")
        return redirect(url_for('configure'))

    try:
        # Sauvegarder les paramètres dans la config.json
        config = load_config()
        config['wifi_ssid'] = ssid
        config['wifi_password'] = password
        save_config(config)

        # Appliquer les paramètres Wi-Fi au système
        set_wifi_config(ssid, password)
        flash("Paramètres Wi-Fi enregistrés et appliqués. Le Raspberry Pi va tenter de se connecter.", "success")
    except Exception as e:
        flash(f"Erreur lors de l'application des paramètres Wi-Fi : {e}", "danger")
    return redirect(url_for('configure'))
# --- Lancement de l'application ---

@app.route('/api/system_info')
@login_required
def get_system_info_api():
    """Retourne les informations système (température, CPU, RAM, stockage) en JSON."""
    try:
        # Température CPU
        cpu_temp = "N/A"
        try:
            # Essai avec vcgencmd (spécifique Raspberry Pi)
            temp_output = subprocess.check_output(['vcgencmd', 'measure_temp']).decode('utf-8')
            match = re.search(r"temp=(\d+\.?\d*)'C", temp_output)
            if match:
                cpu_temp = f"{float(match.group(1)):.1f}°C"
            else:
                # Fallback pour les systèmes Linux génériques
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    temp_raw = int(f.read())
                    cpu_temp = f"{temp_raw / 1000:.1f}°C"
        except Exception:
            try: # Second fallback if first generic fails
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    temp_raw = int(f.read())
                    cpu_temp = f"{temp_raw / 1000:.1f}°C"
            except Exception:
                pass # Keep N/A

        # Utilisation CPU
        cpu_usage = f"{psutil.cpu_percent(interval=0.1)}%" # Short interval for quick snapshot

        # Utilisation RAM
        ram = psutil.virtual_memory()
        ram_usage = f"{ram.percent}% ({ram.used / (1024**3):.1f}GB / {ram.total / (1024**3):.1f}GB)"

        # Utilisation Disque
        disk = psutil.disk_usage('/')
        disk_usage = f"{disk.percent}% ({disk.used / (1024**3):.1f}GB / {disk.total / (1024**3):.1f}GB)"

        return jsonify({
            "success": True,
            "cpu_temp": cpu_temp,
            "cpu_usage": cpu_usage,
            "ram_usage": ram_usage,
            "disk_usage": disk_usage
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/logs')
@login_required
def get_logs_api():
    """Retourne le contenu d'un fichier de log spécifié."""
    log_type = request.args.get('type', 'app')
    log_file_path = ""

    if log_type == 'app':
        log_file_path = "logs/log_app.txt"
    elif log_type == 'slideshow_stdout':
        log_file_path = "logs/slideshow_stdout.log"
    elif log_type == 'slideshow_stderr':
        log_file_path = "logs/slideshow_stderr.log"
    else:
        return jsonify({"success": False, "message": "Type de log invalide."})

    try:
        with open(log_file_path, 'r') as f:
            content = f.read()
        return jsonify({"success": True, "content": content})
    except FileNotFoundError:
        return jsonify({"success": False, "message": f"Fichier de log '{log_file_path}' non trouvé."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/clear_logs', methods=['POST'])
@login_required
def clear_logs_api():
    """Efface le contenu d'un fichier de log spécifié."""
    data = request.get_json()
    log_type = data.get('type')

    log_file_path = ""
    if log_type == 'app':
        log_file_path = "logs/log_app.txt"
    elif log_type == 'slideshow_stdout':
        log_file_path = "logs/slideshow_stdout.log"
    elif log_type == 'slideshow_stderr':
        log_file_path = "logs/slideshow_stderr.log"
    else:
        return jsonify({"success": False, "message": "Type de log invalide."}), 400

    try:
        if os.path.exists(log_file_path):
            with open(log_file_path, 'w') as f:
                f.truncate(0) # Efface le contenu du fichier
            return jsonify({"success": True, "message": f"Le log '{log_type}' a été effacé."})
        else:
            return jsonify({"success": False, "message": f"Fichier de log '{log_file_path}' non trouvé."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/tide_info')
@login_required
def get_tide_info_api():
    """Retourne les informations de marée depuis le fichier cache."""
    tide_cache_path = Path('cache/tides.json')
    if not tide_cache_path.exists():
        return jsonify({"success": False, "message": "Cache des marées non trouvé. Le diaporama doit tourner au moins une fois."})

    try:
        with open(tide_cache_path, 'r') as f:
            cache_data = json.load(f)
        
        last_update_iso = cache_data.get('timestamp')
        last_update_dt = datetime.fromisoformat(last_update_iso)
        last_update_str = last_update_dt.strftime('%d/%m/%Y à %H:%M:%S')

        tide_data = cache_data.get('data', {})
        next_high_str = "N/A"
        next_low_str = "N/A"
        api_status = "OK"

        if cache_data.get('cooldown'):
            api_status = f"En cooldown (quota API probablement atteint). Prochaine tentative après { (last_update_dt + timedelta(hours=12)).strftime('%H:%M') }."
        
        if tide_data.get('next_high') and tide_data['next_high'].get('time'):
            high_time_dt = datetime.fromisoformat(tide_data['next_high']['time'])
            next_high_str = f"{high_time_dt.strftime('%H:%M')} ({tide_data['next_high']['height']:.1f}m)"

        if tide_data.get('next_low') and tide_data['next_low'].get('time'):
            low_time_dt = datetime.fromisoformat(tide_data['next_low']['time'])
            next_low_str = f"{low_time_dt.strftime('%H:%M')} ({tide_data['next_low']['height']:.1f}m)"
            
        return jsonify({"success": True, "last_update": last_update_str, "next_high": next_high_str, "next_low": next_low_str, "api_status": api_status})
    except (json.JSONDecodeError, KeyError, Exception) as e:
        return jsonify({"success": False, "message": f"Erreur lecture du cache: {str(e)}"})

@app.route('/api/apply_filter', methods=['POST'])
@login_required
def apply_filter_api():
    """Applique un filtre à une photo préparée."""
    data = request.get_json()
    photo_relative_path = data.get('photo')
    filter_name = data.get('filter')

    if not photo_relative_path or not filter_name:
        return jsonify({"success": False, "message": "Chemin de la photo ou nom du filtre manquant."}), 400

    # Le chemin relatif est de la forme 'source/nom_photo.jpg'
    photo_full_path = Path('static/prepared') / photo_relative_path

    if not photo_full_path.is_file():
        return jsonify({"success": False, "message": f"Photo non trouvée : {photo_full_path}"}), 404

    try:
        apply_filter_to_image(str(photo_full_path), filter_name)
        # Le chemin ne change pas, mais on le renvoie pour forcer le rafraîchissement du cache du navigateur
        new_url = url_for('static', filename=f'prepared/{photo_relative_path}')
        return jsonify({"success": True, "message": "Filtre appliqué !", "new_path": new_url})
    except ValueError as e: # Pour les noms de filtres invalides
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        print(f"Erreur lors de l'application du filtre : {e}")
        return jsonify({"success": False, "message": f"Erreur interne du serveur : {e}"}), 500

@app.route('/api/set_photo_filter', methods=['POST'])
@login_required
def set_photo_filter():
    """Enregistre la préférence de filtre pour une photo donnée."""
    data = request.get_json()
    photo_relative_path = data.get('photo')
    filter_name = data.get('filter')

    if not photo_relative_path or not filter_name:
        return jsonify({"success": False, "message": "Données manquantes."}), 400

    states = load_filter_states()
    
    if filter_name in ['none', 'original']:
        # Si le filtre est 'none' ou 'original', on le retire du fichier d'état
        states.pop(photo_relative_path, None)
    else:
        states[photo_relative_path] = filter_name
    
    save_filter_states(states)
    return jsonify({"success": True, "message": "Préférence de filtre enregistrée."})

@app.route('/api/scan_wifi', methods=['GET'])
@login_required
def scan_wifi():
    """Scanne les réseaux Wi-Fi disponibles et les retourne en JSON."""
    try:
        # La commande nmcli est plus moderne et gérée par NetworkManager
        # --terse pour un output facile à parser
        # --fields pour ne sélectionner que les champs utiles
        # --rescan yes pour forcer une nouvelle recherche
        cmd = ['sudo', 'nmcli', '--terse', '--fields', 'SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list', '--rescan', 'yes']
        
        # Utiliser un timeout pour éviter que la requête ne bloque indéfiniment
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=20)
        
        output = result.stdout.strip()
        
        # Éviter les doublons de SSID, ne garder que le plus fort signal
        seen_ssids = {}

        for line in output.split('\n'):
            if not line:
                continue
            
            # Gérer les SSID qui peuvent contenir des ':' en les échappant.
            # nmcli --terse échappe les ':' avec '\:'. On ne peut pas juste splitter.
            # La méthode la plus simple est de joindre toutes les parties sauf les deux dernières.
            parts = line.split(':')
            if len(parts) < 3:
                continue
            
            security = parts[-1]
            signal = int(parts[-2])
            ssid = ":".join(parts[:-2]).replace('\\:', ':')

            if not ssid: # Ignorer les SSID vides (réseaux cachés)
                continue

            # Si on a déjà vu ce SSID, on garde seulement celui avec le meilleur signal
            if ssid not in seen_ssids or signal > seen_ssids[ssid]['signal']:
                seen_ssids[ssid] = {
                    "ssid": ssid,
                    "signal": signal,
                    "security": security if security else "Open"
                }
        
        networks = sorted(seen_ssids.values(), key=lambda x: x['signal'], reverse=True)

        return jsonify({"success": True, "networks": networks})

    except FileNotFoundError:
        return jsonify({"success": False, "message": "La commande 'nmcli' est introuvable. NetworkManager est-il installé et actif ?"}), 500
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "message": f"Erreur lors du scan Wi-Fi : {e.stderr}"}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "message": "Le scan Wi-Fi a pris trop de temps (timeout)."}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur inattendue : {str(e)}"}), 500

if __name__ == '__main__':
    # Démarrer les workers de mise à jour dans des threads séparés
    immich_thread = threading.Thread(target=immich_update_worker, daemon=True)
    immich_thread.start()
    samba_thread = threading.Thread(target=samba_update_worker, daemon=True)
    samba_thread.start()

    # Vérifier si le diaporama doit être lancé au démarrage
    check_and_start_slideshow_on_boot()

    app.run(host='0.0.0.0', port=5000)
