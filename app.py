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
from datetime import datetime, timedelta
from pathlib import Path

# Modules internes
from utils.download_album import download_and_extract_album
from utils.auth import login_required
from utils.slideshow_manager import is_slideshow_running, start_slideshow, stop_slideshow
from utils.prepare_all_photos import prepare_all_photos_with_progress
from utils.import_usb_photos import import_usb_photos  # Déplacé dans utils
from utils.import_samba import import_samba_photos

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Chemins de config
CONFIG_PATH = 'config/config.json'
CREDENTIALS_PATH = '/boot/firmware/credentials.json'

# --- Gestionnaire d'état pour les workers ---
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


# --- Fonctions utilitaires ---

def get_screen_resolution():
    """
    Détecte la résolution de l'écran principal via swaymsg.
    Retourne (width, height) ou (1920, 1080) en cas d'erreur.
    """
    default_width = 1920
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

        result = subprocess.run(['swaymsg', '-t', 'get_outputs'], capture_output=True, text=True, check=True)
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
        "pan_zoom_factor": 1.15, # New option
        "immich_auto_update": False,
        "immich_update_interval_hours": 24,
        "pan_zoom_enabled": False, # New option
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
        "weather_units": "metric", # Re-added
        "weather_update_interval_minutes": 60, # Re-added
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

def save_config(config):
    temp_path = CONFIG_PATH + '.tmp'
    try:
        with open(temp_path, 'w') as f:
            json.dump(config, f, indent=4)
        os.rename(temp_path, CONFIG_PATH)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde de la configuration : {e}")

def get_prepared_photos_by_source():
    """
    Récupère les photos préparées, organisées par leur source (immich, usb, samba).
    Retourne un dictionnaire où les clés sont les noms des sources
    et les valeurs sont des listes de chemins relatifs aux photos.
    Ex: {'immich': ['immich/photo1.jpg', 'immich/photo2.jpg'], 'usb': ['usb/photo3.jpg']}
    """
    base_prepared_dir = Path("static/prepared")
    photos_by_source = {}
    for source_dir in base_prepared_dir.iterdir():
        if source_dir.is_dir():
            source_name = source_dir.name
            photos = sorted([
                f.name for f in source_dir.glob("*")
                if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".gif"]
            ])
            photos_by_source[source_name] = [f"{source_name}/{photo}" for photo in photos]
    return photos_by_source

def get_all_prepared_photos():
    """
    Récupère toutes les photos préparées de toutes les sources dans une seule liste plate.
    """
    return [photo for source_photos in get_prepared_photos_by_source().values() for photo in source_photos]



# --- Routes principales ---

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if check_credentials(request.form['username'], request.form['password']):
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
            'pan_zoom_factor', # Added pan_zoom_factor
            'immich_update_interval_hours', 'date_format', 
            'weather_api_key', 'weather_city', 'weather_units', 'weather_update_interval_minutes', # Re-added
            'smb_host', 'smb_share', 'smb_path', 'smb_user', 'smb_password',
            'smb_update_interval_hours'
        ]:
            if key in request.form:
                value = request.form.get(key)
                # Gérer les champs numériques
                if key in ['display_duration', 'clock_offset_x', 'clock_offset_y', 'clock_font_size', 'weather_update_interval_minutes', 'immich_update_interval_hours', 'smb_update_interval_hours']: # Integer fields
                    try:
                        config[key] = int(value)
                    except (ValueError, TypeError):
                        config[key] = 0 # Mettre une valeur par défaut en cas d'erreur
                elif key in ['pan_zoom_factor']: # Float fields
                    try:
                        config[key] = float(value)
                    except (ValueError, TypeError):
                        config[key] = 1.0 # Default to no zoom
                else: # Gérer les champs texte
                    config[key] = value
        
        # Gérer la clé display_sources (checkboxes)
        # request.form.getlist() retourne une liste vide si aucune checkbox avec ce nom n'est cochée.
        config['display_sources'] = request.form.getlist('display_sources')
        config["pan_zoom_enabled"] = 'pan_zoom_enabled' in request.form # New checkbox handling
        config["clock_background_enabled"] = 'clock_background_enabled' in request.form

        # Traitement des checkboxes
        config["show_clock"] = 'show_clock' in request.form
        config["immich_auto_update"] = 'immich_auto_update' in request.form
        config["smb_auto_update"] = 'smb_auto_update' in request.form

        config["show_date"] = 'show_date' in request.form
        config["show_weather"] = 'show_weather' in request.form
        save_config(config)
        stop_slideshow()
        start_slideshow()
        flash("Configuration enregistrée et diaporama relancé", "success")
        return redirect(url_for('configure'))

    slideshow_running = any(
        'local_slideshow.py' in (p.info['cmdline'] or []) for p in psutil.process_iter(attrs=['cmdline'])
    )
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
            return f"data: {json.dumps(data)}\n\n"

        screen_width, screen_height = get_screen_resolution()

        try:
            # --- Étape 1: Import depuis la clé USB ---
            for update in import_usb_photos():
                if update.get("type") == "error":
                    yield stream_event(update)
                    return  # Arrêter le flux en cas d'erreur
                
                # Simplifier l'événement pour le client, ne garder que l'essentiel
                if update.get("type") in ["progress", "done"]:
                    yield stream_event({"type": "progress", "percent": update.get("percent"), "message": update.get("message")})
                elif update.get("type") == "warning":
                    yield stream_event(update)

            # --- Étape 2: Compter les photos et préparer ---
            source_dir = Path("static/photos")
            photo_files = [f for f in source_dir.iterdir() if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.heic', '.heif']]
            total_photos = len(photo_files)

            if total_photos > 0:
                yield stream_event({
                    "type": "progress", "stage": "PREPARING", "percent": 80,
                    "message": f"Préparation de {total_photos} photos pour l'affichage..."
                })
                
                for update in prepare_all_photos_with_progress(screen_width, screen_height, "usb"):
                    # Seuls les événements de type 'progress' sont transformés pour la barre principale
                    if update.get("type") == "progress":
                        prep_percent = update.get("percent", 0)
                        # Créer un message de progression unifié pour le front-end
                        main_progress_update = {
                            "type": "progress",
                            "percent": 80 + int(prep_percent * 0.20), # Pourcentage mis à l'échelle
                            "message": f"Préparation de {total_photos} photos pour l'affichage..."
                        }
                        yield stream_event(main_progress_update)
                    # Les avertissements et erreurs sont transmis directement
                    elif update.get("type") in ["warning", "error"]:
                        yield stream_event(update)
                yield stream_event({
                    "type": "done", "percent": 100,
                    "message": f"Import terminé ! {total_photos} photos sont prêtes."
                })
            else:
                yield stream_event({"type": "warning", "message": "Aucune photo n'a été importée ou trouvée."})

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
            """Formate les données en événement Server-Sent Event (SSE)."""
            return f"data: {json.dumps(data)}\n\n"

        screen_width, screen_height = get_screen_resolution()

        try:
            # --- Étape 1: Téléchargement depuis Immich ---
            for update in download_and_extract_album(config):
                if update.get("type") == "error":
                    yield stream_event(update)
                    return  # Stop on error

                # Simplifier l'événement pour le client, ne garder que l'essentiel
                if update.get("type") in ["progress", "done"]:
                    yield stream_event({"type": "progress", "percent": update.get("percent"), "message": update.get("message")})
                elif update.get("type") == "warning":
                    yield stream_event(update)

            # --- Étape 2: Compter les photos et préparer ---
            source_dir = Path("static/photos")
            photo_files = [f for f in source_dir.iterdir() if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.heic', '.heif']]
            total_photos = len(photo_files)

            if total_photos > 0:
                yield stream_event({
                    "type": "progress", "stage": "PREPARING", "percent": 80,
                    "message": f"Préparation de {total_photos} photos pour l'affichage..."
                })

                for update in prepare_all_photos_with_progress(screen_width, screen_height, "immich"):
                    # Seuls les événements de type 'progress' sont transformés pour la barre principale
                    if update.get("type") == "progress":
                        prep_percent = update.get("percent", 0)
                        # Créer un message de progression unifié pour le front-end
                        main_progress_update = {
                            "type": "progress",
                            "percent": 80 + int(prep_percent * 0.20), # Pourcentage mis à l'échelle
                            "message": f"Préparation de {total_photos} photos pour l'affichage..."
                        }
                        yield stream_event(main_progress_update)
                    # Les avertissements et erreurs sont transmis directement
                    elif update.get("type") in ["warning", "error"]:
                        yield stream_event(update)
                yield stream_event({
                    "type": "done", "percent": 100,
                    "message": f"Import Immich terminé ! {total_photos} photos sont prêtes."
                })
            else:
                yield stream_event({"type": "warning", "message": "Aucune photo n'a été téléchargée ou trouvée."})

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
            return f"data: {json.dumps(data)}\n\n"

        screen_width, screen_height = get_screen_resolution()

        try:
            # --- Étape 1: Import depuis Samba ---
            for update in import_samba_photos(config):
                if update.get("type") == "error":
                    yield stream_event(update)
                    return

                # Simplifier l'événement pour le client, ne garder que l'essentiel
                if update.get("type") in ["progress", "done"]:
                    yield stream_event({"type": "progress", "percent": update.get("percent"), "message": update.get("message")})
                elif update.get("type") == "warning":
                    yield stream_event(update)

            # --- Étape 2: Compter les photos et préparer ---
            source_dir = Path("static/photos")
            photo_files = [f for f in source_dir.iterdir() if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.heic', '.heif']]
            total_photos = len(photo_files)

            if total_photos > 0:
                yield stream_event({
                    "type": "progress", "stage": "PREPARING", "percent": 80,
                    "message": f"Préparation de {total_photos} photos pour l'affichage..."
                })

                for update in prepare_all_photos_with_progress(screen_width, screen_height, "samba"):
                    # Seuls les événements de type 'progress' sont transformés pour la barre principale
                    if update.get("type") == "progress":
                        prep_percent = update.get("percent", 0)
                        # Créer un message de progression unifié pour le front-end
                        main_progress_update = {
                            "type": "progress",
                            "percent": 80 + int(prep_percent * 0.20), # Pourcentage mis à l'échelle
                            "message": f"Préparation de {total_photos} photos pour l'affichage..."
                        }
                        yield stream_event(main_progress_update)
                    # Les avertissements et erreurs sont transmis directement
                    elif update.get("type") in ["warning", "error"]:
                        yield stream_event(update)
                yield stream_event({"type": "done", "percent": 100, "message": f"Import Samba terminé ! {total_photos} photos prêtes."})
            else:
                yield stream_event({"type": "warning", "message": "Aucune photo n'a été importée ou trouvée."})

        except Exception as e:
            yield stream_event({"type": "error", "message": f"Erreur critique : {str(e)}"})

    return Response(generate(), mimetype='text/event-stream', headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})

@app.route('/test-samba', methods=['POST'])
@login_required
def test_samba_connection():
    """Teste la connexion à un partage Samba sans importer de fichiers."""
    from smbclient import register_session, path
    from smbprotocol.exceptions import SMBException

    data = request.get_json()
    server = data.get("smb_host")
    share = data.get("smb_share")
    path_in_share = data.get("smb_path", "")
    user = data.get("smb_user")
    password = data.get("smb_password")

    if not all([server, share]):
        return jsonify({"success": False, "message": "Le serveur et le nom du partage sont requis."})

    full_samba_path = f"\\\\{server}\\{share}\\{path_in_share}".replace('/', '\\')

    try:
        if user and password:
            register_session(server, username=user, password=password)
        
        if path.exists(full_samba_path):
            return jsonify({"success": True, "message": "Connexion réussie ! Le chemin a été trouvé."})
        return jsonify({"success": False, "message": "Connexion réussie, mais le chemin est introuvable."})
    except SMBException as e:
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
        response = requests.get(url, timeout=5)
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
        # This route seems to be a simple POST fallback and might need to be updated or removed.
        flash("Photos téléchargées avec succès", "success")
    except Exception as e:
        flash(f"Erreur téléchargement : {e}", "danger")
    return redirect(url_for("configure"))


# --- Worker de mise à jour automatique ---

def immich_update_worker():
    """
    Thread en arrière-plan qui vérifie et met à jour l'album Immich périodiquement.
    """
    print("== Démarrage du worker de mise à jour automatique Immich ==")
    while True:
        config = load_config()
        is_enabled = config.get("immich_auto_update", False)
        interval_hours = config.get("immich_update_interval_hours", 24)
        
        if is_enabled:
            message = f"Mise à jour auto. activée. Intervalle : {interval_hours}h."
            print(f"[Auto-Update Immich] {message}")
            immich_status_manager.update_status(message=message)
            
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
                    screen_width, screen_height = get_screen_resolution() # Récupérer la résolution
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
            message = "Mise à jour automatique désactivée."
            print(f"[Auto-Update Immich] {message}")
            immich_status_manager.update_status(message=message)
        
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
        
        if is_enabled:
            message = f"Mise à jour auto. activée. Intervalle : {interval_hours}h."
            print(f"[Auto-Update Samba] {message}")
            samba_status_manager.update_status(message=message)
            
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
                    screen_width, screen_height = get_screen_resolution() # Récupérer la résolution
                    prep_successful = False
                    for update in prepare_all_photos_with_progress(screen_width, screen_height, "samba"):
                        samba_status_manager.update_status(message=update.get('message', '')) # Update status with preparation message
                        if update.get("type") == "error":
                            print(f"[Auto-Update Samba - Prepare] Erreur lors de la préparation : {update.get('message')}")
                            samba_status_manager.update_status(message=f"Erreur préparation: {update.get('message')}")
                            break # Arrêter la préparation en cas d'erreur critique
                        elif update.get("type") == "warning":
                            print(f"[Auto-Update Samba - Prepare] Avertissement lors de la préparation : {update.get('message')}")
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
    def generate():
        try:
            yield "Import depuis la clé USB...\n"
            import_usb_photos()
            yield "Préparation des photos...\n"
            prepare_all_photos()
            yield "TerminÃ©. (100%)\n"
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

    save_config(config)

    return redirect(url_for('configure'))
    
# --- Suppression photo ---
@app.route('/delete_photo/<path:photo>', methods=['DELETE'])
@login_required
def delete_photo(photo):
    try:
        photo_path = os.path.join('static', 'prepared', photo)
        if os.path.isfile(photo_path):
            os.remove(photo_path)
            return '', 204
        return 'Not found', 404
    except Exception as e:
        return str(e), 500
# --- Contrôle système ---

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


# --- Lancement de l'application ---
if __name__ == '__main__':
    # Démarrer les workers de mise à jour dans des threads séparés
    immich_thread = threading.Thread(target=immich_update_worker, daemon=True)
    immich_thread.start()
    samba_thread = threading.Thread(target=samba_update_worker, daemon=True)
    samba_thread.start()

    # Vérifier si le diaporama doit être lancé au démarrage
    check_and_start_slideshow_on_boot()

    app.run(host='0.0.0.0', port=5000)
