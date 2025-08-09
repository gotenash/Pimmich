import os
import random
import time
import pygame
import traceback
import requests
from PIL import Image
import re
import socket
import subprocess, sys
import glob
import collections
import math
from datetime import datetime, timedelta
import json
import qrcode
import psutil
from pathlib import Path
from utils.text_drawer import draw_text_with_outline
from utils.slideshow_manager import HDMI_OUTPUT # Importer la constante centralisée
from utils.config_manager import load_config

# Définition des chemins
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREPARED_BASE_DIR = Path(BASE_DIR) / 'static' / 'prepared'
SOUNDS_DIR = Path(BASE_DIR) / 'static' / 'sounds'
ICONS_DIR = Path(BASE_DIR) / 'static' / 'icons'
NEW_POSTCARD_FLAG = Path(BASE_DIR) / 'cache' / 'new_postcard.flag'
CURRENT_PHOTO_FILE = "/tmp/pimmich_current_photo.txt"
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'config.json')
FAVORITES_PATH = os.path.join(BASE_DIR, 'config', 'favorites.json')
FILTER_STATES_PATH = os.path.join(BASE_DIR, 'config', 'filter_states.json')
TIDES_CACHE_FILE = Path(BASE_DIR) / 'cache' / 'tides.json'
_icon_cache = {} # Cache pour les icônes météo chargées
_envelope_blink_end_time = None # Pour gérer le clignotement de l'icône

VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv')

def reinit_pygame():
    """Quitte et réinitialise complètement Pygame et les ressources associées."""
    print("[Slideshow] Réinitialisation complète de Pygame...")
    pygame.quit()
    pygame.init()

    global _icon_cache
    _icon_cache = {}
    print("[Slideshow] Cache des icônes météo vidé.")

    info = pygame.display.Info()
    width, height = info.current_w, info.current_h
    screen = pygame.display.set_mode((width, height), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)
    print(f"[Slideshow] Pygame entièrement réinitialisé à {width}x{height}.")
    return screen, width, height

def load_filter_states():
    """Charge les états des filtres depuis un fichier JSON."""
    if not os.path.exists(FILTER_STATES_PATH):
        return {}
    try:
        with open(FILTER_STATES_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        print(f"Avertissement: Impossible de lire le fichier d'état des filtres '{FILTER_STATES_PATH}'.")
        return {}

def load_favorites():
    """Charge la liste des photos favorites depuis un fichier JSON."""
    if not os.path.exists(FAVORITES_PATH):
        return []
    try:
        with open(FAVORITES_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def get_local_ip():
    """Tente de récupérer l'adresse IP locale de la machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Cette IP n'a pas besoin d'être joignable
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "xxx.xxx.xxx.xxx" # Fallback
    finally:
        s.close()
    return ip

# Vérifie si on est dans les heures actives
def is_within_active_hours(start, end):
    now = datetime.now().time()
    try:
        start_time = datetime.strptime(start, "%H:%M").time()
        end_time = datetime.strptime(end, "%H:%M").time()
    except Exception as e:
        print(f"Erreur format horaire : {e}")
        return True

    if start_time <= end_time:
        return start_time <= now <= end_time
    else:
        return now >= start_time or now <= end_time

# --- Gestion de la météo ---
_weather_and_forecast_data = None
_last_weather_and_forecast_fetch = None
_weather_warning_printed = False

def get_weather_and_forecast(config):
    """Récupère la météo actuelle et les prévisions sur 3 jours."""
    global _weather_and_forecast_data, _last_weather_and_forecast_fetch, _weather_warning_printed
    
    api_key = config.get("weather_api_key")
    city = config.get("weather_city")
    units = config.get("weather_units", "metric")
    try:
        interval_minutes = int(config.get("weather_update_interval_minutes", 30))
    except (ValueError, TypeError):
        interval_minutes = 30

    if not api_key or not city:
        if not _weather_warning_printed:
            print("[Weather] Clé API ou ville manquante. La météo est désactivée.")
            _weather_warning_printed = True
        return None

    now = datetime.now()
    if _last_weather_and_forecast_fetch and (now - _last_weather_and_forecast_fetch).total_seconds() < interval_minutes * 60:
        return _weather_and_forecast_data

    print("[Weather] Récupération des prévisions météo...")
    _last_weather_and_forecast_fetch = now # Mettre à jour pour éviter les appels répétés en cas d'échec

    try:
        # Utilise l'API de prévision 5 jours / 3 heures (disponible en offre gratuite)
        url = f"https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={api_key}&units={units}&lang=fr"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        api_data = response.json()

        # --- Traitement des données pour obtenir une prévision par jour ---
        current_weather = api_data['list'][0]
        
        daily_forecasts = collections.defaultdict(lambda: {'temps': [], 'icons': []})
        
        # Grouper les données par jour
        for forecast in api_data['list']:
            day = datetime.fromtimestamp(forecast['dt']).strftime('%Y-%m-%d')
            daily_forecasts[day]['temps'].append(forecast['main']['temp'])
            daily_forecasts[day]['icons'].append((forecast['weather'][0]['icon'], forecast['dt_txt'], forecast['weather'][0]['description']))

        processed_forecast = []
        # Trier les jours et prendre les 3 prochains jours (en excluant aujourd'hui)
        today_str = datetime.now().strftime('%Y-%m-%d')
        sorted_days = sorted([day for day in daily_forecasts.keys() if day > today_str])[:3]

        day_map_fr = {'Mon':'Lun', 'Tue':'Mar', 'Wed':'Mer', 'Thu':'Jeu', 'Fri':'Ven', 'Sat':'Sam', 'Sun':'Dim'}

        for i, day_str in enumerate(sorted_days):
            day_data = daily_forecasts[day_str]
            
            if i == 0:
                day_name_fr = "Demain"
            else:
                day_name_en = datetime.strptime(day_str, '%Y-%m-%d').strftime('%a')
                day_name_fr = day_map_fr.get(day_name_en, day_name_en.upper())

            min_temp = round(min(day_data['temps']))
            max_temp = round(max(day_data['temps']))
            
            # Choisir une icône représentative (celle la plus proche de 13h)
            midday_icon = day_data['icons'][0][0] # icon
            midday_desc = day_data['icons'][0][2] # description
            min_hour_diff = 24
            for icon, dt_txt, desc in day_data['icons']:
                hour = int(dt_txt.split(' ')[1].split(':')[0])
                if abs(hour - 13) < min_hour_diff:
                    min_hour_diff = abs(hour - 13)
                    midday_icon = icon
                    midday_desc = desc

            processed_forecast.append({
                'day': day_name_fr,
                'min_temp': min_temp,
                'max_temp': max_temp,
                'icon': midday_icon,
                'description': midday_desc.capitalize()
            })
        
        _weather_and_forecast_data = {'current': current_weather, 'forecast': processed_forecast}
        print(f"[Weather] Météo et prévisions mises à jour pour {city}.")
        return _weather_and_forecast_data

    except requests.exceptions.RequestException as e:
        print(f"[Weather] Erreur réseau lors de la récupération des prévisions : {e}")
        return None
    except Exception as e:
        print(f"[Weather] Erreur générale lors de la récupération des prévisions : {e}")
        traceback.print_exc()
        return None

# --- Gestion des marées ---
_tides_data = None
_last_tides_fetch = None
_tides_warning_printed = False

def get_tides(config):
    """Récupère les prochaines marées haute et basse, avec un cache en mémoire et un cache fichier persistant."""
    global _tides_data, _last_tides_fetch, _tides_warning_printed
    api_key = config.get("stormglass_api_key")
    lat = config.get("tide_latitude")
    lon = config.get("tide_longitude")
    # Intervalle de cache de 12 heures pour limiter les appels API à 2 par jour max.
    cache_duration_seconds = 12 * 3600

    if not all([api_key, lat, lon]):
        if not _tides_warning_printed:
            print("[Tides] Clé API StormGlass, latitude ou longitude manquante. Les marées sont désactivées.")
            _tides_warning_printed = True
        return None

    # 1. Vérifier le cache en mémoire d'abord
    now = datetime.now()
    if _last_tides_fetch and (now - _last_tides_fetch).total_seconds() < cache_duration_seconds:
        return _tides_data

    # 2. Le cache mémoire est expiré, on vérifie le cache fichier
    TIDES_CACHE_FILE.parent.mkdir(exist_ok=True)
    if TIDES_CACHE_FILE.exists():
        try:
            with open(TIDES_CACHE_FILE, 'r') as f:
                cache_content = json.load(f)
            
            last_file_fetch_dt = datetime.fromisoformat(cache_content['timestamp'])
            
            if (now - last_file_fetch_dt).total_seconds() < cache_duration_seconds:
                # Si c'est une entrée de cooldown, on ne fait rien et on attend.
                if cache_content.get('cooldown'):
                    print("[Tides] Cooldown API actif depuis le cache fichier.")
                    _last_tides_fetch = now # Mettre à jour le timer en mémoire pour respecter le cooldown
                    _tides_data = None
                    return None

                tide_data_from_cache = cache_content.get('data')

                # --- NOUVEAU: Vérification du format du cache pour la compatibilité ascendante ---
                if isinstance(tide_data_from_cache, list):
                    print("[Tides] Données de marée valides (format liste) trouvées dans le cache fichier.")
                    _tides_data = tide_data_from_cache
                    _last_tides_fetch = now
                    return tide_data_from_cache
                else:
                    print("[Tides] Ancien format de cache détecté (dictionnaire). Le cache sera invalidé et recréé.")
                    # On laisse l'exécution continuer pour appeler l'API
        except Exception as e:
            print(f"[Tides] Erreur lecture du cache fichier, récupération depuis l'API. Erreur: {e}")

    # 3. Les deux caches sont invalides, appeler l'API
    print("[Tides] Récupération des données de marée depuis l'API StormGlass...")
    _last_tides_fetch = now # Mettre à jour pour éviter les appels répétés en cas d'échec

    try:
        start_time_utc = datetime.utcnow()
        end_time_utc = start_time_utc + timedelta(days=7) # --- MODIFICATION: Récupérer 7 jours de données ---

        headers = {'Authorization': api_key}
        params = {'lat': lat, 'lng': lon, 'start': start_time_utc.isoformat(), 'end': end_time_utc.isoformat()}
        
        response = requests.get('https://api.stormglass.io/v2/tide/extremes/point', params=params, headers=headers, timeout=15)
        response.raise_for_status()
        extremes_data = response.json().get('data', [])

        # Filtrer pour ne garder que les marées futures
        now_utc = datetime.utcnow().replace(tzinfo=None)
        future_extremes = [e for e in extremes_data if datetime.fromisoformat(e['time'].replace('Z', '+00:00')).replace(tzinfo=None) > now_utc]

        if not future_extremes:
            print("[Tides] Aucune marée future trouvée dans les données de l'API pour les prochaines 24h.")
            return None

        # Sauvegarder la liste complète des marées futures dans le cache
        data_to_cache = {'data': future_extremes, 'timestamp': datetime.now().isoformat()}
        
        with open(TIDES_CACHE_FILE, 'w') as f:
            json.dump(data_to_cache, f, indent=2)
        
        print("[Tides] Données de marée mises à jour et cache sauvegardé.")
        # --- CORRECTION: Mettre à jour le cache en mémoire avant de retourner ---
        _tides_data = future_extremes
        return _tides_data
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 402:
            print("[Tides] ERREUR: Quota API StormGlass dépassé. Prochaine tentative dans 12h.")
            # Écrire un timestamp de cooldown dans le cache pour éviter les re-tentatives si le script redémarre
            cooldown_data = {'data': {}, 'timestamp': datetime.now().isoformat(), 'cooldown': True}
            try:
                with open(TIDES_CACHE_FILE, 'w') as f:
                    json.dump(cooldown_data, f, indent=2)
                print("[Tides] Timestamp de cooldown écrit dans le cache fichier.")
            except Exception as write_e:
                print(f"[Tides] Impossible d'écrire le cooldown dans le cache fichier: {write_e}")
        else:
            print(f"[Tides] Erreur HTTP lors de la récupération des marées : {e}")
        _tides_data = None
        return None
    except Exception as e:
        print(f"[Tides] Erreur générale lors de la récupération des marées : {e}")
        traceback.print_exc()
        _tides_data = [] # Retourner une liste vide en cas d'erreur
        return None

def load_icon(icon_name, size, is_weather_icon=True):
    """
    Charge une icône, la met en cache et la retourne comme une surface Pygame.
    Retourne un carré rouge en cas d'échec pour un débogage visuel.
    """
    if size <= 0:
        print(f"[Display] AVERTISSEMENT: Taille d'icône invalide ({size}px) pour '{icon_name}'.")
        return None

    icon_key = f"{icon_name}_{size}"
    if icon_key in _icon_cache:
        return _icon_cache[icon_key]

    if is_weather_icon:
        icon_dir = PREPARED_BASE_DIR.parent / 'weather_icons'
    else:
        icon_dir = ICONS_DIR
    
    icon_path = icon_dir / f"{icon_name}.png"

    if icon_path.exists():
        try:
            loaded_surface = pygame.image.load(str(icon_path)).convert_alpha()
            icon_surface = pygame.transform.scale(loaded_surface, (size, size))
            _icon_cache[icon_key] = icon_surface
            return icon_surface
        except Exception as e:
            print(f"[Display] Erreur chargement icône '{icon_path}': {e}")
            # Fall through to return placeholder
    else:
        warning_key = f"warn_{icon_name}"
        if warning_key not in _icon_cache:
            print(f"[Display] AVERTISSEMENT: Fichier icône non trouvé : {icon_path}")
            _icon_cache[warning_key] = True
    
    # --- Retourner None en cas d'échec ---
    # Cela permet à la logique d'affichage de simplement ignorer l'icône.
    return None

def get_today_postcard_count():
    """Compte le nombre de cartes postales reçues aujourd'hui."""
    count = 0
    today_date = datetime.now().date()
    telegram_dir = PREPARED_BASE_DIR / 'telegram'

    if not telegram_dir.is_dir():
        return 0

    # On ne compte que les fichiers de cartes postales pour éviter les doublons
    for f in telegram_dir.glob('*_postcard.jpg'):
        # Utilise une regex pour extraire le timestamp du nom de fichier
        match = re.search(r'telegram_(\d+)_', f.name)
        if match:
            try:
                timestamp = int(match.group(1))
                photo_date = datetime.fromtimestamp(timestamp).date()
                if photo_date == today_date:
                    count += 1
            except (ValueError, OSError):
                continue # Ignorer les fichiers avec un timestamp invalide
    return count

def get_path_to_display(photo_path_obj, source, filter_states):
    """
    Détermine le chemin de fichier correct à afficher en fonction de la source et des filtres.
    """
    relative_path_str = f"{source}/{photo_path_obj.name}"
    active_filter = filter_states.get(relative_path_str, 'none')
    
    # Par défaut, on affiche l'image de base
    path_to_display = str(photo_path_obj)

    # Priorité 1: Filtre explicite de l'utilisateur
    if active_filter == 'polaroid':
        polaroid_path = photo_path_obj.with_name(f"{photo_path_obj.stem}_polaroid.jpg")
        if polaroid_path.exists():
            path_to_display = str(polaroid_path)
    elif active_filter == 'postcard':
        postcard_path = photo_path_obj.with_name(f"{photo_path_obj.stem}_postcard.jpg")
        if postcard_path.exists():
            path_to_display = str(postcard_path)
    # Priorité 2: Comportement par défaut pour la source Telegram (si aucun filtre n'est actif)
    elif source == 'telegram' and active_filter in ['none', 'original']:
        postcard_path = photo_path_obj.with_name(f"{photo_path_obj.stem}_postcard.jpg")
        if postcard_path.exists():
            path_to_display = str(postcard_path)
            
    return path_to_display

def build_playlist(media_list, config, favorites):
    """
    Construit la playlist finale en appliquant les boosts pour les favoris et les photos récentes.
    """
    favorite_boost = int(config.get("favorite_boost_factor", 2))
    telegram_boost_enabled = config.get("telegram_boost_enabled", True)
    telegram_boost_factor = int(config.get("telegram_boost_factor", 4))
    telegram_boost_duration_days = int(config.get("telegram_boost_duration_days", 7))

    playlist = []
    for media_path in media_list:
        playlist.append(media_path)
        relative_path = str(Path(media_path).relative_to(PREPARED_BASE_DIR))
        normalized_relative_path = re.sub(r'(_polaroid|_postcard)\.jpg$', '.jpg', relative_path)

        if telegram_boost_enabled and 'telegram' in media_path:
            match = re.search(r'telegram_(\d+)_', Path(media_path).name)
            if match and (datetime.now() - datetime.fromtimestamp(int(match.group(1)))).days < telegram_boost_duration_days:
                for _ in range(telegram_boost_factor): playlist.append(media_path)
        if normalized_relative_path in favorites:
            for _ in range(favorite_boost): playlist.append(media_path)
    return playlist

_hdmi_output = HDMI_OUTPUT
_hdmi_state = None  # variable pour éviter les appels répétitifs

# Gestion de l'alimentation de l'écran via swaymsg
def set_display_power(on: bool):
    global _hdmi_state
    if _hdmi_state == on:
        return
    if not _hdmi_output:
        # Ne rien faire si aucune sortie n'a été détectée
        return
    cmd = ['swaymsg', 'output', _hdmi_output, 'enable' if on else 'disable']
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        _hdmi_state = on
        print(f"Écran {'activé' if on else 'désactivé'} via swaymsg ({_hdmi_output})")
    except Exception as e:
        print(f"Erreur changement état écran via swaymsg : {e}")

try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM) # Utiliser la numérotation BCM des pins
    GPIO_AVAILABLE = True
except ImportError:
    print("RPi.GPIO non disponible. Le contrôle du ventilateur est désactivé.")
    GPIO_AVAILABLE = False

def set_gpio_output(pin, state):
    """
    Définit l'état (HIGH/True ou LOW/False) d'un pin GPIO en sortie.

    Args:
        pin (int): Le numéro du pin GPIO (en numérotation BCM).
        state (bool): True pour HIGH (3.3V), False pour LOW (0V).

    Returns:
        None
    """
    if GPIO_AVAILABLE:
        try:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
        except Exception as e:
            print(f"Erreur lors de la manipulation du GPIO {pin}: {e}")

def control_fan(temperature, threshold=55, pin=14):
    if temperature >= threshold:
        set_gpio_output(pin, True)
        # print(f"Ventilateur activé (température : {temperature}°C, seuil : {threshold}°C)") # Commenté pour réduire le bruit dans les logs
    else:
        set_gpio_output(pin, False)

# Helper function to parse hex colors (including alpha)
def parse_color(hex_color):
    hex_color = str(hex_color).lstrip('#')
    if len(hex_color) == 6: # RRGGBB
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    elif len(hex_color) == 8: # RRGGBBAA
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4, 6))
    else:
        return (255, 255, 255) # Default to white if invalid

# New function to perform a transition between two images
def perform_transition(screen, old_image_surface, new_image_path, duration, screen_width, screen_height, main_font, config, transition_type):
    clock = pygame.time.Clock()
    fps = 60 # FPS for the transition
    num_frames = int(duration * fps)
    if num_frames == 0: # Avoid division by zero if duration is too small
        num_frames = 1

    # Load and prepare new image
    new_pil_image = Image.open(new_image_path)
    if new_pil_image.mode != 'RGB':
        new_pil_image = new_pil_image.convert('RGB')

    # Scale new image to fit the screen (maintain aspect ratio, center)
    # This is the base image for the transition, not the pan/zoom scaled one
    new_pil_image_scaled = new_pil_image.copy()
    new_pil_image_scaled.thumbnail((screen_width, screen_height), Image.Resampling.LANCZOS)
    
    new_surface_scaled = pygame.Surface((screen_width, screen_height))
    new_surface_scaled.fill((0,0,0)) # Black background for new image
    
    img_x = (screen_width - new_pil_image_scaled.width) // 2
    img_y = (screen_height - new_pil_image_scaled.height) // 2
    
    new_surface_scaled.blit(pygame.image.fromstring(new_pil_image_scaled.tobytes(), new_pil_image_scaled.size, new_pil_image_scaled.mode), (img_x, img_y))

    for i in range(num_frames + 1):
        progress = i / num_frames # 0.0 to 1.0

        if transition_type == "fade":
            alpha = int(255 * progress)
            temp_new_surface_with_alpha = new_surface_scaled.copy()
            temp_new_surface_with_alpha.set_alpha(alpha)
            screen.blit(old_image_surface, (0, 0))
            screen.blit(temp_new_surface_with_alpha, (0, 0))
        elif transition_type.startswith("slide_"):
            # Determine slide direction
            direction = transition_type.split("_")[1]
            
            # Calculate offset for the new image
            offset_x, offset_y = 0, 0
            if direction == "left":
                offset_x = int(screen_width * (1 - progress)) # New image starts off-screen right, slides left
            elif direction == "right":
                offset_x = int(-screen_width * (1 - progress)) # New image starts off-screen left, slides right
            elif direction == "up":
                offset_y = int(screen_height * (1 - progress)) # New image starts off-screen bottom, slides up
            elif direction == "down":
                offset_y = int(-screen_height * (1 - progress)) # New image starts off-screen top, slides down
            
            screen.blit(old_image_surface, (0, 0)) # Draw old image first
            screen.blit(new_surface_scaled, (offset_x, offset_y)) # Draw new image sliding in
        else: # Fallback to fade if unknown type
            screen.blit(old_image_surface, (0, 0))
            screen.blit(new_surface_scaled, (0, 0)) # Just blit new image directly
        
        # Draw overlay during transition
        draw_overlay(screen, screen_width, screen_height, config, main_font)

        pygame.display.flip()
        clock.tick(fps)

    # Ensure the new image is fully blitted at the end of the transition
    screen.blit(new_surface_scaled, (0, 0))
    draw_overlay(screen, screen_width, screen_height, config, main_font)
    pygame.display.flip()

    return new_pil_image # Return the PIL image for further processing (pan/zoom)

# New function to draw the overlay elements (clock, date, weather)
def draw_overlay(screen, screen_width, screen_height, config, main_font):
    now = datetime.now()
    text_color = parse_color(config.get("clock_color", "#FFFFFF"))
    outline_color = parse_color(config.get("clock_outline_color", "#000000"))

    # --- Météo et Prévisions ---
    weather_and_forecast = None
    if config.get("show_weather", False):
        weather_and_forecast = get_weather_and_forecast(config)

    if config.get("show_clock", False):
        separator = "  |  "
        icon_padding = 10

        # --- Préparation des éléments à afficher ---
        elements = []

        # Heure
        time_str = now.strftime(config.get("clock_format", "%H:%M"))
        elements.append({'type': 'text', 'text': time_str})

        # Date
        if config.get("show_date", False):
            date_str = now.strftime(config.get("date_format", "%A %d %B %Y"))
            elements.append({'type': 'text', 'text': separator + date_str})

        # Météo Actuelle (utilisant les données déjà récupérées)
        if weather_and_forecast and weather_and_forecast.get('current'):
            try:
                current_weather = weather_and_forecast['current']
                icon_code = current_weather['weather'][0]['icon']
                icon_surface = load_icon(icon_code, main_font.get_height(), is_weather_icon=True)
                if icon_surface:
                    elements.append({'type': 'icon', 'surface': icon_surface, 'padding': icon_padding})

                temp = round(current_weather['main']['temp'])
                description = current_weather['weather'][0]['description'].capitalize()
                weather_str = f"{temp}°C, {description}"
                elements.append({'type': 'text', 'text': " " + weather_str})
            except Exception as e:
                print(f"[Display] Erreur préparation météo actuelle: {e}")

        # --- Prévisions sur 3 jours ---
        if weather_and_forecast and weather_and_forecast.get('forecast'):
            for forecast_day in weather_and_forecast.get('forecast', []):
                try:
                    elements.append({'type': 'text', 'text': separator})

                    # Icône pour le jour de prévision
                    icon_code = forecast_day.get('icon')
                    if icon_code:
                        icon_surface = load_icon(icon_code, main_font.get_height(), is_weather_icon=True)
                        if icon_surface:
                            elements.append({'type': 'icon', 'surface': icon_surface, 'padding': icon_padding})

                    # Texte de la prévision
                    day_name = forecast_day.get('day', '')
                    temp_str = f"{forecast_day['max_temp']}°/{forecast_day['min_temp']}°"
                    weather_str = f"{day_name}: {temp_str}"
                    elements.append({'type': 'text', 'text': " " + weather_str})
                except (IndexError, KeyError) as e:
                    print(f"[Display] Erreur préparation météo pour un jour: {e}")

        # --- Compteur de cartes postales du jour ---
        today_postcard_count = get_today_postcard_count()
        if today_postcard_count > 0:
            elements.append({'type': 'text', 'text': separator})

            # --- Logique de clignotement ---
            global _envelope_blink_end_time
            is_blinking = _envelope_blink_end_time and datetime.now() < _envelope_blink_end_time
            
            icon_surface = load_icon("envelope", main_font.get_height(), is_weather_icon=False)
            if icon_surface:
                # On ajoute toujours l'icône à la liste pour la largeur, mais on contrôle sa visibilité
                should_draw_icon = not is_blinking or (is_blinking and datetime.now().second % 2 == 0)
                elements.append({'type': 'icon', 'surface': icon_surface, 'padding': icon_padding, 'visible': should_draw_icon})
            
            # Texte du compteur
            elements.append({'type': 'text', 'text': f" {today_postcard_count}"})


        # --- Calcul de la taille totale et positionnement du bloc ---
        total_width = 0
        max_height = 0
        for el in elements:
            if el['type'] == 'text':
                el['surface'] = main_font.render(el['text'], True, text_color)
            total_width += el['surface'].get_width()
            if el.get('padding'):
                total_width += el['padding']
            if el['surface'].get_height() > max_height:
                max_height = el['surface'].get_height()

        offset_x = int(config.get("clock_offset_x", 0))
        offset_y = int(config.get("clock_offset_y", 0))
        position = config.get("clock_position", "center")

        if position == "left":
            block_x = offset_x
        elif position == "right":
            block_x = screen_width - total_width + offset_x
        else: # center
            block_x = (screen_width - total_width) // 2 + offset_x
        
        # Positionner le bloc en haut de l'écran avec un padding de 15px
        block_y = 15 + offset_y

        # --- Dessin du fond semi-transparent ---
        if config.get("clock_background_enabled", False):
            bg_color_hex = config.get("clock_background_color", "#00000080")
            bg_color_rgba = parse_color(bg_color_hex)
            
            if len(bg_color_rgba) == 3:
                bg_color_rgba = bg_color_rgba + (128,) # Ajouter une semi-transparence par défaut
            
            bg_surface = pygame.Surface((screen_width, max_height + 20), pygame.SRCALPHA)
            bg_surface.fill(bg_color_rgba)
            screen.blit(bg_surface, (0, block_y - 10))

        # --- Dessin des éléments séquentiellement ---
        current_x = block_x
        for el in elements:
            el_y = block_y + (max_height - el['surface'].get_height()) // 2
            
            if el.get('padding'):
                current_x += el['padding']

            # On ne dessine l'élément que s'il est visible (par défaut True)
            if el.get('visible', True):
                if el['type'] == 'text':
                    draw_text_with_outline(screen, el['text'], main_font, text_color, outline_color, (current_x, el_y), anchor="topleft")
                elif el['type'] == 'icon':
                    screen.blit(el['surface'], (current_x, el_y))
            
            current_x += el['surface'].get_width()

        # --- Bloc du bas pour les marées ---
        if config.get("show_tides", False):
            tides_data = get_tides(config)
            tide_text = None
            font_to_use = main_font

            if tides_data:
                tide_parts = []
                today = datetime.now().date()
                tomorrow = today + timedelta(days=1)
                day_map = {'Mon':'Lun', 'Tue':'Mar', 'Wed':'Mer', 'Thu':'Jeu', 'Fri':'Ven', 'Sat':'Sam', 'Sun':'Dim'}

                # Afficher les 4 prochaines marées pour avoir une bonne visibilité sur les jours à venir
                for tide in tides_data[:4]:
                    tide_dt = datetime.fromisoformat(tide['time']).astimezone()
                    tide_date = tide_dt.date()

                    if tide_date == today: day_str = "Auj."
                    elif tide_date == tomorrow: day_str = "Dem."
                    else: day_str = day_map.get(tide_dt.strftime('%a'), tide_dt.strftime('%a'))

                    type_str = "PM" if tide['type'] == 'high' else "BM"
                    time_str = tide_dt.strftime('%H:%M')
                    
                    tide_parts.append(f"{day_str} {type_str}: {time_str}")
                
                if tide_parts:
                    tide_text = " | ".join(tide_parts)
            else:
                # Afficher un message si les données ne sont pas disponibles mais que la fonction est activée
                tide_text = "Données de marée non disponibles"
                try:
                    # Utiliser une police légèrement plus petite pour le message d'erreur
                    font_path = config.get("clock_font_path", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
                    font_size = int(main_font.get_height() * 0.8) # 80% de la taille de la police principale
                    font_to_use = pygame.font.Font(font_path, font_size)
                except Exception as e:
                    print(f"[Display] Erreur chargement police pour message marée: {e}")
                    font_to_use = main_font # Fallback

            if tide_text:
                tide_offset_x = int(config.get("tide_offset_x", 0))
                tide_offset_y = int(config.get("tide_offset_y", 0))

                tide_surface = font_to_use.render(tide_text, True, text_color)
                tide_rect = tide_surface.get_rect(centerx=(screen_width // 2) + tide_offset_x, bottom=(screen_height - 15) + tide_offset_y)

                # --- Ajout du fond pour les marées ---
                if config.get("clock_background_enabled", False):
                    bg_color_hex = config.get("clock_background_color", "#00000080")
                    bg_color_rgba = parse_color(bg_color_hex)

                    if len(bg_color_rgba) == 3:
                        bg_color_rgba = bg_color_rgba + (128,)

                    # Créer une surface de fond sur toute la largeur de l'écran
                    bg_height = tide_rect.height + 10  # Ajouter 5px de padding en haut et en bas
                    bg_surface = pygame.Surface((screen_width, bg_height), pygame.SRCALPHA)
                    bg_surface.fill(bg_color_rgba)
                    # Positionner le fond verticalement pour qu'il encadre le texte
                    screen.blit(bg_surface, (0, tide_rect.top - 5))

                draw_text_with_outline(screen, tide_text, font_to_use, text_color, outline_color, tide_rect.topleft, anchor="topleft")

# Fonction pour afficher une image et l'heure
def display_photo_with_pan_zoom(screen, pil_image, screen_width, screen_height, config, main_font):
    """Affiche une image préparée et l'heure sur l'écran."""
    try:
        # Ensure it's in a compatible mode for Pygame (RGB is generally safe)
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')

        pan_zoom_enabled = config.get("pan_zoom_enabled", False)
        display_duration = config.get("display_duration", 10)
        print(f"[Slideshow] Using display_duration: {display_duration} seconds.") # Debug print
        
        # Always blit the base image first (this will be overwritten by animation if enabled)
        pygame_image_base = pygame.image.fromstring(pil_image.tobytes(), pil_image.size, pil_image.mode)
        screen.blit(pygame_image_base, (0, 0))
        
        if not pan_zoom_enabled: # If pan/zoom is disabled, just show static image
            # Affichage statique : blit une fois et attendre la durée
            draw_overlay(screen, screen_width, screen_height, config, main_font)
            pygame.display.flip()
            time.sleep(display_duration)
        else:
            # Logique de l'effet Pan/Zoom
            zoom_factor = float(config.get("pan_zoom_factor", 1.15)) # Récupérer le facteur de zoom de la config
            
            # Calculate scaled image dimensions
            scaled_width = int(screen_width * zoom_factor)
            scaled_height = int(screen_height * zoom_factor)

            # Scale the image once using PIL for quality, then convert to Pygame surface
            scaled_pil_image = pil_image.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
            scaled_pygame_image = pygame.image.fromstring(scaled_pil_image.tobytes(), scaled_pil_image.size, scaled_pil_image.mode)

            # --- NOUVELLE LOGIQUE DE PANNING AMÉLIORÉE ---
            max_x_offset = scaled_width - screen_width
            max_y_offset = scaled_height - screen_height

            # S'assurer que les offsets ne sont pas négatifs (si l'image est plus petite que l'écran)
            max_x_offset = max(0, max_x_offset)
            max_y_offset = max(0, max_y_offset)

            def get_random_edge_point(max_x, max_y):
                """Génère un point aléatoire sur l'un des quatre bords du rectangle de rognage."""
                edge = random.choice(['top', 'bottom', 'left', 'right'])
                if edge == 'top':
                    return (random.randint(0, max_x), 0)
                elif edge == 'bottom':
                    return (random.randint(0, max_x), max_y)
                elif edge == 'left':
                    return (0, random.randint(0, max_y))
                else: # right
                    return (max_x, random.randint(0, max_y))

            # Générer un point de départ et un point d'arrivée qui ne sont pas identiques
            start_offset = get_random_edge_point(max_x_offset, max_y_offset)
            end_offset = get_random_edge_point(max_x_offset, max_y_offset)
            while end_offset == start_offset:
                end_offset = get_random_edge_point(max_x_offset, max_y_offset)

            start_x, start_y = start_offset
            end_x, end_y = end_offset

            clock = pygame.time.Clock()
            start_animation_time = time.time()

            while time.time() - start_animation_time < display_duration:
                elapsed_animation_time = time.time() - start_animation_time
                # Appliquer une fonction d'accélération/décélération (ease-in-out) pour un mouvement plus doux
                raw_progress = min(1.0, elapsed_animation_time / display_duration)
                eased_progress = 0.5 * (1 - math.cos(raw_progress * math.pi))

                # Calculate current pan position
                current_x = int(start_x + (end_x - start_x) * eased_progress)
                current_y = int(start_y + (end_y - start_y) * eased_progress)

                # Blit the portion of the scaled image onto the screen
                screen.blit(scaled_pygame_image, (0, 0), (current_x, current_y, screen_width, screen_height))

                # Draw overlay (clock/date/weather)
                draw_overlay(screen, screen_width, screen_height, config, main_font)
                pygame.display.flip()
                clock.tick(60) # Limit frame rate to 60 FPS for smoother animation
                
    except Exception as e:
        print(f"Erreur affichage photo avec pan/zoom : {e}")
        traceback.print_exc()

def fade_to_black(screen, previous_surface, duration, clock):
    """Effectue un fondu au noir sur la surface donnée."""
    num_frames = int(duration * 60)
    if num_frames == 0: num_frames = 1
    
    black_surface = pygame.Surface(screen.get_size()).convert()
    black_surface.fill((0, 0, 0))

    for i in range(num_frames + 1):
        progress = i / num_frames
        alpha = int(255 * progress)
        black_surface.set_alpha(alpha)
        
        screen.blit(previous_surface, (0, 0))
        screen.blit(black_surface, (0, 0))
        pygame.display.flip()
        clock.tick(60)

def display_video(screen, video_path, screen_width, screen_height, config, main_font, previous_surface, clock):
    """Affiche une vidéo en plein écran en utilisant le lecteur externe mpv."""
    audio_enabled = config.get("video_audio_enabled", False)
    audio_output = config.get("video_audio_output", "auto")
    audio_volume = int(config.get("video_audio_volume", 100))
    transition_duration = float(config.get("transition_duration", 1.0))
    hwdec_enabled = config.get("video_hwdec_enabled", False)

    # Libérer le mixer de Pygame avant de lancer la vidéo pour éviter les conflits
    if audio_enabled:
        print("[Slideshow] Quitting pygame.mixer to free audio device for mpv.")
        pygame.mixer.quit()

    try:
        # 1. Fondu au noir avant de lancer la vidéo
        if previous_surface:
            fade_to_black(screen, previous_surface, transition_duration / 2, clock)

        print(f"[Slideshow] Preparing video (Audio: {'On' if audio_enabled else 'Off'}, Output: {audio_output}, Volume: {audio_volume}%): {video_path}")
        # On réaffiche la souris au cas où l'utilisateur voudrait interagir avec mpv (barre de progression, etc.)
        pygame.mouse.set_visible(True)
        
        # --- NOUVEAU: Forcer le volume système avec amixer ---
        if audio_enabled:
            print(f"[Audio] Forcing system volume to {audio_volume}% using amixer.")
            # Liste des contrôles de volume à maximiser.
            # On ignore les erreurs si un contrôle n'existe pas (check=False).
            for control in ['Master', 'PCM', 'Headphone', 'HDMI']:
                try:
                    subprocess.run(['amixer', 'sset', control, f'{audio_volume}%', 'unmute'], check=False, capture_output=True, text=True)
                except FileNotFoundError:
                    print("AVERTISSEMENT: La commande 'amixer' est introuvable. Impossible de régler le volume système.")
                    break # Inutile de continuer si amixer n'est pas là
        
        # Commande pour mpv
        # --ao=pulse: Utilise la couche de compatibilité PulseAudio de PipeWire, qui est souvent plus robuste
        # --hwdec=auto : Tente d'utiliser le décodage vidéo matériel, crucial pour les RPi
        # --vo=gpu : Utilise le rendu GPU, plus efficace
        hwdec_mode = 'auto' if hwdec_enabled else 'no'
        command = [
            'mpv',
            '--no-config',
            f'--hwdec={hwdec_mode}',
            '--vo=gpu',
            '--ao=pulse', # PulseAudio (ou PipeWire-Pulse) est un bon défaut pour la compatibilité
            '--fs', '--no-osc', '--no-osd-bar', '--loop=no', '--ontop',
            video_path
        ]

        if audio_enabled:
            # On ne spécifie plus de périphérique de sortie audio.
            # mpv utilisera la sortie par défaut du système, ce qui est plus robuste.
            # L'utilisateur peut configurer la sortie par défaut via les paramètres du système d'exploitation.
            command.extend([f'--volume={audio_volume}', '--no-mute'])
        else:
             command.append('--no-audio')
        
        print(f"[Slideshow] Executing mpv command: {' '.join(command)}")
        # On retire la redirection de la sortie d'erreur pour pouvoir diagnostiquer les problèmes de mpv dans les logs.
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)

    except FileNotFoundError:
        print(f"ERREUR: Commande introuvable. Assurez-vous que 'mpv' et 'amixer' (alsa-utils) sont installés.")
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de l'exécution de mpv pour la vidéo {video_path}. mpv a retourné un code d'erreur. Vérifiez les logs slideshow_stderr.log pour les détails.")
    except Exception as e:
        print(f"Erreur inattendue lors de la lecture de la vidéo {video_path}: {e}")
    finally:
        # --- Ré-initialiser le mixer de Pygame après la lecture vidéo ---
        # C'est crucial pour que Pygame puisse potentiellement jouer des sons plus tard,
        # et pour maintenir un état cohérent.
        if audio_enabled:
            print("[Slideshow] Re-initializing pygame.mixer.")
            try:
                pygame.mixer.init()
            except pygame.error as e:
                print(f"AVERTISSEMENT: Impossible de réinitialiser pygame.mixer: {e}")

# Boucle principale du diaporama
def start_slideshow():
    try: # Global try-except block for robust error handling
        print("[Slideshow] Starting slideshow initialization.")
        config = load_config() # Utilise le gestionnaire centralisé
        print(f"[Slideshow] Config loaded. show_clock: {config.get('show_clock')}, show_weather: {config.get('show_weather')}")

        pygame.init()
        print("[Slideshow] Pygame initialized.")
        info = pygame.display.Info()
        SCREEN_WIDTH, SCREEN_HEIGHT = info.current_w, info.current_h
        print(f"[Slideshow] Screen resolution: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
        print("[Slideshow] Pygame display set to FULLSCREEN.")
        pygame.mouse.set_visible(False)
        print("[Slideshow] Mouse cursor hidden.")

        try:
            import locale
            locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
            print("[Slideshow] Locale set to fr_FR.UTF-8.")
        except locale.Error:
            print("Avertissement: locale fr_FR.UTF-8 non disponible. Les dates seront en anglais.")

        print("[Slideshow] Entering main slideshow loop.")
        while True:
            config = load_config() # Recharger la config à chaque itération

            # --- Vérification et affichage immédiat de nouvelle carte postale ---
            if NEW_POSTCARD_FLAG.exists():
                print("[Slideshow] Nouvelle carte postale détectée.")
                
                # Déclencher le clignotement de l'icône pour 30 secondes
                global _envelope_blink_end_time
                _envelope_blink_end_time = datetime.now() + timedelta(seconds=30)

                new_postcard_path_str = ""
                try:
                    # 1. Lire le chemin de la nouvelle photo
                    with open(NEW_POSTCARD_FLAG, 'r') as f:
                        new_postcard_path_str = f.read().strip()
                    
                    new_postcard_path = Path(new_postcard_path_str)

                    if new_postcard_path.exists():
                        # 2. Jouer le son
                        lang = config.get('language', 'fr') # Récupérer la langue, avec 'fr' comme défaut
                        
                        # Construire le chemin du son spécifique à la langue
                        lang_sound_path = SOUNDS_DIR / f'notification_{lang}.wav'
                        
                        # Utiliser le son spécifique s'il existe, sinon le son par défaut
                        notification_sound_path = lang_sound_path if lang_sound_path.exists() else SOUNDS_DIR / 'notification.wav'
                        
                        if notification_sound_path.exists():
                            if not pygame.mixer.get_init(): # S'assurer que le mixer est initialisé
                                pygame.mixer.init()
                            notification_sound = pygame.mixer.Sound(str(notification_sound_path))
                            notification_sound.play()
                        
                        # 3. Afficher immédiatement la nouvelle carte postale
                        print(f"[Slideshow] Affichage immédiat de la nouvelle carte postale : {new_postcard_path}")
                        
                        # Recharger la police pour l'overlay
                        font_path_config = config.get("clock_font_path", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
                        clock_font_size_config = int(config.get("clock_font_size", 72))
                        try:
                            main_font_loaded = pygame.font.Font(font_path_config, clock_font_size_config)
                        except Exception as e:
                            main_font_loaded = pygame.font.SysFont("Arial", clock_font_size_config)

                        pil_image = Image.open(new_postcard_path)
                        
                        # Afficher avec pan/zoom pour la durée configurée
                        display_photo_with_pan_zoom(screen, pil_image, SCREEN_WIDTH, SCREEN_HEIGHT, config, main_font_loaded)
                        
                        # Mettre à jour la surface précédente pour la transition suivante
                        previous_photo_surface = screen.copy()
                    else:
                        print(f"[Slideshow] Erreur: le chemin '{new_postcard_path_str}' dans le fichier drapeau n'existe pas.")

                except Exception as e:
                    print(f"[Slideshow] Erreur lors du traitement de la nouvelle carte postale: {e}")
                    traceback.print_exc()
                finally:
                    # 4. Supprimer le drapeau pour ne pas rejouer
                    if NEW_POSTCARD_FLAG.exists():
                        NEW_POSTCARD_FLAG.unlink()

            filter_states = load_filter_states() # Charger les préférences de filtre
            favorites = load_favorites() # Charger la liste des favoris
            start_time = config.get("active_start", "06:00")
            end_time = config.get("active_end", "20:00")
            duration = config.get("display_duration", 10)
            
            # --- Chargement de la police à chaque itération ---
            # C'est plus robuste, surtout après une réinitialisation de l'affichage.
            font_path_config = config.get("clock_font_path", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
            clock_font_size_config = int(config.get("clock_font_size", 72))
            try:
                main_font_loaded = pygame.font.Font(font_path_config, clock_font_size_config)
            except Exception as e:
                print(f"Erreur chargement police : {e}. Utilisation de la police système.")
                main_font_loaded = pygame.font.SysFont("Arial", clock_font_size_config)
            # --- Fin du chargement de la police ---
            
            
            # Initialize transition_duration here to ensure it's always defined within the loop scope
            transition_type = config.get("transition_type", "fade") # Get transition type
            transition_enabled = config.get("transition_enabled", True) # Get transition enabled status
            transition_duration = float(config.get("transition_duration", 1.0)) 
            
            display_sources = config.get("display_sources", ["immich"]) # Nouvelle clé de config
            
            all_media = []
            for source in display_sources:
                source_dir = PREPARED_BASE_DIR / source
                if source_dir.is_dir():
                    # Obtenir les médias de base (non-polaroid, non-vignette, non-postcard)
                    base_photos = [f for f in source_dir.iterdir() if f.is_file() and (f.suffix.lower() in ('.jpg', '.jpeg', '.png') or f.suffix.lower() in VIDEO_EXTENSIONS) and not f.name.endswith(('_polaroid.jpg', '_thumbnail.jpg', '_postcard.jpg'))]
                    
                    for photo_path_obj in base_photos:
                        path_to_display = get_path_to_display(photo_path_obj, source, filter_states)
                        all_media.append(path_to_display)
            
            # --- Logique de création de la playlist avec boost ---
            playlist = build_playlist(all_media, config, favorites)

            if not playlist:
                print("Aucune photo trouvée dans les sources activées. Vérification dans 60 secondes.")
                
                screen.fill((0, 0, 0)) # Fond noir
                
                text_color = parse_color(config.get("clock_color", "#FFFFFF"))
                outline_color = parse_color(config.get("clock_outline_color", "#000000"))
                
                try:
                    font_path = config.get("clock_font_path", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
                    font_size = int(config.get("clock_font_size", 72) * 0.6) # Augmenté de 0.5
                    message_font = pygame.font.Font(font_path, font_size)
                    ip_font_size = int(config.get("clock_font_size", 72) * 0.8) # Augmenté de 0.65
                    ip_font = pygame.font.Font(font_path, ip_font_size)
                    small_font_size = int(config.get("clock_font_size", 72) * 0.4) # Augmenté de 0.35
                    small_font = pygame.font.Font(font_path, small_font_size)
                except Exception:
                    message_font = pygame.font.SysFont("Arial", 48)
                    ip_font = pygame.font.SysFont("Arial", 64)
                    small_font = pygame.font.SysFont("Arial", 32)

                # --- Logo ---
                logo_surface, logo_height, logo_spacing = None, 0, 30
                try:
                    logo_path = Path(BASE_DIR) / 'static' / 'pimmich_logo.png'
                    if logo_path.exists():
                        logo_img = pygame.image.load(str(logo_path)).convert_alpha()
                        original_width, original_height = logo_img.get_size()
                        new_width = 300
                        new_height = int(new_width * (original_height / original_width))
                        logo_surface = pygame.transform.smoothscale(logo_img, (new_width, new_height))
                        logo_height = logo_surface.get_height()
                except Exception as e:
                    print(f"Erreur chargement du logo : {e}")

                # --- Génération du QR Code ---
                qr_surface, qr_height, qr_spacing = None, 0, 30
                try:
                    ip_address_for_qr = get_local_ip()
                    url = f"http://{ip_address_for_qr}"
                    qr_img_pil = qrcode.make(url, box_size=8).convert('RGB')
                    qr_surface = pygame.image.fromstring(qr_img_pil.tobytes(), qr_img_pil.size, qr_img_pil.mode)
                    qr_height = qr_surface.get_height()
                except Exception as e:
                    print(f"Erreur génération QR code : {e}")

                ip_address = get_local_ip()
                messages = [
                    (message_font, "Aucune photo trouvée."),
                    (ip_font, f"Configurez sur : http://{ip_address}"),
                    (small_font, "(Identifiants dans credentials.json à la racine de la SD)"),
                    (message_font, "Nouvelle tentative dans 60 secondes...")
                ]
                
                line_spacing = 20
                text_block_height = sum(font.get_height() for font, _ in messages) + (len(messages) - 1) * line_spacing
                
                # Calcul de la hauteur totale pour un centrage parfait
                total_height = text_block_height
                if logo_surface: total_height += logo_height + logo_spacing
                if qr_surface: total_height += qr_height + qr_spacing + small_font.get_height() + 10
                current_y = (SCREEN_HEIGHT - total_height) // 2

                if logo_surface:
                    logo_rect = logo_surface.get_rect(centerx=SCREEN_WIDTH // 2, top=current_y)
                    screen.blit(logo_surface, logo_rect)
                    current_y += logo_height + logo_spacing

                for font, txt in messages:
                    text_surface = font.render(txt, True, text_color)
                    text_rect = text_surface.get_rect(centerx=SCREEN_WIDTH // 2, top=current_y)
                    draw_text_with_outline(screen, txt, font, text_color, outline_color, text_rect.topleft, anchor="topleft")
                    current_y += font.get_height() + line_spacing

                # Affichage du QR Code
                if qr_surface:
                    current_y += qr_spacing - line_spacing # Ajuster l'espacement avant le QR
                    qr_title_text = "Scannez pour configurer"
                    qr_title_surface = small_font.render(qr_title_text, True, text_color)
                    qr_title_rect = qr_title_surface.get_rect(centerx=SCREEN_WIDTH // 2, top=current_y)
                    draw_text_with_outline(screen, qr_title_text, small_font, text_color, outline_color, qr_title_rect.topleft, anchor="topleft")
                    current_y += qr_title_surface.get_height() + 10
                    qr_rect = qr_surface.get_rect(centerx=SCREEN_WIDTH // 2, top=current_y)
                    screen.blit(qr_surface, qr_rect)
                
                pygame.display.flip()

                time.sleep(60)
                continue

            previous_photo_surface = None # Initialize previous_photo_surface before the loop

            random.shuffle(playlist)
            for photo_path in playlist:
                # --- CORRECTIF: Vérifier si le fichier existe avant de tenter de l'afficher ---
                if not os.path.exists(photo_path):
                    print(f"[Slideshow] Fichier non trouvé (probablement supprimé) : {photo_path}. Passage au suivant.")
                    continue

                # La gestion de la veille/réveil est maintenant gérée par le planificateur dans app.py

                print(f"[Slideshow] Preparing to display: {photo_path}")
                
                # --- Contrôle du ventilateur ---
                if GPIO_AVAILABLE:
                    try:
                        temp = psutil.sensors_temperatures()['cpu_thermal'][0].current
                        control_fan(temp)
                    except Exception as e:
                        print(f"Erreur lors de la lecture de la température ou du contrôle du ventilateur : {e}")

                # Vérifier si le fichier est une vidéo ou une image
                is_video = any(photo_path.lower().endswith(ext) for ext in VIDEO_EXTENSIONS)

                # Écrire le chemin de la photo actuelle dans le fichier d'état
                try:
                    with open(CURRENT_PHOTO_FILE, "w") as f:
                        path_to_write = Path(photo_path)
                        if is_video:
                            # Pour une vidéo, on écrit le chemin de sa vignette pour l'aperçu live
                            thumbnail_path = path_to_write.with_name(f"{path_to_write.stem}_thumbnail.jpg")
                            if thumbnail_path.exists():
                                path_to_write = thumbnail_path

                        # Convertir le chemin absolu en chemin relatif au dossier 'static'
                        relative_path = path_to_write.relative_to(Path(BASE_DIR) / 'static')
                        f.write(str(relative_path))
                except Exception as e:
                    print(f"Erreur écriture fichier photo actuelle : {e}")

                if is_video:
                    display_video(screen, photo_path, SCREEN_WIDTH, SCREEN_HEIGHT, config, main_font_loaded, previous_photo_surface, pygame.time.Clock())
                    
                    # --- NOUVEAU: Utilisation de la fonction de réinitialisation centralisée ---
                    # On réinitialise Pygame pour libérer les ressources audio/vidéo.
                    # Le 'break' force la boucle principale à redémarrer, ce qui recharge la police et la config.
                    screen, SCREEN_WIDTH, SCREEN_HEIGHT = reinit_pygame()
                    break # Forcer la boucle principale à redémarrer pour recharger la police et la config
                else: # C'est une image
                    current_pil_image = None # Initialize to None to ensure it's always defined
                    try:
                        # Perform transition if it's not the first photo and transition is enabled
                        if previous_photo_surface is not None and transition_enabled and transition_duration > 0 and transition_type != "none": # Added transition_type check
                            current_pil_image = perform_transition(screen, previous_photo_surface, photo_path, transition_duration, SCREEN_WIDTH, SCREEN_HEIGHT, main_font_loaded, config, transition_type)
                        else:
                            # For the first image or no transition, just load and blit it directly
                            current_pil_image = Image.open(photo_path)
                            if current_pil_image.mode != 'RGB': current_pil_image = current_pil_image.convert('RGB')
                            # For the first image, we need to blit it directly before pan/zoom takes over
                            # This blit is only for the initial display, not part of pan/zoom animation
                            screen.blit(pygame.image.fromstring(current_pil_image.tobytes(), current_pil_image.size, current_pil_image.mode), (0,0))
                            draw_overlay(screen, SCREEN_WIDTH, SCREEN_HEIGHT, config, main_font_loaded)
                            pygame.display.flip()
                    except FileNotFoundError:
                        print(f"[Slideshow] Média non trouvé, il a peut-être été supprimé : {photo_path}. Passage au suivant.")
                        previous_photo_surface = None 
                        continue # Passe au média suivant dans la boucle
                    except Image.UnidentifiedImageError:
                        print(f"[Slideshow] Média corrompu ou non identifiable : {photo_path}. Passage au suivant.")
                        previous_photo_surface = None 
                        continue # Passe au média suivant dans la boucle
                    except Exception as e:
                        print(f"[Slideshow] Error loading or transitioning to photo {photo_path}: {e}")
                        traceback.print_exc()
                        current_pil_image = None # Explicitly set to None on error

                    if current_pil_image: # Only proceed if image was successfully loaded
                        display_photo_with_pan_zoom(screen, current_pil_image, SCREEN_WIDTH, SCREEN_HEIGHT, config, main_font_loaded)
                        previous_photo_surface = screen.copy()
                    else:
                        print(f"[Slideshow] Skipping photo {photo_path} due to loading error.")

    except KeyboardInterrupt:
        print("Arrêt manuel du diaporama.")
    except Exception as e:
        print(f"FATAL ERROR IN SLIDESHOW: {e}")
        traceback.print_exc() # Print full traceback for any unhandled error
    finally:
        set_display_power(False)
        # Nettoyer le fichier d'état à la sortie
        if os.path.exists(CURRENT_PHOTO_FILE):
            os.remove(CURRENT_PHOTO_FILE)
        pygame.quit()
        if GPIO_AVAILABLE:
            GPIO.cleanup()
        print("[Slideshow] Pygame exited cleanly.")

if __name__ == "__main__":
    start_slideshow()
