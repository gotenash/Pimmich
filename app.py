from flask import Flask, render_template, request, redirect, url_for, session, flash, stream_with_context, Response, jsonify, send_from_directory
import os
import json
import re
from flask_babel import Babel, _
import subprocess
import psutil
import glob
import time
import requests
import threading
import logging
import asyncio
import collections
import shutil
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from pathlib import Path
from werkzeug.security import check_password_hash
import secrets
import signal
import traceback

from utils.download_album import download_and_extract_album
from utils.auth import login_required # type: ignore
from utils.slideshow_manager import is_slideshow_running, start_slideshow, stop_slideshow, restart_slideshow_process, restart_slideshow_for_update
from utils.config_manager import load_config, save_config
from utils.playlist_manager import load_playlists, save_playlists
from utils.auth_manager import change_password
from utils.network_manager import get_interface_status, set_interface_state
from utils.wifi_manager import set_wifi_config # Import the new utility
from utils.display_manager import get_display_output_name, set_display_power
from utils.prepare_all_photos import prepare_all_photos_with_progress
from utils.import_usb_photos import import_usb_photos  # Déplacé dans utils
from utils.import_samba import import_samba_photos
from utils.image_filters import apply_filter_to_image, add_text_to_polaroid, add_text_to_image, create_polaroid_effect
from utils.voice_control_manager import start_voice_control, stop_voice_control, is_voice_control_running
from utils.telegram_bot import PimmichBot
import smbclient
from smbprotocol.exceptions import SMBException


app = Flask(__name__)

# --- Clé secrète ---
# Il est recommandé de ne pas hardcoder la clé secrète.
# On essaie de la charger depuis les credentials, sinon on en génère une pour le fallback.
try:
    credentials = load_credentials()
    app.secret_key = credentials.get('flask_secret_key', 'supersecretkey_fallback_should_be_changed')
except Exception:
    app.secret_key = 'supersecretkey_fallback_should_be_changed'

# --- NOUVEAU: Limiter la taille des uploads pour éviter les crashs sur RPi ---
# Limite à 32 Mo, ce qui est raisonnable pour des photos.
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

# Configuration du logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler()]) # Envoie les logs vers la sortie standard/erreur, qui est redirigée vers les fichiers de log.


def get_locale():
    # 1. Si un argument 'lang' est passé dans l'URL
    lang = request.args.get('lang')
    if lang and lang in app.config['LANGUAGES']:
        session['lang'] = lang
        return lang
    # 2. Si l'utilisateur a une langue définie dans sa session
    if 'lang' in session and session['lang'] in app.config['LANGUAGES']:
        return session['lang']
    # 3. Depuis l'en-tête 'Accept-Language' du navigateur
    return request.accept_languages.best_match(list(app.config['LANGUAGES'].keys()))

# --- Configuration de Babel (i18n) ---
app.config['LANGUAGES'] = {'fr': 'Français', 'en': 'English', 'es': 'Español'}
app.config['BABEL_DEFAULT_LOCALE'] = 'fr'
babel = Babel(app, locale_selector=get_locale)

# --- Fin de la configuration de Babel ---

@app.context_processor
def inject_locale():
    """Injecte la fonction get_locale dans le contexte des templates."""
    return dict(get_locale=get_locale)


# Chemins de base
BASE_DIR = Path(__file__).resolve().parent
# Chemins de config
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv')
PENDING_UPLOADS_DIR = BASE_DIR / "static" / "pending_uploads"
CONFIG_PATH = 'config/config.json'
CREDENTIALS_PATH = '/boot/firmware/credentials.json'
FILTER_STATES_PATH = 'config/filter_states.json'
FAVORITES_PATH = 'config/favorites.json'
POLAROID_TEXTS_PATH = 'config/polaroid_texts.json'
TEXT_STATES_PATH = 'config/text_states.json'
INVITATIONS_PATH = 'config/invitations.json'
TELEGRAM_GUEST_USERS_PATH = 'config/telegram_guest_users.json'
NEW_POSTCARD_FLAG_PATH = 'cache/new_postcard.flag'
CUSTOM_PLAYLIST_FILE = "/tmp/pimmich_custom_playlist.json"
CURRENT_PHOTO_FILE = "/tmp/pimmich_current_photo.txt"
PREPARED_DIR = BASE_DIR / "static" / "prepared"

# Dictionnaire central pour les fichiers de log
LOG_FILES_MAP = {
    "app": {"path": "logs/log_app.txt", "name_key": "app.py (Serveur Web & Supervisor)"},
    "slideshow_stdout": {"path": "logs/slideshow_stdout.log", "name_key": "local_slideshow.py (Diaporama - Sortie Standard)"},
    "slideshow_stderr": {"path": "logs/slideshow_stderr.log", "name_key": "local_slideshow.py (Diaporama - Erreurs)"},
    "voice_control_stdout": {"path": "logs/voice_control_stdout.log", "name_key": "voice_control.py (Contrôle Vocal - Sortie Standard)"},
    "voice_control_stderr": {"path": "logs/voice_control_stderr.log", "name_key": "voice_control.py (Contrôle Vocal - Erreurs)"},
}

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
telegram_status_manager = WorkerStatus()

# Historique pour le graphique de température CPU (conserve les 60 dernières mesures)
cpu_temp_history = collections.deque(maxlen=60)
# NOUVEAU: Historique pour le graphique d'utilisation CPU
cpu_usage_history = collections.deque(maxlen=60)
# NOUVEAU: Historique pour le graphique d'utilisation RAM
ram_usage_history = collections.deque(maxlen=60)
# NOUVEAU: Historique pour le graphique d'utilisation Disque
disk_usage_history = collections.deque(maxlen=60)

def get_screen_resolution():
    """
    Détecte la résolution de l'écran principal via swaymsg.
    Retourne (width, height) ou (1920, 1080) en cas d'erreur.
    """
    # Charger la configuration pour avoir une résolution de secours fiable
    config = load_config()
    default_width = int(config.get('display_width', 1920))
    default_height = int(config.get('display_height', 1080))
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
                print("SWAYSOCK non trouvé, utilisation de la résolution de secours depuis la config.")
                return default_width, default_height

        # Utiliser HDMI_OUTPUT du slideshow_manager pour cibler la bonne sortie
        # ou chercher la sortie active si HDMI_OUTPUT n'est pas suffisant.
        # Pour l'instant, on se base sur la sortie active.
        result = subprocess.run(['swaymsg', '-t', 'get_outputs'], capture_output=True, text=True, check=True, env=os.environ)
        outputs = json.loads(result.stdout)
        
        # --- MODIFICATION ---
        # On cherche la première sortie qui a un mode configuré, qu'elle soit active ou non.
        # C'est plus robuste car l'écran peut être désactivé (en veille).
        for output in outputs:
            if output.get('current_mode'):
                mode = output['current_mode']
                print(f"Résolution détectée sur la sortie '{output.get('name')}': {mode['width']}x{mode['height']} (Active: {output.get('active', False)})")
                return mode['width'], mode['height']
        
        print("Aucune sortie avec un mode configuré trouvée (écran en veille ?), utilisation de la résolution de secours depuis la config.")
        return default_width, default_height
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError, IndexError) as e:
        print(f"Erreur lors de la détection de la résolution de l'écran : {e}. Utilisation de la résolution de secours depuis la config.")
        return default_width, default_height
    except Exception as e:
        print(f"Erreur inattendue lors de la détection de la résolution : {e}. Utilisation de la résolution de secours depuis la config.")
        return default_width, default_height

def get_photo_previews():
    photo_dir = BASE_DIR / "static" / "photos"
    return sorted([f.name for f in photo_dir.glob("*") if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".gif"]])

def load_credentials():
    try:
        with open(CREDENTIALS_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback if file is missing or corrupt. setup.sh should create it.
        # The hash is for the default password 'pimmich'.
        return {"username": "admin", "password_hash": "pbkdf2:sha256:600000$YgWJtLgqgBqYvRzS$b2185c72e38933b3c655b7a748c928b1b88b1d62480579f4a1f9b1b1c8e8c8d2"}

def check_credentials(username, password):
    credentials = load_credentials()
    stored_username = credentials.get("username")
    stored_hash = credentials.get("password_hash")

    if not stored_username or not stored_hash:
        # Handle legacy plaintext password for backward compatibility
        stored_password = credentials.get("password")
        if stored_password and username == stored_username and password == stored_password:
            print("AVERTISSEMENT: Le mot de passe est stocké en clair. Veuillez le changer pour le sécuriser.")
            return True
        return False

    return username == stored_username and check_password_hash(stored_hash, password)

def load_filter_states():
    """Charge les états des filtres depuis un fichier JSON."""
    if not os.path.exists(FILTER_STATES_PATH):
        return {}
    try:
        with open(FILTER_STATES_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_filter_states(states):
    """Sauvegarde les états des filtres dans un fichier JSON."""
    try:
        with open(FILTER_STATES_PATH, 'w') as f:
            json.dump(states, f, indent=4)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des états de filtre : {e}")

def load_favorites():
    """Charge la liste des photos favorites depuis un fichier JSON."""
    if not os.path.exists(FAVORITES_PATH):
        return []
    try:
        with open(FAVORITES_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

def save_favorites(favorites_list):
    """Sauvegarde la liste des photos favorites dans un fichier JSON."""
    try:
        with open(FAVORITES_PATH, 'w') as f:
            json.dump(favorites_list, f, indent=2)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des favoris : {e}")

def load_polaroid_texts():
    """Charge les textes des polaroids depuis un fichier JSON."""
    if not os.path.exists(POLAROID_TEXTS_PATH):
        return {}
    try:
        with open(POLAROID_TEXTS_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_polaroid_texts(texts_dict):
    """Sauvegarde les textes des polaroids dans un fichier JSON."""
    try:
        with open(POLAROID_TEXTS_PATH, 'w') as f:
            json.dump(texts_dict, f, indent=2)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des textes polaroid : {e}")

def load_text_states():
    """Charge les textes des photos depuis un fichier JSON."""
    if not os.path.exists(TEXT_STATES_PATH):
        return {}
    try:
        with open(TEXT_STATES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_text_states(states):
    """Sauvegarde les textes des photos dans un fichier JSON."""
    try:
        with open(TEXT_STATES_PATH, 'w', encoding='utf-8') as f:
            json.dump(states, f, indent=4)
    except IOError as e:
        print(f"Erreur lors de la sauvegarde des états de texte : {e}")

def load_telegram_guest_users():
    """Charge les utilisateurs invités de Telegram depuis un fichier JSON."""
    if not os.path.exists(TELEGRAM_GUEST_USERS_PATH):
        return {}
    try:
        with open(TELEGRAM_GUEST_USERS_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_telegram_guest_users(guest_users_dict):
    """Sauvegarde les utilisateurs invités de Telegram dans un fichier JSON."""
    try:
        with open(TELEGRAM_GUEST_USERS_PATH, 'w') as f:
            json.dump(guest_users_dict, f, indent=4)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des invités Telegram : {e}")

def add_telegram_guest_user(user_id, guest_name):
    """Ajoute un nouvel invité Telegram et sauvegarde le fichier."""
    guest_users = load_telegram_guest_users()
    guest_users[str(user_id)] = guest_name
    save_telegram_guest_users(guest_users)

def load_invitations():
    """Charge les invitations Telegram depuis un fichier JSON."""
    if not os.path.exists(INVITATIONS_PATH):
        return {}
    try:
        with open(INVITATIONS_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_invitations(invitations_dict):
    """Sauvegarde les invitations Telegram dans un fichier JSON."""
    try:
        with open(INVITATIONS_PATH, 'w') as f:
            json.dump(invitations_dict, f, indent=4)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des invitations : {e}")

def get_prepared_photos_by_source():
    """
    Récupère les médias préparés (photos et vidéos), organisés par leur source.
    Retourne un dictionnaire où les clés sont les noms des sources et les valeurs sont des listes de dictionnaires.
    Ex: {'immich': [{'path': 'immich/media.jpg', 'type': 'image', 'has_polaroid': True}, ...]}
    """
    # Charger la configuration pour obtenir les noms des invités
    config = load_config()
    guest_users = config.get('telegram_guest_users', {})

    base_prepared_dir = PREPARED_DIR
    media_by_source = {}
    filter_states = load_filter_states()
    favorites = load_favorites()
    polaroid_texts = load_polaroid_texts()
    text_states = load_text_states()
    
    if base_prepared_dir.exists():
        for source_dir in base_prepared_dir.iterdir():
            if source_dir.is_dir():
                source_name = source_dir.name
                
                # Lister tous les fichiers (images et vidéos)
                all_files_in_dir = list(source_dir.iterdir())
                all_filenames = {f.name for f in all_files_in_dir}
                
                # Identifier les médias de base (non-polaroid, non-vignette, non-postcard)
                base_media = sorted(
                    [f for f in all_files_in_dir if f.is_file() and not f.name.endswith(('_polaroid.jpg', '_thumbnail.jpg', '_postcard.jpg'))]
                )

                media_data_list = []
                for media_path_obj in base_media:
                    media_name = media_path_obj.name
                    media_relative_path = f"{source_name}/{media_name}"
                    media_type = 'video' if media_path_obj.suffix.lower() in VIDEO_EXTENSIONS else 'image'
                    
                    media_item = {
                        "path": media_relative_path,
                        "type": media_type,
                        "is_favorite": media_relative_path in favorites
                    }

                    # Les options de filtre ne s'appliquent qu'aux images
                    if media_type == 'image':
                        base_name = media_path_obj.stem
                        has_polaroid = f"{base_name}_polaroid.jpg" in all_filenames
                        has_postcard = f"{base_name}_postcard.jpg" in all_filenames
                        media_item["has_polaroid"] = has_polaroid
                        media_item["has_postcard"] = has_postcard
                        media_item["polaroid_text"] = polaroid_texts.get(media_relative_path, "")
                        media_item["text"] = text_states.get(media_relative_path, "")
                        media_item["active_filter"] = filter_states.get(media_relative_path, "none")
                    elif media_type == 'video':
                        # Chercher la vignette correspondante pour la vidéo
                        thumbnail_name = f"{media_path_obj.stem}_thumbnail.jpg"
                        if thumbnail_name in all_filenames:
                            media_item["thumbnail_path"] = f"{source_name}/{thumbnail_name}"
                    
                    media_data_list.append(media_item)
                
                if media_data_list:
                    media_by_source[source_name] = media_data_list
                    
    return media_by_source

def handle_new_telegram_photo(temp_photo_path_str, caption, user_name=None):
    """
    Fonction de rappel pour traiter une nouvelle photo reçue via Telegram.
    Cette fonction est synchrone et peut maintenant inclure le nom de l'expéditeur.
    """
    with app.app_context():
        print(f"[Telegram] Traitement de la nouvelle photo : {temp_photo_path_str}")
        try:
            # Construire la légende finale en ajoutant le nom de l'expéditeur
            final_caption = caption
            if user_name:
                # Si une légende existe déjà, ajouter le nom avant. Sinon, utiliser juste le nom.
                if caption:
                    final_caption = f"De {user_name} : {caption}"
                else:
                    final_caption = f"De {user_name}"

            temp_photo_path = Path(temp_photo_path_str)
            
            # 1. Définir les chemins
            source_dir = BASE_DIR / "static" / "photos" / "telegram"
            prepared_dir = BASE_DIR / "static" / "prepared" / "telegram"
            source_dir.mkdir(parents=True, exist_ok=True)
            prepared_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = int(time.time())
            # Ajouter quelques caractères aléatoires pour éviter les collisions si plusieurs photos arrivent dans la même seconde
            new_filename_base = f"telegram_{timestamp}_{secrets.token_hex(4)}"
            
            # 2. Copier la photo temporaire vers le dossier source permanent
            source_photo_path = source_dir / f"{new_filename_base}.jpg"
            shutil.copy(temp_photo_path, source_photo_path)
            
            # 3. Préparer la photo
            from utils.prepare_all_photos import prepare_photo # Import local pour éviter dépendance circulaire
            prepared_photo_path = prepared_dir / f"{new_filename_base}.jpg"
            config = load_config()
            screen_width, screen_height = config.get("display_width", 1920), config.get("display_height", 1080)
            prepare_photo(str(source_photo_path), str(prepared_photo_path), screen_width, screen_height, source_type='telegram', caption=final_caption)
            
            # 4. Gérer la légende
            if final_caption:
                relative_path = f"telegram/{new_filename_base}.jpg"
                text_states = load_text_states()
                text_states[relative_path] = final_caption
                save_text_states(text_states)
                add_text_to_image(str(prepared_photo_path), final_caption)

            # Créer un fichier "drapeau" pour notifier le diaporama et y écrire le chemin de la nouvelle carte postale
            postcard_path = prepared_dir / f"{new_filename_base}_postcard.jpg"
            path_to_write = str(postcard_path) if postcard_path.exists() else str(prepared_photo_path)

            try:
                with open(NEW_POSTCARD_FLAG_PATH, 'w') as f:
                    f.write(path_to_write)
                print(f"[Telegram] Fichier de notification sonore créé avec le chemin : {path_to_write}")
            except Exception as e:
                print(f"[Telegram] ERREUR lors de la création du fichier de notification : {e}")

            print(f"[Telegram] Photo {new_filename_base}.jpg traitée avec succès.")
        except Exception as e:
            error_message = f"[Telegram] ERREUR lors du traitement de la photo : {e}\n{traceback.format_exc()}"
            print(error_message)
            # Renvoyer l'exception pour que le bot puisse notifier l'utilisateur de l'échec.
            raise Exception(f"Le traitement de la photo a échoué côté serveur. {e}")
        finally:
            # Nettoyer le fichier temporaire créé par le bot
            if Path(temp_photo_path_str).exists():
                Path(temp_photo_path_str).unlink()

def validate_telegram_invitation(code, user_id, user_name):
    """Valide un code d'invitation, et si valide, ajoute l'utilisateur à la config."""
    invitations = load_invitations()
    
    if code not in invitations:
        return {"success": False, "message": "Code d'invitation invalide."}

    invitation = invitations[code]
    
    # Vérifier si le code est expiré
    if datetime.fromisoformat(invitation['expires_at']) < datetime.now():
        return {"success": False, "message": "Ce code d'invitation a expiré."}

    # Vérifier si le code a déjà été utilisé
    if invitation.get('used_by_user_id'):
        # Si c'est le même utilisateur qui réutilise le code, on l'autorise
        if invitation['used_by_user_id'] == user_id:
            return {"success": True, "message": "Vous êtes déjà autorisé. Envoyez-moi une photo !"}
        else:
            return {"success": False, "message": "Ce code d'invitation a déjà été utilisé."}

    # Si le code est valide et non utilisé, on ajoute l'utilisateur à la liste des invités
    add_telegram_guest_user(user_id, invitation['guest_name'])

    # Marquer l'invitation comme utilisée
    invitation['used_by_user_id'] = user_id
    invitation['used_by_user_name'] = user_name
    invitation['used_at'] = datetime.now().isoformat()
    save_invitations(invitations)

    return {"success": True, "message": f"Félicitations {invitation['guest_name']} ! Vous pouvez maintenant envoyer des cartes postales au cadre."}

@app.route('/api/telegram/invitations/<code>/revoke', methods=['POST'])
@login_required
def revoke_telegram_invitation(code):
    """Révoque l'accès d'un utilisateur en dissociant son ID de l'invitation."""
    invitations = load_invitations()
    if code not in invitations:
        return jsonify({"success": False, "message": "Invitation non trouvée."}), 404

    # Récupérer le nom de l'utilisateur avant de le supprimer pour le message de confirmation
    guest_name = invitations[code].get('used_by_user_name', 'Utilisateur inconnu')

    # Révoquer l'accès en remettant les champs 'used_by' à null
    invitations[code]['used_by_user_id'] = None
    invitations[code]['used_by_user_name'] = None
    invitations[code]['used_at'] = None

    # --- IMPORTANT ---
    # L'invitation redevient "utilisable" mais conserve sa date d'expiration d'origine.
    # Si vous souhaitez que la révocation soit définitive, vous pouvez supprimer l'invitation :
    # del invitations[code]
    # Ou la marquer comme révoquée :
    # invitations[code]['status'] = 'revoked'
    # Pour l'instant, nous la rendons simplement réutilisable.

    save_invitations(invitations)
    
    flash(_("L'accès pour l'invité '%(name)s' a été révoqué.", name=guest_name), "success")
    return jsonify({"success": True, "message": "Accès révoqué."})

@app.route('/api/telegram/bot_info')
@login_required
def get_telegram_bot_info():
    """Récupère le nom d'utilisateur du bot Telegram configuré."""
    config = load_config()
    token = config.get("telegram_bot_token")

    if not token:
        return jsonify({"success": False, "message": "Le token du bot Telegram n'est pas configuré."})

    url = f"https://api.telegram.org/bot{token}/getMe"

    try:
        response = requests.get(url, timeout=10)
        response_data = response.json()

        if response.status_code == 200 and response_data.get("ok"):
            bot_username = response_data.get("result", {}).get("username")
            if bot_username:
                return jsonify({"success": True, "username": bot_username})
            else:
                return jsonify({"success": False, "message": "Le bot n'a pas de nom d'utilisateur ou le token est incorrect."})
        else:
            error_description = response_data.get('description', 'Réponse invalide de Telegram.')
            return jsonify({"success": False, "message": f"Échec de la récupération des infos du bot : {error_description}"})
    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "message": f"Erreur de connexion à l'API Telegram : {e}"})


# --- Routes principales ---

@app.route('/upload', methods=['GET'])
def upload_page():
    """Affiche la page publique pour envoyer des photos."""
    return render_template('upload.html')

@app.route('/handle_upload', methods=['POST'])
def handle_upload():
    """Gère la réception des fichiers depuis la page publique."""
    if 'photos' not in request.files:
        flash(_("Aucun fichier sélectionné."), "error")
        return redirect(url_for('upload_page'))

    files = request.files.getlist('photos')
    if not files or files[0].filename == '':
        flash(_("Aucun fichier sélectionné."), "error")
        return redirect(url_for('upload_page'))

    PENDING_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    
    count = 0
    for file in files:
        if file:
            # Sécuriser le nom du fichier
            filename = secure_filename(file.filename)
            # Gérer les collisions de noms en ajoutant un timestamp et une chaîne aléatoire
            base, ext = os.path.splitext(filename)
            unique_suffix = f"{int(time.time())}_{secrets.token_hex(2)}"
            final_path = PENDING_UPLOADS_DIR / f"{base}_{unique_suffix}{ext}"
            file.save(final_path)
            print(f"[Upload] Nouveau fichier reçu de l'invité et en attente : {final_path.name}")
            count += 1

    flash(_('%(count)s photo(s) envoyée(s) pour validation avec succès !', count=count), "success")
    return redirect(url_for('upload_page'))

@app.route('/api/get_pending_photos')
@login_required
def get_pending_photos():
    """Retourne la liste des photos en attente de validation."""
    try:
        # S'assurer que le dossier existe pour éviter les erreurs.
        if not PENDING_UPLOADS_DIR.exists():
            PENDING_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

        print(f"[DEBUG] Listing pending photos in: {PENDING_UPLOADS_DIR}")

        # Lister les fichiers dans le dossier des uploads en attente.
        files_with_mtime = []
        for f in PENDING_UPLOADS_DIR.iterdir():
            if f.is_file() and not f.name.startswith('.'): # Ignorer les fichiers cachés
                try:
                    files_with_mtime.append((f.name, f.stat().st_mtime))
                except OSError as e:
                    print(f"[DEBUG] Error reading file {f.name}: {e}")

        # Trier par date de modification (le plus récent en premier)
        files_with_mtime.sort(key=lambda x: x[1], reverse=True)
        pending_files = [f[0] for f in files_with_mtime]
        
        print(f"[DEBUG] Found {len(pending_files)} pending photos.")

        # Retourner une réponse structurée et ajouter des en-têtes anti-cache.
        response = jsonify({"success": True, "photos": pending_files})
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        print(f"[ERROR] get_pending_photos failed: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500

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
        # Utiliser un dossier spécifique 'invités' pour éviter de mélanger ou supprimer d'autres photos
        target_source = "invités"
        source_dir = BASE_DIR / "static" / "photos" / target_source
        source_dir.mkdir(parents=True, exist_ok=True)

        # Copier la photo pour la traiter
        shutil.copy(str(pending_path), str(source_dir / pending_path.name))

        # Lancer la préparation
        config = load_config()
        screen_width, screen_height = config.get("display_width", 1920), config.get("display_height", 1080)
        try:
            preparation_successful = False
            # Utiliser la fonction importée correcte et la source 'guests'
            for update in prepare_all_photos_with_progress(screen_width, screen_height, source_type=target_source):
                # On vérifie si la préparation s'est terminée avec succès en lisant le flux d'événements
                if update.get("type") == "done":
                    preparation_successful = True
            
            if preparation_successful:
                pending_path.unlink() # Supprimer l'original seulement si tout s'est bien passé

                # --- NOUVEAU: Activer automatiquement la source 'invites' si elle ne l'est pas ---
                # Cela garantit que la photo validée sera bien diffusée par le diaporama.
                current_sources = config.get('display_sources', [])
                if 'invités' not in current_sources:
                    current_sources.append('invités')
                    config['display_sources'] = current_sources
                    save_config(config)

                # Redémarrer le diaporama pour inclure la nouvelle photo immédiatement
                if is_slideshow_running():
                    restart_slideshow_for_update()

                return jsonify({"success": True, "message": "Photo approuvée et préparée. Le diaporama a été mis à jour."})
            else:
                return jsonify({"success": False, "message": "La préparation de la photo a échoué. La photo reste en attente."}), 500
        except Exception as e:
            return jsonify({"success": False, "message": f"Erreur lors de la préparation: {e}"}), 500

    return jsonify({"success": False, "message": "Action inconnue."}), 400

@app.route('/debug/pending')
@login_required
def debug_pending():
    """Route de diagnostic pour voir les fichiers bruts."""
    if not PENDING_UPLOADS_DIR.exists():
        return f"Le dossier {PENDING_UPLOADS_DIR} n'existe pas."
    files = [f.name for f in PENDING_UPLOADS_DIR.iterdir()]
    return f"Fichiers dans le dossier d'attente : {files}"

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username and password and check_credentials(username, password):
            session['logged_in'] = True
            flash(_("Connexion réussie"), "success")
            return redirect(url_for('configure'))
        else:
            flash(_("Identifiants invalides"), "error")
    return render_template('login.html')

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('logged_in', None)
    flash(_("Déconnexion réussie"), "success")
    return redirect(url_for('login'))


# --- Configuration & gestion diaporama ---

@app.route('/configure', methods=['GET', 'POST'])
@login_required
def configure():
    # --- DEBUG: Vérifier les fichiers en attente au chargement de la page ---
    try:
        if PENDING_UPLOADS_DIR.exists():
            pending_files = [f.name for f in PENDING_UPLOADS_DIR.iterdir() if f.is_file() and not f.name.startswith('.')]
            print(f"[Configure] Chargement de la page. {len(pending_files)} photo(s) en attente dans {PENDING_UPLOADS_DIR}: {pending_files}")
        else:
            print(f"[Configure] Le dossier {PENDING_UPLOADS_DIR} n'existe pas encore.")
    except Exception as e:
        print(f"[Configure] Erreur lors du listage des fichiers en attente : {e}")

    config = load_config()
    invitations = load_invitations()

    # Récupérer la liste des photos en attente pour le template
    pending_photos_list = []
    if PENDING_UPLOADS_DIR.exists():
        pending_photos_list = sorted(
            [f.name for f in PENDING_UPLOADS_DIR.iterdir() if f.is_file() and not f.name.startswith('.')],
            key=lambda p: os.path.getmtime(PENDING_UPLOADS_DIR / p),
            reverse=True
        )

    if request.method == 'POST':
        # Gérer le champ 'source' qui correspond à 'photo_source' dans le config
        if 'source' in request.form:
            config['photo_source'] = request.form.get('source')

        # --- NOUVEAU: Gérer la limite de photos pour Immich ---
        if 'max_photos_to_download_immich' in request.form:
            try:
                # S'assurer que le dictionnaire imbriqué existe
                if 'max_photos_to_download' not in config or not isinstance(config['max_photos_to_download'], dict):
                    config['max_photos_to_download'] = {}
                
                value = request.form.get('max_photos_to_download_immich')
                
                # On stocke un entier. 0, -1 ou vide signifie "illimité" pour le script de téléchargement.
                if value is None or value.strip() in ("", "0", "-1"):
                    config['max_photos_to_download']['immich'] = 0
                else:
                    config['max_photos_to_download']['immich'] = int(value)
            except (ValueError, TypeError):
                flash(_("La valeur pour la limite de photos Immich est invalide. La valeur précédente est conservée."), "warning")

        for key in [
            'immich_url', 'immich_token', 'album_name',
            'display_duration', 'active_start', 'active_end',
            'screen_height_percent', 'clock_font_size', 'clock_color',
            'clock_format', 'clock_offset_x', 'clock_offset_y',
            'clock_background_color',
            'clock_outline_color', 'clock_font_path', 'clock_position',
            'display_width', 'display_height', # Ajout des nouvelles clés
            'transition_enabled', # Added transition_enabled
            'transition_type', 'home_assistant_token', # Added transition_type
            'transition_duration', # Added transition_duration
            'pan_zoom_factor', 'favorite_boost_factor',
            'immich_update_interval_hours', 'date_format', 
            'weather_api_key', 'weather_city', 'weather_units', 'weather_update_interval_minutes',
            'smart_plug_on_url', 'smart_plug_off_url', 'smart_plug_on_delay',
            'smb_host', 'smb_share', 'smb_path', 'smb_user', 'smb_password', 'video_audio_output', 'video_audio_volume', 'telegram_boost_duration_days',
            'telegram_boost_factor',
            'smb_update_interval_hours'
            # New fields
            , 'wifi_ssid', 'wifi_password', 'info_display_duration', 'telegram_bot_token',
            'telegram_authorized_users', 'voice_control_language',
            'voice_control_engine', 'skip_initial_auto_import',
            'tide_latitude', 'tide_longitude', 'stormglass_api_key', 'tide_offset_x', 'tide_offset_y', 'notification_sound_volume'
        ]: 
            if key in request.form:
                value = request.form.get(key)
                # Gérer les champs numériques
                if key in ['display_duration', 'clock_offset_x', 'clock_offset_y', 'clock_font_size', 'weather_update_interval_minutes', 'immich_update_interval_hours', 'smb_update_interval_hours', 'display_width', 'display_height', 'info_display_duration', 'tide_offset_x', 'tide_offset_y', 'video_audio_volume', 'favorite_boost_factor', 'telegram_boost_duration_days', 'telegram_boost_factor']: # Integer fields
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
        config["smart_plug_enabled"] = 'smart_plug_enabled' in request.form
        config["transition_enabled"] = 'transition_enabled' in request.form # New checkbox handling
        config["clock_background_enabled"] = 'clock_background_enabled' in request.form
        config["video_audio_enabled"] = 'video_audio_enabled' in request.form
        config["video_hwdec_enabled"] = 'video_hwdec_enabled' in request.form

        config["telegram_boost_enabled"] = 'telegram_boost_enabled' in request.form
        # Traitement des checkboxes
        config["show_clock"] = 'show_clock' in request.form
        config["immich_auto_update"] = 'immich_auto_update' in request.form
        config["smb_auto_update"] = 'smb_auto_update' in request.form

        config["telegram_bot_enabled"] = 'telegram_bot_enabled' in request.form # 'telegram_enabled' is removed
        config["show_date"] = 'show_date' in request.form
        config["show_weather"] = 'show_weather' in request.form
        config["show_tides"] = 'show_tides' in request.form
        # La gestion de l'activation/désactivation du contrôle vocal se fait maintenant via une API dédiée
        # mais il faut aussi sauvegarder son état ici pour la persistance au redémarrage.
        config['voice_control_enabled'] = 'voice_control_enabled' in request.form
        # pour éviter les conflits avec le bouton "Enregistrer".
        if 'porcupine_access_key' in request.form:
            config['porcupine_access_key'] = request.form['porcupine_access_key']
        if 'voice_control_device_index' in request.form:
            config['voice_control_device_index'] = request.form['voice_control_device_index']

        save_config(config)
        restart_slideshow_process() # Redémarre uniquement le processus du diaporama
        flash(_("Configuration enregistrée. Le diaporama a été relancé pour appliquer les changements."), "success")
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

    prepared_media_by_source = get_prepared_photos_by_source()

    # --- NOUVEAU: Créer une liste plate des favoris pour le nouvel onglet ---
    favorite_photos = []
    for source, media_list in prepared_media_by_source.items():
        for media in media_list:
            if media.get('is_favorite'):
                favorite_photos.append(media)

    return render_template(
        'configure.html',
        config=config,
        prepared_photos_by_source=prepared_media_by_source, # Le template utilise ce nom de variable
        favorite_photos=favorite_photos, # Nouvelle variable pour l'onglet des favoris
        slideshow_running=slideshow_running,
        invitations=invitations,
        pending_photos=pending_photos_list
    )

@app.route("/import-usb")
@login_required
def import_usb():
    # Nettoyer le drapeau d'annulation avant de commencer
    cancel_flag = Path('/tmp/pimmich_cancel_import.flag')
    if cancel_flag.exists(): cancel_flag.unlink()

    @stream_with_context
    def generate():
        def stream_event(data):
            """Formate les données en événement Server-Sent Event (SSE)."""
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        try:
            for update in import_usb_photos():
                yield stream_event(update)
        except Exception as e:
            yield stream_event({"type": "error", "message": f"Erreur critique : {str(e)}"})

    return Response(generate(), mimetype='text/event-stream', headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})

@app.route("/import-immich")
@login_required
def import_immich():
    # Nettoyer le drapeau d'annulation avant de commencer
    cancel_flag = Path('/tmp/pimmich_cancel_import.flag')
    if cancel_flag.exists(): cancel_flag.unlink()

    config = load_config()
    @stream_with_context
    def generate():
        def stream_event(data):
            """Formate les données en événement Server-Sent Event (SSE)."""
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        try:
            for update in download_and_extract_album(config):
                yield stream_event(update)
        except Exception as e:
            yield stream_event({"type": "error", "message": f"Erreur critique : {str(e)}"})

    return Response(generate(), mimetype='text/event-stream', headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})

@app.route("/import-samba")
@login_required
def import_samba():
    # Nettoyer le drapeau d'annulation avant de commencer
    cancel_flag = Path('/tmp/pimmich_cancel_import.flag')
    if cancel_flag.exists(): cancel_flag.unlink()

    config = load_config()
    @stream_with_context
    def generate():
        def stream_event(data):
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        try:
            for update in import_samba_photos(config):
                yield stream_event(update)
        except Exception as e:
            yield stream_event({"type": "error", "message": f"Erreur critique : {str(e)}"})

    return Response(generate(), mimetype='text/event-stream', headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})

@app.route("/import-smartphone", methods=['POST'])
@login_required
def import_smartphone():
    # Nettoyer le drapeau d'annulation avant de commencer
    cancel_flag = Path('/tmp/pimmich_cancel_import.flag')
    if cancel_flag.exists(): cancel_flag.unlink()

    """
    Gère l'upload de photos depuis un smartphone via un formulaire web.
    """
    @stream_with_context
    def generate():
        def stream_event(data):
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        config = load_config()
        screen_width, screen_height = config.get("display_width", 1920), config.get("display_height", 1080)
        source_dir = BASE_DIR / "static" / "photos" / "smartphone"

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
            for update in prepare_all_photos_with_progress(screen_width, screen_height, source_type="smartphone"):
                yield stream_event(update)

        except Exception as e:
            print(f"[Import Smartphone] Erreur : {e}")
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

@app.route('/prepare-photos')
@login_required
def prepare_photos():
    # Nettoyer le drapeau d'annulation avant de commencer
    cancel_flag = Path('/tmp/pimmich_cancel_import.flag')
    if cancel_flag.exists(): cancel_flag.unlink()

    """
    Route pour lancer la préparation des photos pour une source donnée.
    Utilise Server-Sent Events (SSE) pour streamer le progrès.
    """
    source = request.args.get('source')
    if not source:
        def error_stream():
            error_update = {"type": "error", "message": "Le paramètre 'source' est manquant."}
            yield f"data: {json.dumps(error_update)}\n\n"
        return Response(stream_with_context(error_stream()), mimetype='text/event-stream')

    def generate_preparation_stream():
        """Générateur qui produit les événements de progression."""
        try:
            config = load_config()
            screen_width = config.get('display_width')
            screen_height = config.get('display_height')

            # --- NOUVELLE LOGIQUE DE FUSION DES LÉGENDES ---
            # On centralise ici la préparation des légendes pour donner la priorité
            # au texte saisi manuellement dans Pimmich.

            # 1. Charger les descriptions de base (ex: depuis le cache Immich)
            base_description_map = {}
            if source == "immich":
                immich_cache_path = Path("cache") / "immich_description_map.json"
                if immich_cache_path.exists():
                    try:
                        with open(immich_cache_path, 'r', encoding='utf-8') as f:
                            base_description_map = json.load(f)
                    except Exception as e:
                        print(f"[App] Avertissement: Impossible de charger le cache de description Immich: {e}")

            # 2. Charger les légendes manuelles de Pimmich
            manual_captions = load_text_states()

            # 3. Fusionner, en donnant la priorité aux légendes manuelles
            final_caption_map = base_description_map.copy()
            for path, caption in manual_captions.items():
                # La clé est 'source/fichier.jpg', on extrait juste le nom du fichier
                filename = Path(path).name
                final_caption_map[filename] = caption

            # Lancer la préparation et streamer les mises à jour.
            for update in prepare_all_photos_with_progress(screen_width, screen_height, source_type=source, description_map=final_caption_map):
                # Ajouter le chemin de l'image source à l'événement pour l'affichage en direct
                if update.get("current_photo_path"):
                    update["current_photo_url"] = url_for('static', filename=f"photos/{source}/{update['current_photo_path']}")
                
                yield f"data: {json.dumps(update, ensure_ascii=False)}\n\n"
        except Exception as e:
            error_update = {"type": "error", "message": f"Erreur serveur lors de la préparation : {str(e)}"}
            yield f"data: {json.dumps(error_update)}\n\n"

    return Response(stream_with_context(generate_preparation_stream()), mimetype='text/event-stream', headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})

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

@app.route('/api/test_smart_plug', methods=['POST'])
@login_required
def test_smart_plug():
    """Teste une URL de prise connectée."""
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"success": False, "message": "L'URL est requise."})

    try:
        # Utiliser un timeout court pour ne pas bloquer l'interface
        response = requests.post(url, timeout=5)
        if 200 <= response.status_code < 300:
            return jsonify({"success": True, "message": f"Succès ! La prise a répondu avec le code {response.status_code}."})
        else:
            return jsonify({"success": False, "message": f"Échec. La prise a répondu avec une erreur : {response.status_code}."})
    except requests.exceptions.Timeout:
        return jsonify({"success": False, "message": "Échec. La requête a expiré (timeout). Vérifiez l'adresse IP de la prise."})
    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "message": f"Échec. Erreur de connexion : {e}"})

@app.route('/test-telegram', methods=['POST'])
@login_required
def test_telegram():
    """Teste si le token du bot Telegram est valide en appelant la méthode getMe."""
    data = request.get_json()
    token = data.get("token")

    if not token:
        return jsonify({"success": False, "message": _("Le token du bot est requis.")})

    url = f"https://api.telegram.org/bot{token}/getMe"

    try:
        response = requests.get(url, timeout=10)
        response_data = response.json()

        if response.status_code == 200 and response_data.get("ok"):
            bot_name = response_data.get("result", {}).get("first_name", "Inconnu")
            return jsonify({"success": True, "message": _("Token valide ! Le bot s'appelle '%(bot_name)s'.", bot_name=bot_name)})
        else:
            error_description = response_data.get('description', 'Réponse invalide de Telegram.')
            return jsonify({"success": False, "message": _("Échec de l'envoi : %(error)s", error=error_description)})
    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "message": _("Erreur de connexion : %(error)s", error=str(e))})

@app.route('/api/force_tide_update', methods=['POST'])
@login_required
def force_tide_update():
    """Force la mise à jour des données de marée en appelant l'API et en écrivant dans le cache."""
    config = load_config()
    api_key = config.get("stormglass_api_key")
    lat = config.get("tide_latitude")
    lon = config.get("tide_longitude")
    tide_cache_path = Path('cache/tides.json')

    if not all([api_key, lat, lon]):
        return jsonify({"success": False, "message": "Configuration StormGlass incomplète."})

    try:
        start_time_utc = datetime.utcnow()
        # --- MODIFICATION: Récupérer 7 jours de données pour être cohérent avec le slideshow ---
        end_time_utc = start_time_utc + timedelta(days=7)

        headers = {'Authorization': api_key}
        params = {'lat': lat, 'lng': lon, 'start': start_time_utc.isoformat(), 'end': end_time_utc.isoformat()}
        
        response = requests.get('https://api.stormglass.io/v2/tide/extremes/point', params=params, headers=headers, timeout=15)
        response.raise_for_status()
        
        extremes_data = response.json().get('data', [])
        now_utc = datetime.utcnow().replace(tzinfo=None)
        future_extremes = [e for e in extremes_data if datetime.fromisoformat(e['time'].replace('Z', '+00:00')).replace(tzinfo=None) > now_utc]

        if not future_extremes:
            return jsonify({"success": False, "message": "Aucune marée future trouvée par l'API."})

        # --- CORRECTION: Sauvegarder la liste complète des marées futures, pas juste les deux prochaines ---
        data_to_cache = {'data': future_extremes, 'timestamp': datetime.now().isoformat()}
        
        tide_cache_path.parent.mkdir(exist_ok=True)
        with open(tide_cache_path, 'w') as f:
            json.dump(data_to_cache, f, indent=2)

        return jsonify({"success": True, "message": "Données de marée mises à jour avec succès !"})

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 402:
            # --- AMÉLIORATION: Écrire un état de cooldown dans le cache ---
            cooldown_data = {'data': [], 'timestamp': datetime.now().isoformat(), 'cooldown': True}
            try:
                with open(tide_cache_path, 'w') as f: json.dump(cooldown_data, f, indent=2)
            except Exception: pass
            return jsonify({"success": False, "message": "Quota API StormGlass dépassé."})
        return jsonify({"success": False, "message": f"Erreur API ({e.response.status_code})."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur inattendue : {e}"})


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

@app.route('/telegram_update_status')
@login_required
def telegram_update_status():
    """Retourne l'état actuel du worker du bot Telegram."""
    return jsonify(telegram_status_manager.get_status())

@app.route('/telegram_bot_status')
@login_required
def telegram_bot_status():
    """Retourne un état simplifié du bot Telegram pour l'interface, avec un statut pour la couleur."""
    status_data = telegram_status_manager.get_status()
    message = status_data.get("status_message", "Inconnu")
    
    status = "unknown" # Statut par défaut
    msg_lower = message.lower()

    if "actif" in msg_lower:
        status = "running"
    elif "désactivé" in msg_lower or "non configuré" in msg_lower:
        status = "stopped"
    elif "erreur" in msg_lower:
        status = "error"
        
    return jsonify({
        "status": status,
        "status_message": message
    })

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

def schedule_worker():
    """
    Thread en arrière-plan qui gère le démarrage et l'arrêt du diaporama
    en fonction des heures d'activité configurées.
    """
    logging.info("== Démarrage du worker de planification du diaporama ==")
    
    # --- Séquence de démarrage unique ---
    # Cette partie ne s'exécute qu'une seule fois au lancement de l'application.
    try:
        logging.info("[Scheduler] Séquence de démarrage initiale.")
        # Attendre que le système soit stable avant de manipuler l'affichage
        time.sleep(5)
        config = load_config()
        output_name = get_display_output_name()
        if output_name:
            width = config.get('display_width', 1920)
            height = config.get('display_height', 1080)
            logging.info(f"[Scheduler] Forçage de la résolution {width}x{height} sur l'écran '{output_name}' au démarrage.")
            try:
                subprocess.run(['swaymsg', 'output', output_name, 'mode', f'{width}x{height}'], check=True, timeout=10)
                time.sleep(2) # Laisser le temps à l'écran de se stabiliser
            except Exception as e:
                logging.error(f"[Scheduler] Échec du forçage de la résolution au démarrage : {e}")
        
        # Démarrer le diaporama si on est dans les heures actives au lancement de l'app
        start_str = config.get("active_start", "07:00")
        end_str = config.get("active_end", "22:00")
        now_time = datetime.now().time()
        start_time = datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.strptime(end_str, "%H:%M").time()
        in_schedule_at_boot = (start_time <= end_time and start_time <= now_time <= end_time) or \
                              (start_time > end_time and (now_time >= start_time or now_time <= end_time))
        
        if in_schedule_at_boot:
            logging.info("[Scheduler] Heures actives au démarrage, lancement du diaporama.")
            start_slideshow()
    except Exception as e:
        logging.error(f"[Scheduler] Erreur critique dans la séquence de démarrage : {e}", exc_info=True)

    while True:
        try:
            config = load_config()
            start_str = config.get("active_start", "07:00")
            end_str = config.get("active_end", "22:00")

            now_time = datetime.now().time()
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()

            if start_time <= end_time:
                in_schedule = start_time <= now_time <= end_time
            else:
                in_schedule = now_time >= start_time or now_time <= end_time

            slideshow_is_running = is_slideshow_running()

            if not in_schedule and slideshow_is_running:
                logging.info("[Scheduler] Heure inactive détectée et diaporama en cours. Arrêt...")
                stop_slideshow()
            elif in_schedule and not slideshow_is_running:
                logging.info("[Scheduler] Heure active et diaporama arrêté. Séquence de démarrage...")
                # 1. On s'assure que l'écran est allumé (via DPMS si pas de prise)
                set_display_power(on=True)
                # 2. On attend un court instant pour laisser l'environnement d'affichage se stabiliser
                time.sleep(2)
                # 3. On lance explicitement le diaporama
                start_slideshow()

        except Exception as e:
            logging.error(f"[Scheduler] Erreur dans le worker de planification : {e}", exc_info=True)

        # Attendre 60 secondes avant la prochaine vérification
        time.sleep(60)

def immich_update_worker():
    """
    Thread en arrière-plan qui vérifie et met à jour l'album Immich périodiquement.
    """
    logging.info("== Démarrage du worker de mise à jour automatique Immich ==")
    while True:
        config = load_config()
        is_enabled = config.get("immich_auto_update", False)
        interval_hours = config.get("immich_update_interval_hours", 24)
        skip_initial = config.get("skip_initial_auto_import", False) # New config option

        global _immich_first_run_skipped
        if not _immich_first_run_skipped and skip_initial:
            logging.info("[Auto-Update Immich] Import initial skipped as per configuration.")
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
            logging.info(f"[Auto-Update Immich] {status_msg}")
            immich_status_manager.update_status(message=status_msg)
            
            try:
                immich_status_manager.update_status(message="Lancement du téléchargement...")
                logging.info("[Auto-Update Immich] Lancement du téléchargement et de la préparation...")
                
                # Étape 1: Téléchargement
                download_success = False
                description_map = {} # Initialiser un mappage vide
                for update in download_and_extract_album(config):
                    # NOUVEAU: Afficher les messages de progression du worker dans les logs pour le débogage
                    if update.get("message"):
                        logging.info(f"[Auto-Update Immich] {update.get('message')}")

                    if update.get("type") == "error":
                        logging.error(f"[Auto-Update Immich] Erreur lors du téléchargement : {update.get('message')}")
                        immich_status_manager.update_status(message=f"Erreur téléchargement: {update.get('message')}")
                    immich_status_manager.update_status(message=update.get('message', '')) # Update status with download message
                    if update.get("type") == "done":
                        download_success = True
                        description_map = update.get("description_map", {}) # Récupérer le mappage

                # Étape 2: Préparation et redémarrage du diaporama
                if download_success:
                    # Fusionner les descriptions d'Immich et celles de l'interface Pimmich
                    manual_captions = load_text_states()
                    final_description_map = description_map.copy()
                    # Les légendes manuelles (clés "source/fichier.jpg") écrasent celles d'Immich (clés "fichier.jpg")
                    for path, caption in manual_captions.items():
                        path_obj = Path(path)
                        if path_obj.parts and path_obj.parts[0] == "immich":
                            filename = path_obj.name
                            final_description_map[filename] = caption

                    immich_status_manager.update_status(message="Préparation des photos...")
                    screen_width = config.get("display_width", 1920) # Utiliser la résolution configurée
                    screen_height = config.get("display_height", 1080) # Utiliser la résolution configurée
                    prep_successful = False
                    for update in prepare_all_photos_with_progress(screen_width=screen_width, screen_height=screen_height, source_type="immich", description_map=final_description_map):
                        immich_status_manager.update_status(message=update.get('message', '')) # Update status with preparation message
                        if update.get("type") == "error":
                            logging.error(f"[Auto-Update Immich] Erreur lors de la préparation : {update.get('message')}")
                            immich_status_manager.update_status(message=f"Erreur préparation: {update.get('message')}")
                            break # Sortir de la boucle de préparation
                        if update.get("type") == "done":
                            prep_successful = True
                    
                    if prep_successful:
                        immich_status_manager.update_status(message="Mise à jour terminée. Redémarrage du diaporama...")
                        print("[Auto-Update] Mise à jour terminée avec succès. Redémarrage du diaporama.")
                        if is_slideshow_running():
                            restart_slideshow_for_update()
                        immich_status_manager.update_status(last_run=datetime.now(), message="Dernière mise à jour réussie.")
                    else:
                        immich_status_manager.update_status(message="Mise à jour terminée avec avertissements/erreurs.")

            except Exception as e:
                logging.error(f"[Auto-Update Immich] Erreur critique dans le worker : {e}", exc_info=True)
                immich_status_manager.update_status(message=f"Erreur critique : {e}")

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
                    samba_status_manager.update_status(message=update.get('message', '')) # Update status with import message
                    if update.get("type") == "done":
                        import_success = True

                if import_success:
                    samba_status_manager.update_status(message="Préparation des photos...")
                    # Charger les légendes manuelles pour Samba
                    manual_captions = load_text_states()
                    final_description_map = {}
                    for path, caption in manual_captions.items():
                        path_obj = Path(path)
                        if path_obj.parts and path_obj.parts[0] == "samba":
                            filename = path_obj.name
                            final_description_map[filename] = caption

                    screen_width = config.get("display_width", 1920) # Utiliser la résolution configurée
                    screen_height = config.get("display_height", 1080) # Utiliser la résolution configurée
                    prep_successful = False
                    for update in prepare_all_photos_with_progress(screen_width, screen_height, "samba", description_map=final_description_map):
                        samba_status_manager.update_status(message=update.get('message', '')) # Update status with preparation message
                        if update.get("type") == "error":
                            samba_status_manager.update_status(message=f"Erreur préparation: {update.get('message')}")
                            break
                        if update.get("type") == "done":
                            prep_successful = True
                    
                    if prep_successful:
                        samba_status_manager.update_status(message="Mise à jour terminée. Redémarrage du diaporama...")
                        print("[Auto-Update Samba] Mise à jour terminée. Redémarrage du diaporama.")
                        if is_slideshow_running():
                            restart_slideshow_for_update()
                        samba_status_manager.update_status(last_run=datetime.now(), message="Dernière mise à jour réussie.")
                    else:
                        samba_status_manager.update_status(message="Mise à jour terminée avec avertissements/erreurs.")
            except Exception as e:
                logging.error(f"[Auto-Update Samba] Erreur critique dans le worker : {e}", exc_info=True)
                samba_status_manager.update_status(message=f"Erreur critique : {e}")
        else:
            samba_status_manager.update_status(message="Mise à jour automatique Samba désactivée.")
        
        sleep_seconds = (interval_hours * 3600) if is_enabled else (15 * 60)
        next_run_time = datetime.now() + timedelta(seconds=sleep_seconds)
        samba_status_manager.update_status(next_run=next_run_time) # Update next_run regardless of enabled state
        if is_enabled: # Only set message to "En attente..." if it's enabled
            samba_status_manager.update_status(message="En attente...")
        time.sleep(sleep_seconds)

def telegram_bot_worker():
    """
    Thread en arrière-plan qui lance et maintient le bot Telegram actif.
    """
    print("== Démarrage du worker du bot Telegram ==")
    while True: # Boucle pour relancer le bot en cas de crash
        config = load_config()
        is_enabled = config.get("telegram_bot_enabled", False)
        token = config.get("telegram_bot_token")
        users = config.get("telegram_authorized_users")
        # Charger les invités autorisés depuis leur propre fichier
        guest_users = load_telegram_guest_users()

        if is_enabled and token and users:
            try:
                # Créer et définir une nouvelle boucle d'événements pour ce thread.
                # C'est nécessaire car le bot Telegram est asynchrone et a besoin
                # d'une boucle pour fonctionner correctement en arrière-plan.
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                telegram_status_manager.update_status(message="Bot actif.")
                bot = PimmichBot(token, users, guest_users, handle_new_telegram_photo, validate_telegram_invitation)
                bot.run() # Cette fonction est bloquante (polling)
            except Exception as e:
                # Tentative de capture d'erreurs spécifiques pour un meilleur feedback
                error_str = str(e).lower()
                if 'invalid token' in error_str:
                    error_msg = "Erreur : Token du bot Telegram invalide."
                elif 'conflict' in error_str:
                    error_msg = "Erreur : Conflit, une autre instance du bot est peut-être déjà lancée."
                else:
                    error_msg = f"Erreur critique du bot : {str(e)[:100]}..."
                
                final_error_msg = f"{error_msg} Redémarrage dans 60s."
                print(f"[Telegram Worker] {final_error_msg}")
                telegram_status_manager.update_status(message=error_msg) # On affiche le message concis dans l'UI
        else:
            telegram_status_manager.update_status(message="Bot désactivé ou non configuré.")
        time.sleep(60) # Attendre avant de vérifier à nouveau la config ou de relancer
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
    all_media = [media for source_media in get_prepared_photos_by_source().values() for media in source_media]
    return render_template('slideshow_view.html', photos=all_media) # Le template s'attend probablement à une variable 'photos'

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
        # Le chemin relatif est de la forme 'source/nom_photo.jpg'
        photo_path_obj = Path('static/prepared') / photo
        
        # Déterminer les chemins des versions alternatives et de la sauvegarde
        polaroid_path = photo_path_obj.with_name(f"{photo_path_obj.stem}_polaroid.jpg")
        postcard_path = photo_path_obj.with_name(f"{photo_path_obj.stem}_postcard.jpg")
        backup_path = Path('static/.backups') / photo

        # Supprimer tous les fichiers associés
        if photo_path_obj.is_file():
            photo_path_obj.unlink()
        if polaroid_path.is_file():
            polaroid_path.unlink()
        if postcard_path.is_file():
            postcard_path.unlink()
        if backup_path.is_file():
            backup_path.unlink()
        
        # Supprimer l'état du filtre pour cette photo
        states = load_filter_states()
        if states.pop(photo, None):
            save_filter_states(states)

        # Supprimer des favoris si la photo y était
        favorites = load_favorites()
        if photo in favorites:
            favorites.remove(photo)
            save_favorites(favorites)

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

    prepared_dir = PREPARED_DIR / source_name
    backup_dir = BASE_DIR / 'static' / '.backups' / source_name

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

@app.route('/system_reboot', methods=['POST'])
@login_required
def system_reboot():
    """Affiche la page de redémarrage et lance le reboot après 1 seconde."""
    return render_template('rebooting.html')

@app.route('/api/trigger_reboot', methods=['POST'])
@login_required
def trigger_reboot():
    """Lance la commande de redémarrage système."""
    try:
        # Lancer le reboot en arrière-plan pour que la réponse HTTP puisse être envoyée
        import threading
        def delayed_reboot():
            time.sleep(1)  # Attendre 1 seconde pour que la page se charge
            os.system("sudo reboot")
        
        reboot_thread = threading.Thread(target=delayed_reboot)
        reboot_thread.daemon = True
        reboot_thread.start()
        
        return jsonify({"success": True, "message": "Redémarrage initié"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/ping', methods=['GET'])
def ping():
    """Endpoint simple pour vérifier que le serveur est disponible."""
    return jsonify({"status": "ok"})


@app.route('/restart_app', methods=['POST'])
@login_required
def restart_app():
    """Redémarre uniquement l'application web Flask."""
    # Code de sortie spécial pour indiquer au script shell de redémarrer l'application
    RESTART_EXIT_CODE = 42
    def do_restart():
        # Laisser le temps au navigateur de recevoir la réponse avant de tuer le processus
        time.sleep(2)
        print("[Restart] Redémarrage de l'application web demandé par l'utilisateur.")
        sys.exit(RESTART_EXIT_CODE)
        os._exit(RESTART_EXIT_CODE)

    # Lancer le redémarrage dans un thread pour ne pas bloquer la réponse HTTP
    restart_thread = threading.Thread(target=do_restart)
    restart_thread.start()
    
    flash(_("L'application web redémarre... La page sera inaccessible pendant quelques instants."), "success")
    return redirect(url_for('configure'))

@app.route('/api/slideshow/restart_for_update', methods=['POST'])
@login_required
def restart_slideshow_for_update_route():
    """Redémarre le diaporama pour une mise à jour de contenu, sans éteindre l'écran."""
    try:
        if is_slideshow_running():
            restart_slideshow_for_update()
        return jsonify({"success": True, "message": "Commande de redémarrage envoyée."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/cancel_import', methods=['POST'])
@login_required
def cancel_import():
    """Crée un fichier drapeau pour signaler l'annulation aux processus d'import/préparation."""
    try:
        Path('/tmp/pimmich_cancel_import.flag').touch()
        return jsonify({"success": True, "message": "Signal d'annulation envoyé."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/playlists/play', methods=['POST'])
def play_playlist():
    # Sécurité : n'accepter que les requêtes venant de la machine elle-même (contrôle vocal) ou d'un utilisateur connecté
    if not session.get('logged_in') and request.remote_addr != '127.0.0.1':
        return jsonify({"success": False, "message": "Accès non autorisé."}), 403

    data = request.get_json()
    playlist_id = data.get('id')
    if not playlist_id:
        return jsonify({"success": False, "message": "ID de playlist manquant."}), 400

    try:
        playlists = load_playlists()
        target_playlist = next((p for p in playlists if p.get('id') == playlist_id), None)

        if not target_playlist:
            return jsonify({"success": False, "message": "Playlist non trouvée."}), 404

        if not target_playlist.get('photos'):
            return jsonify({"success": False, "message": "La playlist est vide."}), 400

        # CORRECTION : Créer un objet JSON avec le nom ET les photos
        playlist_data_to_save = {
            "name": target_playlist.get('name', 'Playlist'), # Utilise le nom, ou 'Playlist' par défaut
            "photos": target_playlist.get('photos', [])
        }

        # Écrire les données dans le fichier temporaire que le diaporama lira
        with open(CUSTOM_PLAYLIST_FILE, 'w') as f:
            json.dump(playlist_data_to_save, f)
        
        # Arrêter le diaporama actuel s'il est en cours
        if is_slideshow_running():
            stop_slideshow()
            time.sleep(1) # Laisser le temps au processus de se terminer
        
        # Démarrer le nouveau diaporama
        start_slideshow()
        
        return jsonify({"success": True, "message": f"Lancement du diaporama pour la playlist '{target_playlist.get('name')}'."})
    except Exception as e:
        print(f"Erreur lors du lancement de la playlist : {e}")
        return jsonify({"success": False, "message": "Erreur interne du serveur."}), 500

@app.route('/api/slideshow/restart_standard', methods=['POST'])
def restart_standard_slideshow():
    """Arrête tout diaporama en cours et en lance un nouveau en mode standard."""
    # Sécurité : n'accepter que les requêtes venant de la machine elle-même (contrôle vocal) ou d'un utilisateur connecté
    if not session.get('logged_in') and request.remote_addr != '127.0.0.1':
        return jsonify({"success": False, "message": "Accès non autorisé."}), 403

    try:
        # S'assurer que le fichier de playlist personnalisée est supprimé
        if os.path.exists(CUSTOM_PLAYLIST_FILE):
            os.remove(CUSTOM_PLAYLIST_FILE)
        
        if is_slideshow_running():
            stop_slideshow()
            time.sleep(1) # Laisser le temps au processus de se terminer
        
        start_slideshow()
        return jsonify({"success": True, "message": "Diaporama standard relancé."})
    except Exception as e:
        print(f"Erreur lors du redémarrage du diaporama standard : {e}")
        return jsonify({"success": False, "message": str(e)}), 500

# --- API pour la gestion des Playlists ---

@app.route('/api/playlists', methods=['GET'])
def get_playlists():
    """Retourne la liste de toutes les playlists."""
    playlists = load_playlists()
    return jsonify(playlists)

@app.route('/api/playlists', methods=['POST'])
@login_required
def create_playlist():
    """Crée une nouvelle playlist."""
    data = request.get_json()
    name = data.get('name')
    if not name or not name.strip():
        return jsonify({"success": False, "message": "Le nom de la playlist est requis."}), 400

    playlists = load_playlists()
    
    # Vérifier si une playlist avec le même nom existe déjà
    if any(p['name'].lower() == name.strip().lower() for p in playlists):
        return jsonify({"success": False, "message": "Une playlist avec ce nom existe déjà."}), 409

    new_playlist = {
        "id": secrets.token_hex(8),
        "name": name.strip(),
        "photos": []
    }
    playlists.append(new_playlist)
    save_playlists(playlists)
    return jsonify({"success": True, "playlist": new_playlist}), 201

@app.route('/api/playlists/<playlist_id>', methods=['DELETE'])
def delete_playlist(playlist_id):
    """Supprime une playlist."""
    playlists = load_playlists()
    playlists = [p for p in playlists if p.get('id') != playlist_id]
    save_playlists(playlists)
    return jsonify({"success": True})

@app.route('/api/playlists/<playlist_id>/rename', methods=['POST'])
def rename_playlist(playlist_id):
    """Renomme une playlist."""
    data = request.get_json()
    new_name = data.get('name')
    if not new_name or not new_name.strip():
        return jsonify({"success": False, "message": "Le nouveau nom ne peut pas être vide."}), 400

    playlists = load_playlists()
    
    if any(p['name'].lower() == new_name.strip().lower() and p.get('id') != playlist_id for p in playlists):
        return jsonify({"success": False, "message": "Une autre playlist avec ce nom existe déjà."}), 409

    found = False
    for playlist in playlists:
        if playlist.get('id') == playlist_id:
            playlist['name'] = new_name.strip()
            found = True
            break
    
    save_playlists(playlists)
    return jsonify({"success": True, "message": "Playlist renommée."})

@app.route('/api/playlists/<playlist_id>/photos', methods=['POST'])
def add_photo_to_playlist(playlist_id):
    """Ajoute une photo à une playlist."""
    data = request.get_json()
    photo_path = data.get('photo_path')
    if not photo_path:
        return jsonify({"success": False, "message": "Chemin de la photo manquant."}), 400

    playlists = load_playlists()
    for playlist in playlists:
        if playlist.get('id') == playlist_id:
            if photo_path not in playlist['photos']:
                playlist['photos'].append(photo_path)
            save_playlists(playlists)
            return jsonify({"success": True})
    return jsonify({"success": False, "message": "Playlist non trouvée."}), 404

@app.route('/api/playlists/<playlist_id>/photos/<path:photo_path>', methods=['DELETE'])
def remove_photo_from_playlist(playlist_id, photo_path):
    """Retire une photo d'une playlist."""
    playlists = load_playlists()
    for playlist in playlists:
        if playlist.get('id') == playlist_id:
            if photo_path in playlist['photos']:
                playlist['photos'].remove(photo_path)
            save_playlists(playlists)
            return jsonify({"success": True})
    return jsonify({"success": False, "message": "Playlist non trouvée."}), 404

@app.route('/api/playlists/<playlist_id>/reorder', methods=['POST'])
def reorder_playlist(playlist_id):
    """
    Réorganise les photos d'une playlist spécifique.
    Reçoit une liste de chemins de photos dans le nouvel ordre.
    """
    data = request.get_json()
    if not data or 'photos' not in data:
        return jsonify({"success": False, "message": "Données manquantes."}), 400

    new_photo_order = data['photos']

    try:
        playlists = load_playlists() 
        
        playlist_found = False
        for playlist in playlists:
            if playlist.get('id') == playlist_id:
                # Mesure de sécurité : on vérifie que le nouvel ordre contient
                # exactement les mêmes photos que l'ordre original, sans ajout ni suppression.
                original_photos_set = set(playlist['photos'])
                new_photos_set = set(new_photo_order)

                if original_photos_set != new_photos_set:
                     return jsonify({"success": False, "message": "Incohérence dans la liste des photos."}), 400

                playlist['photos'] = new_photo_order
                playlist_found = True
                break
        
        if not playlist_found:
            return jsonify({"success": False, "message": "Playlist non trouvée."}), 404

        save_playlists(playlists) 

        return jsonify({"success": True, "message": "Ordre de la playlist sauvegardé."})

    except Exception as e:
        print(f"Erreur lors de la réorganisation de la playlist : {e}")
        return jsonify({"success": False, "message": "Erreur interne du serveur."}), 500


@app.route('/api/audio_devices', methods=['GET'])
@login_required
def get_audio_devices():
    """Retourne la liste des périphériques d'entrée audio."""
    try:
        # L'importation peut échouer si les dépendances C (comme portaudio) sont manquantes
        import sounddevice as sd
        devices = sd.query_devices()
        input_devices = [
            {"index": i, "name": d['name'], "hostapi": sd.query_hostapis(d['hostapi'])['name']}
            for i, d in enumerate(devices) if d['max_input_channels'] > 0
        ]
        return jsonify({"success": True, "devices": input_devices})
    except Exception as e:
        # Renvoyer une erreur JSON claire au lieu de planter ou de renvoyer une liste vide.
        # Cela permet au frontend d'afficher un message d'erreur utile.
        error_message = f"Erreur API Audio: {type(e).__name__} - {e}"
        print(f"[ERROR] in get_audio_devices: {error_message}") # Log pour le débogage côté serveur
        return jsonify({"success": False, "message": error_message, "devices": []})

@app.route('/api/voice_control/status', methods=['GET'])
@login_required
def get_voice_control_status():
    status_file = 'logs/voice_control_status.json'
    if not is_voice_control_running():
        return jsonify({"status": "stopped", "message": _("Le service est arrêté.")})
    
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                return jsonify(json.load(f))
        except Exception as e:
            return jsonify({"status": "unknown", "message": f"Erreur lecture statut: {e}"})
    else:
        return jsonify({"status": "starting", "message": _("Démarrage du service...")})


@app.route('/api/audio_diagnostics', methods=['GET'])
@login_required
def get_audio_diagnostics():
    """Exécute des commandes de diagnostic audio et retourne le résultat."""
    diagnostics = {}
    try:
        # Commande lsusb pour lister les périphériques USB
        lsusb_result = subprocess.run(
            ['lsusb'], capture_output=True, text=True, check=False, timeout=5
        )
        diagnostics['lsusb'] = lsusb_result.stdout.strip() if lsusb_result.returncode == 0 else f"Erreur (code {lsusb_result.returncode}):\n{lsusb_result.stderr.strip()}"
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        diagnostics['lsusb'] = f"Erreur lors de l'exécution de 'lsusb': {e}"

    try:
        # Commande arecord -l pour lister les périphériques de capture audio
        arecord_result = subprocess.run(
            ['arecord', '-l'], capture_output=True, text=True, check=False, timeout=5
        )
        diagnostics['arecord'] = arecord_result.stdout.strip() if arecord_result.returncode == 0 else f"Erreur (code {arecord_result.returncode}):\n{arecord_result.stderr.strip()}"
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        diagnostics['arecord'] = f"Erreur lors de l'exécution de 'arecord -l': {e}"

    return jsonify({"success": True, "diagnostics": diagnostics})

# --- NOUVELLES ROUTES POUR LE CONTRÔLE VOCAL AVANCÉ ---

@app.route('/api/system/shutdown', methods=['POST'])
def system_shutdown():
    """Éteint le système."""
    # Sécurité : n'accepter que les requêtes venant de la machine elle-même
    if request.remote_addr != '127.0.0.1':
        return jsonify({"success": False, "message": "Accès non autorisé."}), 403
    print("Arrêt du système demandé via API.")
    subprocess.run(['sudo', 'shutdown', '-h', 'now'])
    return jsonify({"success": True, "message": "Arrêt en cours."})

@app.route('/api/display/power', methods=['POST'])
def display_power():
    """Allume ou éteint l'écran."""
    if request.remote_addr != '127.0.0.1':
        return jsonify({"success": False, "message": "Accès non autorisé."}), 403
    
    data = request.get_json()
    state = data.get('state') # 'on' or 'off'

    if state not in ['on', 'off']:
        return jsonify({"success": False, "message": "État invalide. Utilisez 'on' ou 'off'."}), 400

    # La logique est maintenant dans le slideshow_manager
    if state == 'on':
        if not is_slideshow_running():
            start_slideshow()
        success, message = True, "Commande de démarrage envoyée."
    else: # off
        if is_slideshow_running():
            stop_slideshow()
        success, message = True, "Commande d'arrêt envoyée."

    return jsonify({"success": success, "message": message})

@app.route('/api/sources/play/<source_name>', methods=['POST'])
def play_source_as_playlist(source_name):
    """Joue toutes les photos d'une source donnée comme une playlist."""
    if request.remote_addr != '127.0.0.1':
        return jsonify({"success": False, "message": "Accès non autorisé."}), 403

    source_dir = PREPARED_DIR / source_name
    if not source_dir.is_dir():
        return jsonify({"success": False, "message": f"La source '{source_name}' n'existe pas."}), 404

    photos = [
        f"{source_name}/{f.name}" for f in source_dir.iterdir() 
        if f.is_file() and not f.name.endswith(('_polaroid.jpg', '_thumbnail.jpg', '_postcard.jpg'))
    ]

    if not photos:
        return jsonify({"success": False, "message": f"La source '{source_name}' est vide."}), 400
    
    playlist_data = {"name": f"Source: {source_name.capitalize()}", "photos": photos}
    
    try:
        with open(CUSTOM_PLAYLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(playlist_data, f)
        
        stop_slideshow()
        time.sleep(1.5) # Donner un peu plus de temps pour l'arrêt
        start_slideshow()
        
        return jsonify({"success": True, "message": f"Lancement du diaporama pour la source '{source_name}'."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur lors du lancement de la playlist source: {e}"}), 500

@app.route('/api/sources/toggle', methods=['POST'])
def toggle_source():
    """Active ou désactive une source dans la configuration."""
    app.logger.info(f"API /api/sources/toggle reçue de {request.remote_addr}")
    if request.remote_addr != '127.0.0.1':
        app.logger.warning(f"Accès non autorisé à /api/sources/toggle de {request.remote_addr}")
        return jsonify({"success": False, "message": "Accès non autorisé."}), 403
        
    data = request.get_json()
    source_name = data.get('source')
    state = data.get('state') # 'on' or 'off'
    app.logger.info(f"Action demandée : '{state}' pour la source '{source_name}'")

    if not source_name or state not in ['on', 'off']:
        app.logger.error(f"Paramètres invalides reçus : source='{source_name}', state='{state}'")
        return jsonify({"success": False, "message": "Paramètres 'source' ou 'state' invalides."}), 400

    try:
        config = load_config()
        original_sources = config.get('display_sources', [])
        app.logger.info(f"Sources avant modification : {original_sources}")
        display_sources = set(original_sources)

        if state == 'on':
            display_sources.add(source_name)
            action_msg = "activée"
        else: # off
            display_sources.discard(source_name)
            action_msg = "désactivée"

        new_sources_list = sorted(list(display_sources))
        config['display_sources'] = new_sources_list
        app.logger.info(f"Sources après modification (avant sauvegarde) : {new_sources_list}")
        save_config(config)
        app.logger.info("Configuration sauvegardée avec succès dans config.json.")
        
        # Le diaporama détectera le changement automatiquement au prochain cycle.
        # Il n'est plus nécessaire de le redémarrer de force, ce qui causait le timeout.
        return jsonify({"success": True, "message": f"Source '{source_name}' {action_msg}. Le changement sera appliqué sur le diaporama."})
    except Exception as e:
        app.logger.error(f"Erreur dans la fonction toggle_source : {e}", exc_info=True)
        return jsonify({"success": False, "message": f"Erreur lors de la modification de la source : {e}"}), 500

@app.route('/api/slideshow/set_duration', methods=['POST'])
def set_slideshow_duration():
    """Modifie la durée d'affichage des photos et redémarre le diaporama."""
    # Sécurité : n'accepter que les requêtes venant de la machine elle-même
    if request.remote_addr != '127.0.0.1':
        return jsonify({"success": False, "message": "Accès non autorisé."}), 403
    
    data = request.get_json()
    duration = data.get('duration')

    if not isinstance(duration, int) or duration <= 0:
        return jsonify({"success": False, "message": "Durée invalide. Un entier positif est requis."}), 400

    try:
        config = load_config()
        config['display_duration'] = duration
        save_config(config)
        
        # Redémarrer le diaporama pour appliquer la nouvelle durée
        if is_slideshow_running():
            stop_slideshow()
            time.sleep(1) # Laisser le temps au processus de se terminer
        
        start_slideshow()
        
        return jsonify({"success": True, "message": f"Durée d'affichage réglée à {duration} secondes."})
    except Exception as e:
        app.logger.error(f"Erreur lors du changement de la durée d'affichage : {e}", exc_info=True)
        return jsonify({"success": False, "message": f"Erreur interne du serveur : {e}"}), 500

def _send_slideshow_signal(sig):
    """Helper function to send a signal to the slideshow process."""
    if not is_slideshow_running():
        return jsonify({"success": False, "message": "Le diaporama n'est pas en cours."}), 404
    try:
        with open("/tmp/pimmich_slideshow.pid", "r") as f:
            pid = int(f.read())
        os.kill(pid, sig)
        return jsonify({"success": True})
    except (FileNotFoundError, ValueError, ProcessLookupError) as e:
        return jsonify({"success": False, "message": f"Impossible de communiquer avec le diaporama : {e}"}), 500

@app.route('/api/slideshow/next', methods=['POST'])
def slideshow_next():
    return _send_slideshow_signal(signal.SIGUSR1)

@app.route('/api/slideshow/previous', methods=['POST'])
def slideshow_previous():
    return _send_slideshow_signal(signal.SIGUSR2)

@app.route('/api/slideshow/toggle_pause', methods=['POST'])
def slideshow_toggle_pause():
    return _send_slideshow_signal(signal.SIGTSTP)

@app.route('/api/slideshow/status')
def slideshow_status():
    if not is_slideshow_running():
        return jsonify({"running": False, "paused": False})
    try:
        with open("/tmp/pimmich_slideshow_status.json", "r") as f:
            status = json.load(f)
        return jsonify({"running": True, **status})
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify({"running": True, "paused": False}) # Assume not paused if file is missing

@app.route('/api/get_available_resolutions')
@login_required
def get_available_resolutions():
    """
    Récupère les résolutions disponibles pour la sortie d'affichage principale.
    """
    try:
        output_name = get_display_output_name()
        if not output_name:
            return jsonify({"success": False, "message": "Aucune sortie d'affichage principale trouvée."})

        result = subprocess.run(['swaymsg', '-t', 'get_outputs'], capture_output=True, text=True, check=True, env=os.environ)
        outputs = json.loads(result.stdout)

        resolutions = []
        for output in outputs:
            if output.get('name') == output_name and 'modes' in output:
                for mode in output['modes']:
                    resolutions.append({
                        "width": mode['width'],
                        "height": mode['height'],
                        "refresh": mode['refresh'] / 1000, # Convertir de mHz à Hz
                        "text": f"{mode['width']}x{mode['height']} @ {mode['refresh']/1000:.2f}Hz"
                    })
                # Inverser pour avoir les plus hautes résolutions en premier
                resolutions.reverse()
                return jsonify({"success": True, "resolutions": resolutions})

        return jsonify({"success": False, "message": "Aucun mode trouvé pour la sortie principale."})

    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur lors de la récupération des résolutions : {e}"})

@app.route('/api/set_resolution', methods=['POST'])
@login_required
def set_resolution():
    """
    Applique une nouvelle résolution à l'écran et la sauvegarde dans la configuration.
    """
    data = request.get_json()
    width = data.get('width')
    height = data.get('height')

    if not width or not height:
        return jsonify({"success": False, "message": "Largeur et hauteur requises."}), 400

    try:
        output_name = get_display_output_name()
        if not output_name:
            return jsonify({"success": False, "message": "Aucune sortie d'affichage à configurer."})

        # Appliquer la résolution via swaymsg
        subprocess.run(['swaymsg', 'output', output_name, 'resolution', f'{width}x{height}'], check=True)

        # Sauvegarder dans la configuration pour la persistance
        config = load_config()
        config['display_width'] = int(width)
        config['display_height'] = int(height)
        save_config(config)

        # Redémarrer le diaporama pour qu'il prenne en compte la nouvelle résolution
        if is_slideshow_running():
            stop_slideshow()
            start_slideshow()
            message = _("Résolution appliquée : %(width)sx%(height)s. Le diaporama a été redémarré.", width=width, height=height)
        else:
            message = _("Résolution appliquée : %(width)sx%(height)s. Le diaporama n'était pas en cours.", width=width, height=height)

        return jsonify({"success": True, "message": message})
    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur lors de l'application de la résolution : {e}"}), 500

@app.route('/api/smart_plug/status', methods=['GET'])
@login_required
def get_smart_plug_status():
    """
    Interroge l'URL de statut de la prise connectée et retourne son état.
    """
    config = load_config()
    if not config.get("smart_plug_enabled") or not config.get("smart_plug_status_url"):
        return jsonify({"status": "disabled", "message": "Le statut de la prise n'est pas configuré."})

    status_url = config.get("smart_plug_status_url")
    token = config.get("home_assistant_token") # Le nom de la clé dans la config est 'home_assistant_token'

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(status_url, headers=headers, timeout=5)
        response.raise_for_status() # Lève une exception pour les codes d'erreur HTTP (4xx ou 5xx)
        
        data = response.json()
        # Pour Home Assistant, l'état est dans la clé 'state'
        plug_state = data.get('state', 'unknown').lower()

        return jsonify({"status": plug_state, "message": f"État de la prise : {plug_state}"})

    except requests.exceptions.Timeout:
        return jsonify({"status": "unreachable", "message": "Timeout lors de la connexion à la prise."})
    except requests.exceptions.HTTPError as e:
        # Gérer spécifiquement les erreurs d'authentification pour un meilleur feedback
        if e.response.status_code == 401:
            return jsonify({"status": "error", "message": "Erreur 401: Non autorisé. Vérifiez votre token d'accès Home Assistant."})
        return jsonify({"status": "error", "message": f"Erreur HTTP: {str(e)}"})
    except requests.exceptions.RequestException as e:
        # Renvoyer une erreur plus explicite
        return jsonify({"status": "error", "message": f"Erreur de connexion: {str(e)}"})

@app.route('/get_current_resolution')
@login_required
def get_current_resolution_route():
    """
    Endpoint pour récupérer la résolution de l'écran si le diaporama est actif.
    """
    width, height = get_screen_resolution()
    
    if width and height:
         return jsonify({"success": True, "width": width, "height": height})
    else:
         # Ce cas ne devrait plus arriver car get_screen_resolution a un fallback, mais on le garde par sécurité.
         return jsonify({"success": False, "message": "Impossible de détecter la résolution. L'écran est-il branché ?"})

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
    country = request.form.get('wifi_country') # Get the country code

    if not ssid or not country: # Country is now required
        flash(_("Le SSID et le pays Wi-Fi sont obligatoires."), "danger")
        return redirect(url_for('configure'))

    try:
        # Sauvegarder les paramètres dans la config.json
        config = load_config()
        config['wifi_ssid'] = ssid
        config['wifi_password'] = password
        config['wifi_country'] = country # Save country to config
        save_config(config)

        # Appliquer les paramètres Wi-Fi au système
        set_wifi_config(ssid, password, country) # Pass country to the function
        flash(_("Paramètres Wi-Fi appliqués. Le service réseau a été redémarré pour forcer la connexion. Veuillez patienter une minute et vérifier le statut."), "success")
    except Exception as e:
        flash(_("Erreur lors de l'application des paramètres Wi-Fi : %(error)s", error=e), "danger")
    return redirect(url_for('configure'))

def get_wifi_status():
    """
    Récupère l'état de la connexion Wi-Fi de manière optimisée en un seul appel à nmcli.
    Cette fonction est plus robuste et rapide que de multiples appels à des commandes différentes.
    """
    interface = "wlan0" # On assume que wlan0 est l'interface Wi-Fi
    try:
        # Commande optimisée pour récupérer toutes les infos en une fois, de manière concise (-t)
        cmd = ['nmcli', '-t', '-f', 'GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS', 'dev', 'show', interface]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=5)
        
        output_map = {}
        for line in result.stdout.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                output_map[key] = value

        state_code_str = output_map.get('GENERAL.STATE', '0').split(' ')[0]
        state_code = int(state_code_str) if state_code_str.isdigit() else 0
        is_connected = (state_code == 100)
        
        if is_connected:
            ssid = output_map.get('GENERAL.CONNECTION', 'Inconnu')
            ip_address = output_map.get('IP4.ADDRESS[1]', 'N/A').split('/')[0]
            return {"is_connected": True, "ssid": ssid, "ip_address": ip_address}
        else:
            return {"is_connected": False, "ssid": "Non connecté", "ip_address": "N/A"}

    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, IndexError, ValueError) as e:
        print(f"Erreur lors de la récupération du statut Wi-Fi : {e}")
        return {"is_connected": False, "ssid": "Erreur", "ip_address": "N/A"}

@app.route('/api/wifi_status')
@login_required
def get_wifi_status_api():
    """Retourne l'état actuel de la connexion Wi-Fi."""
    status = get_wifi_status()
    return jsonify({"success": True, **status})

@app.route('/change_password', methods=['POST'])
@login_required
def change_password_route():
    """Gère la modification du mot de passe de l'interface."""
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if not new_password or not confirm_password:
        flash(_("Les deux champs de mot de passe sont requis."), "danger")
        return redirect(url_for('configure'))

    if new_password != confirm_password:
        flash(_("Les mots de passe ne correspondent pas."), "danger")
        return redirect(url_for('configure'))
    
    if len(new_password) < 6:
        flash(_("Le mot de passe doit contenir au moins 6 caractères."), "warning")
        return redirect(url_for('configure'))

    try:
        change_password(new_password)
        flash(_("Mot de passe mis à jour avec succès. Il sera nécessaire pour votre prochaine connexion."), "success")
    except Exception as e:
        flash(_("Erreur lors du changement de mot de passe : %(error)s", error=e), "danger")

    return redirect(url_for('configure'))

@app.route('/api/interface_status/<interface_name>')
@login_required
def get_interface_status_api(interface_name):
    """Retourne l'état d'une interface réseau spécifique."""
    # Valider le nom de l'interface pour la sécurité
    if not re.match(r'^[a-zA-Z0-9-]+$', interface_name):
        return jsonify({"success": False, "message": "Nom d'interface invalide."}), 400
    
    status = get_interface_status(interface_name)
    return jsonify({"success": True, **status})

@app.route('/api/set_interface_state', methods=['POST'])
@login_required
def set_interface_state_api():
    """Active ou désactive une interface réseau."""
    data = request.get_json()
    interface_name = data.get('interface')
    state = data.get('state')

    if not interface_name or not state in ['up', 'down']:
        return jsonify({"success": False, "message": "Données invalides."}), 400
    
    if not re.match(r'^[a-zA-Z0-9-]+$', interface_name):
        return jsonify({"success": False, "message": "Nom d'interface invalide."}), 400

    try:
        set_interface_state(interface_name, state)
        return jsonify({"success": True, "message": f"L'interface {interface_name} a été passée à l'état '{state}'."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
# --- Lancement de l'application ---

@app.route('/api/backup_settings')
@login_required
def backup_settings_api():
    """Permet de télécharger le fichier de configuration actuel."""
    try:
        backup_name = f'pimmich_backup_{datetime.now().strftime("%Y-%m-%d")}.json'
        return send_from_directory('config', 'config.json', as_attachment=True, download_name=backup_name)
    except FileNotFoundError:
        flash(_("Le fichier de configuration n'a pas été trouvé."), "danger")
        return redirect(url_for('configure'))

@app.route('/api/restore_settings', methods=['POST'])
@login_required
def restore_settings_api():
    """Restaure la configuration à partir d'un fichier de sauvegarde."""
    if 'backup_file' not in request.files:
        flash(_("Aucun fichier de sauvegarde sélectionné."), "warning")
        return redirect(url_for('configure'))

    file = request.files['backup_file']
    if file.filename == '':
        flash(_("Aucun fichier de sauvegarde sélectionné."), "warning")
        return redirect(url_for('configure'))

    try:
        # Lire et valider le contenu JSON
        content = file.stream.read().decode("utf-8")
        new_config_data = json.loads(content)

        # Sauvegarder la nouvelle configuration
        save_config(new_config_data)
        flash(_("Configuration restaurée avec succès ! Le diaporama va redémarrer pour appliquer les changements."), "success")
    except (json.JSONDecodeError, UnicodeDecodeError):
        flash(_("Fichier de sauvegarde invalide ou corrompu. Ce n'est pas un fichier JSON valide."), "danger")
    except Exception as e:
        flash(_("Erreur lors de la restauration : %(error)s", error=e), "danger")
    
    return redirect(url_for('configure'))

def get_cpu_temperature():
    """
    Tente de récupérer la température du CPU en utilisant plusieurs méthodes.
    Retourne la température formatée ou "N/A" en cas d'échec.
    """
    # Méthode 1: vcgencmd (spécifique au Raspberry Pi)
    try:
        temp_output = subprocess.check_output(['vcgencmd', 'measure_temp']).decode('utf-8')
        match = re.search(r"temp=([\d\.]*)'C", temp_output)
        if match:
            return float(match.group(1))
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass  # Si la commande échoue, on passe à la méthode suivante

    # Méthode 2: sysfs thermal_zone0 (Linux générique)
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_raw = int(f.read())
            return temp_raw / 1000.0
    except (FileNotFoundError, ValueError):
        pass # Si le fichier n'existe pas ou est invalide, on passe à la suite

    return None # Valeur par défaut si toutes les méthodes échouent

@app.route('/api/system_info')
@login_required
def get_system_info_api():
    """Retourne les informations système (température, CPU, RAM, stockage) en JSON."""
    try:
        # Obtenir l'heure une seule fois pour les deux mesures
        current_time_str = datetime.now().strftime("%H:%M:%S")

        # Température CPU
        current_temp_float = get_cpu_temperature()
        
        # Ajouter la mesure à l'historique si elle est valide
        if current_temp_float is not None:
            cpu_temp_history.append({
                "time": current_time_str,
                "temp": current_temp_float
            })
            cpu_temp_str = f"{current_temp_float:.1f}°C"
        else:
            cpu_temp_str = "N/A"

        # Utilisation CPU
        # interval=None le rend non-bloquant et compare à l'appel précédent. Idéal pour le polling.
        current_cpu_usage_float = psutil.cpu_percent(interval=None)
        cpu_usage_history.append({
            "time": current_time_str,
            "usage": current_cpu_usage_float
        })
        cpu_usage_str = f"{current_cpu_usage_float}%"

        # Utilisation RAM
        ram = psutil.virtual_memory()
        ram_usage_percent_float = ram.percent
        ram_usage_history.append({
            "time": current_time_str,
            "usage": ram_usage_percent_float
        })
        ram_usage_str = f"{ram.percent}% ({ram.used / (1024**3):.1f}GB / {ram.total / (1024**3):.1f}GB)"

        # Utilisation Disque
        disk = psutil.disk_usage('/')
        disk_usage_percent_float = disk.percent
        disk_usage_history.append({
            "time": current_time_str,
            "usage": disk_usage_percent_float
        })
        disk_usage_str = f"{disk.percent}% ({disk.used / (1024**3):.1f}GB / {disk.total / (1024**3):.1f}GB)"

        return jsonify({
            "success": True,
            "cpu_temp": cpu_temp_str,
            "cpu_usage": cpu_usage_str,
            "ram_usage": ram_usage_str,
            "disk_usage": disk_usage_str,
            "cpu_temp_history": list(cpu_temp_history),
            "cpu_usage_history": list(cpu_usage_history),
            "ram_usage_history": list(ram_usage_history),
            "disk_usage_history": list(disk_usage_history) # Ajouter l'historique pour le graphique
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/list_logs', methods=['GET'])
@login_required
def list_logs():
    """Retourne la liste des fichiers de log qui existent réellement."""
    available_logs = []
    # Itérer dans un ordre défini pour une interface utilisateur cohérente
    log_order = ["app", "slideshow_stdout", "slideshow_stderr", "voice_control_stdout", "voice_control_stderr"]
    for key in log_order:
        info = LOG_FILES_MAP.get(key)
        if info and os.path.exists(info["path"]):
            # Traduire la clé du nom pendant la requête
            available_logs.append({"key": key, "name": _(info["name_key"])})
    return jsonify({"success": True, "logs": available_logs})

@app.route('/api/logs')
@login_required
def get_logs_api():
    """Retourne le contenu d'un fichier de log spécifié."""
    log_type = request.args.get('type', 'app')
    
    log_info = LOG_FILES_MAP.get(log_type)
    if not log_info:
        return jsonify({"success": False, "message": "Type de log invalide."})

    log_file_path = log_info['path']

    try:
        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            # Lire seulement les 500 dernières lignes pour améliorer les performances
            # sur les fichiers de log volumineux, ce qui rend l'interface plus réactive.
            lines = f.readlines()
            content = "".join(lines[-500:])
        return jsonify({"success": True, "content": content})
    except FileNotFoundError:
        # C'est un cas normal si le log n'a pas encore été créé. On retourne un contenu vide.
        return jsonify({"success": True, "content": ""})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/clear_logs', methods=['POST'])
@login_required
def clear_logs_api():
    """Efface le contenu d'un fichier de log spécifié."""
    data = request.get_json()
    log_type = data.get('type')

    log_info = LOG_FILES_MAP.get(log_type)
    if not log_info:
        return jsonify({"success": False, "message": "Type de log invalide."}), 400
    log_file_path = log_info['path']

    try:
        if os.path.exists(log_file_path):
            with open(log_file_path, 'w') as f:
                f.truncate(0) # Efface le contenu du fichier
            return jsonify({"success": True, "message": f"Le log '{log_type}' a été effacé."})
        else:
            return jsonify({"success": False, "message": f"Fichier de log '{log_file_path}' non trouvé."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/update_app', methods=['GET'])
@login_required
def update_app():
    """
    Met à jour l'application depuis GitHub et la redémarre.
    Utilise Server-Sent Events pour donner un feedback en direct.
    """
    @stream_with_context
    def generate():
        def stream_event(data):
            """Formate les données en événement Server-Sent Event (SSE)."""
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        update_script_path = Path(app.root_path) / 'update_script.sh'

        if not update_script_path.exists():
            yield stream_event({"type": "error", "message": "Le script de mise à jour 'update_script.sh' est introuvable."})
            return

        try:
            os.chmod(update_script_path, 0o755)
        except OSError as e:
            yield stream_event({"type": "error", "message": f"Impossible de rendre le script de mise à jour exécutable : {e}"})
            return

        yield stream_event({"type": "info", "percent": 5, "message": "Lancement du script de mise à jour..."})

        process = subprocess.Popen(
            ['/bin/bash', str(update_script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            encoding='utf-8'
        )

        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if not line: continue

            if line.startswith("STEP:PULL:"):
                yield stream_event({"type": "info", "percent": 25, "message": line.replace("STEP:PULL:", "").strip()})
            elif line.startswith("STEP:PIP:"):
                yield stream_event({"type": "info", "percent": 75, "message": line.replace("STEP:PIP:", "").strip()})
            elif line.startswith("STEP:RESTART:"):
                yield stream_event({"type": "info", "percent": 95, "message": line.replace("STEP:RESTART:", "").strip()})
            else:
                yield stream_event({"type": "info", "message": line})

        process.stdout.close()
        return_code = process.wait()

        if return_code == 0:
            yield stream_event({"stage": "RESTART", "percent": 100, "message": "Mise à jour terminée. Redémarrage en cours..."})
            def restart_server():
                time.sleep(3)
                print("[Update] Redémarrage du serveur suite à la mise à jour...")
                os.kill(os.getpid(), signal.SIGTERM)
                os._exit(42)
            
            restart_thread = threading.Thread(target=restart_server)
            restart_thread.start()
        else:
            yield stream_event({"type": "error", "message": f"La mise à jour a échoué. Le script a retourné le code d'erreur {return_code}."})

    return Response(generate(), mimetype='text/event-stream', headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})

@app.route('/api/expand_filesystem', methods=['POST'])
@login_required
def expand_filesystem():
    """
    Lance le script qui étend le système de fichiers racine.
    """
    @stream_with_context
    def generate():
        def stream_event(data):
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        script_path = Path(app.root_path) / 'utils' / 'expand_filesystem.sh'

        if not script_path.exists():
            yield stream_event({"type": "error", "message": "Le script 'utils/expand_filesystem.sh' est introuvable."})
            return

        try:
            os.chmod(script_path, 0o755)
        except OSError as e:
            yield stream_event({"type": "error", "message": f"Impossible de rendre le script exécutable : {e}"})
            return

        command = ['/bin/bash', str(script_path)]

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            encoding='utf-8'
        )

        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if not line: continue

            parts = line.split(':', 2)
            if len(parts) == 3:
                yield stream_event({"type": parts[0], "stage": parts[1], "message": parts[2]})
            else:
                yield stream_event({"type": "raw", "message": line})

        process.stdout.close()
        process.wait()

    return Response(generate(), mimetype='text/event-stream', headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


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
        api_status = "OK"
        formatted_tides = []

        if cache_data.get('cooldown'):
            api_status = f"En cooldown (quota API probablement atteint). Prochaine tentative après { (last_update_dt + timedelta(hours=12)).strftime('%H:%M') }."
        
        tides_data = cache_data.get('data', [])
        
        # --- CORRECTION: Gérer l'ancien format de cache (dictionnaire) ---
        if not tides_data or not isinstance(tides_data, list):
            api_status = "Aucune donnée de marée valide dans le cache. Forcez une mise à jour."
            if isinstance(tides_data, dict):
                api_status = "Ancien format de cache détecté. Forcez une mise à jour."
        else:
            today = datetime.now().date()
            tomorrow = today + timedelta(days=1)
            day_map = {'Mon':'Lun', 'Tue':'Mar', 'Wed':'Mer', 'Thu':'Jeu', 'Fri':'Ven', 'Sat':'Sam', 'Sun':'Dim'}

            # On ne prend que les 5 prochaines marées pour l'affichage web
            for tide in tides_data[:5]:
                tide_dt = datetime.fromisoformat(tide['time']).astimezone()
                tide_date = tide_dt.date()

                if tide_date == today: day_str = "Aujourd'hui"
                elif tide_date == tomorrow: day_str = "Demain"
                else: day_str = day_map.get(tide_dt.strftime('%a'), tide_dt.strftime('%a'))

                formatted_tides.append({
                    "type": "Pleine Mer" if tide['type'] == 'high' else "Basse Mer",
                    "time": f"{day_str} à {tide_dt.strftime('%H:%M')}",
                    "height": f"{tide['height']:.2f}m"
                })

        return jsonify({"success": True, "last_update": last_update_str, "tides": formatted_tides, "api_status": api_status})
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
    photo_full_path = PREPARED_DIR / photo_relative_path

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

@app.route('/api/toggle_favorite', methods=['POST'])
@login_required
def toggle_favorite():
    """Ajoute ou retire une photo de la liste des favoris."""
    data = request.get_json()
    photo_relative_path = data.get('photo')

    if not photo_relative_path:
        return jsonify({"success": False, "message": "Chemin de la photo manquant."}), 400

    favorites = load_favorites()
    is_currently_favorite = photo_relative_path in favorites

    if is_currently_favorite:
        favorites.remove(photo_relative_path)
    else:
        favorites.append(photo_relative_path)
    
    save_favorites(favorites)
    
    return jsonify({"success": True, "is_favorite": not is_currently_favorite})

@app.route('/api/set_polaroid_text', methods=['POST'])
@login_required
def set_polaroid_text():
    """Applique un texte à une image Polaroid."""
    data = request.get_json()
    photo_relative_path = data.get('photo')
    text = data.get('text', '')

    if not photo_relative_path:
        return jsonify({"success": False, "message": "Chemin de la photo manquant."}), 400

    try:
        # Construire le chemin vers la version polaroid de l'image
        path_obj = Path(photo_relative_path)
        polaroid_filename = f"{path_obj.stem}_polaroid.jpg"
        polaroid_relative_path = path_obj.with_name(polaroid_filename)
        polaroid_full_path = PREPARED_DIR / polaroid_relative_path

        if not polaroid_full_path.exists():
             return jsonify({"success": False, "message": "La version Polaroid de cette photo n'existe pas."}), 404

        # Appeler la fonction pour ajouter le texte
        add_text_to_polaroid(str(polaroid_full_path), text)

        # Sauvegarder le texte dans le fichier de config
        texts = load_polaroid_texts()
        if text and text.strip():
            texts[photo_relative_path] = text
        else:
            texts.pop(photo_relative_path, None) # Supprimer la clé si le texte est vide
        save_polaroid_texts(texts)

        return jsonify({"success": True, "message": "Texte mis à jour."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur interne du serveur : {e}"}), 500

@app.route('/api/set_image_text', methods=['POST'])
@login_required
def set_image_text():
    """Applique un texte à une image générique."""
    data = request.get_json()
    photo_relative_path = data.get('photo')
    text = data.get('text', '')

    if not photo_relative_path:
        return jsonify({"success": False, "message": "Chemin de la photo manquant."}), 400

    try:
        # Le chemin relatif est de la forme 'source/nom_photo.jpg'
        photo_full_path = PREPARED_DIR / photo_relative_path

        if not photo_full_path.is_file():
            return jsonify({"success": False, "message": f"Photo non trouvée : {photo_full_path}"}), 404

        # Appeler la fonction pour ajouter le texte
        add_text_to_image(str(photo_full_path), text)

        # Sauvegarder le texte dans le fichier de config
        texts = load_text_states()
        if text and text.strip():
            texts[photo_relative_path] = text
        else:
            texts.pop(photo_relative_path, None) # Supprimer la clé si le texte est vide
        save_text_states(texts)

        return jsonify({"success": True, "message": "Texte mis à jour."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur interne du serveur : {e}"}), 500

@app.route('/api/telegram/invitations', methods=['GET', 'POST'])
@login_required
def manage_telegram_invitations():
    if request.method == 'GET':
        invitations = load_invitations()
        # Filtrer pour ne garder que les invitations valides et non expirées
        active_invitations = {
            code: data for code, data in invitations.items()
            if datetime.fromisoformat(data['expires_at']) > datetime.now()
        }
        return jsonify(list(active_invitations.values()))

    if request.method == 'POST':
        data = request.get_json()
        guest_name = data.get('name')
        duration_days = int(data.get('duration', 7))

        if not guest_name:
            return jsonify({"success": False, "message": "Le nom de l'invité est requis."}), 400

        invitations = load_invitations()
        code = secrets.token_urlsafe(6) # Génère un code court et sécurisé
        
        invitations[code] = {
            "code": code,
            "guest_name": guest_name,
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=duration_days)).isoformat(),
            "used_by_user_id": None
        }
        save_invitations(invitations)
        return jsonify({"success": True, "message": "Invitation créée.", "invitation": invitations[code]})

@app.route('/api/telegram/invitations/<code>', methods=['DELETE'])
@login_required
def delete_telegram_invitation(code):
    invitations = load_invitations()
    if code in invitations:
        del invitations[code]
        save_invitations(invitations)
        return jsonify({"success": True, "message": "Invitation supprimée."})
    else:
        return jsonify({"success": False, "message": "Invitation non trouvée."}), 404

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

@app.route('/api/voice_control/toggle', methods=['POST'])
@login_required
def toggle_voice_control():
    """Active ou désactive le service de contrôle vocal."""
    data = request.get_json()
    enabled = data.get('enabled')

    if enabled is None:
        return jsonify({"success": False, "message": _("Paramètre 'enabled' manquant.")}), 400

    try:
        # Mettre à jour la configuration
        config = load_config()
        config['voice_control_enabled'] = enabled
        save_config(config)

        # Démarrer ou arrêter le service
        if enabled:
            start_voice_control()
            message = _("Service de contrôle vocal activé.")
        else:
            stop_voice_control()
            message = _("Service de contrôle vocal désactivé.")
        
        return jsonify({"success": True, "message": message})
    except Exception as e:
        logging.error(f"Erreur lors du basculement du contrôle vocal : {e}", exc_info=True)
        return jsonify({"success": False, "message": _("Erreur interne du serveur : %(error)s", error=str(e))}), 500

def migrate_guest_folders():
    """Migre les anciens dossiers 'guests' et 'invites' vers 'invités'."""
    base_photos = BASE_DIR / "static" / "photos"
    base_prepared = BASE_DIR / "static" / "prepared"
    target_name = "invités"
    legacy_names = ["guests", "invites"]

    # Créer les dossiers cibles s'ils n'existent pas
    (base_photos / target_name).mkdir(parents=True, exist_ok=True)
    (base_prepared / target_name).mkdir(parents=True, exist_ok=True)

    for legacy in legacy_names:
        # Migration des photos sources
        legacy_photos_dir = base_photos / legacy
        if legacy_photos_dir.exists() and legacy_photos_dir.is_dir():
            print(f"[Migration] Déplacement des photos de '{legacy}' vers '{target_name}'...")
            for item in legacy_photos_dir.iterdir():
                dest = base_photos / target_name / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
            # Supprimer le dossier source s'il est vide
            try:
                legacy_photos_dir.rmdir()
            except OSError:
                pass # Le dossier n'est pas vide, on le laisse

        # Migration des photos préparées
        legacy_prepared_dir = base_prepared / legacy
        if legacy_prepared_dir.exists() and legacy_prepared_dir.is_dir():
            print(f"[Migration] Déplacement des fichiers préparés de '{legacy}' vers '{target_name}'...")
            for item in legacy_prepared_dir.iterdir():
                dest = base_prepared / target_name / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
            try:
                legacy_prepared_dir.rmdir()
            except OSError:
                pass

    # Mise à jour de la configuration pour remplacer les anciennes sources par la nouvelle
    config = load_config()
    sources = config.get('display_sources', [])
    new_sources = set(sources)
    modified = False
    for legacy in legacy_names:
        if legacy in new_sources:
            new_sources.remove(legacy)
            new_sources.add(target_name)
            modified = True
    
    if modified:
        config['display_sources'] = list(new_sources)
        save_config(config)
        print(f"[Migration] Configuration mise à jour : sources {sources} -> {list(new_sources)}")

if __name__ == '__main__':
    # Lancer la migration des dossiers invités au démarrage
    migrate_guest_folders()

    # Démarrer les workers de mise à jour dans des threads séparés
    immich_thread = threading.Thread(target=immich_update_worker, daemon=True)
    immich_thread.start()
    samba_thread = threading.Thread(target=samba_update_worker, daemon=True)
    samba_thread.start()
    telegram_thread = threading.Thread(target=telegram_bot_worker, daemon=True)
    telegram_thread.start()
    
    # Démarrer le worker de planification du diaporama
    scheduler_thread = threading.Thread(target=schedule_worker, daemon=True)
    scheduler_thread.start()

    # --- NOUVEAU: Démarrage du contrôle vocal si activé ---
    config = load_config()
    if config.get('voice_control_enabled'):
        print("Le contrôle vocal est activé, démarrage du service...")
        start_voice_control()

    app.run(host='0.0.0.0', port=5000)
