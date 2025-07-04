import os
import random
import time
import pygame
import traceback
import requests
from PIL import Image
import socket
import subprocess, sys
import collections
from datetime import datetime, timedelta
import json
from pathlib import Path
from utils.text_drawer import draw_text_with_outline
from utils.slideshow_manager import HDMI_OUTPUT # Importer la constante centralisée

# Définition des chemins
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREPARED_BASE_DIR = Path(BASE_DIR) / 'static' / 'prepared'
CURRENT_PHOTO_FILE = "/tmp/pimmich_current_photo.txt"
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'config.json')
FILTER_STATES_PATH = os.path.join(BASE_DIR, 'config', 'filter_states.json')
TIDES_CACHE_FILE = Path(BASE_DIR) / 'cache' / 'tides.json'
_icon_cache = {} # Cache pour les icônes météo chargées

# --- Configuration ---
def create_default_config():
    """Crée et retourne un dictionnaire de configuration par défaut, miroir de app.py."""
    return {
        "display_duration": 10,
        "active_start": "07:00",
        "active_end": "22:00",
        "pan_zoom_factor": 1.15,
        "pan_zoom_enabled": False,
        "transition_enabled": True,
        "transition_type": "fade",
        "transition_duration": 1.0,
        "display_sources": ["immich"],
        "show_clock": True,
        "clock_format": "%H:%M",
        "clock_color": "#FFFFFF",
        "clock_outline_color": "#000000",
        "clock_font_size": 72,
        "clock_font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "clock_offset_x": 0,
        "clock_offset_y": 0,
        "clock_position": "center",
        "clock_background_enabled": False,
        "clock_background_color": "#00000080",
        "show_date": True,
        "date_format": "%A %d %B %Y",
        "show_weather": True,
        "weather_api_key": "",
        "weather_city": "Paris",
        "weather_units": "metric",
        "weather_update_interval_minutes": 60,
        "show_tides": False,
        "tide_latitude": "",
        "tide_longitude": "",
        "stormglass_api_key": "",
        "tide_offset_x": 0,
        "tide_offset_y": 0,
    }

# Charger la configuration
def read_config():
    """Charge la configuration, en fusionnant avec les valeurs par défaut."""
    config = create_default_config()
    try:
        with open(CONFIG_PATH, "r") as f:
            loaded_config = json.load(f)
        # Met à jour les valeurs par défaut avec celles du fichier
        for key in config:
            if key in loaded_config:
                config[key] = loaded_config[key]
    except FileNotFoundError:
        print(f"Fichier de configuration '{CONFIG_PATH}' non trouvé. Utilisation des défauts.")
    except json.JSONDecodeError:
        print(f"ERREUR: Le fichier de configuration '{CONFIG_PATH}' est corrompu. Utilisation des défauts.")
    except Exception as e:
        print(f"Erreur lecture config.json : {e}. Utilisation des défauts.")
    return config

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

                print("[Tides] Données de marée valides trouvées dans le cache fichier.")
                # Reconstituer les objets datetime à partir des chaînes ISO
                tide_data = cache_content.get('data', {})
                if tide_data.get('next_high') and tide_data['next_high'].get('time'):
                    tide_data['next_high']['time'] = datetime.fromisoformat(tide_data['next_high']['time']).astimezone()
                if tide_data.get('next_low') and tide_data['next_low'].get('time'):
                    tide_data['next_low']['time'] = datetime.fromisoformat(tide_data['next_low']['time']).astimezone()
                
                # Mettre à jour le cache en mémoire et son timer
                _tides_data = tide_data
                _last_tides_fetch = now
                return tide_data
        except Exception as e:
            print(f"[Tides] Erreur lecture du cache fichier, récupération depuis l'API. Erreur: {e}")

    # 3. Les deux caches sont invalides, appeler l'API
    print("[Tides] Récupération des données de marée depuis l'API StormGlass...")
    _last_tides_fetch = now # Mettre à jour pour éviter les appels répétés en cas d'échec

    try:
        start_time_utc = datetime.utcnow()
        end_time_utc = start_time_utc + timedelta(days=1)

        headers = {'Authorization': api_key}
        params = {'lat': lat, 'lng': lon, 'start': start_time_utc.isoformat(), 'end': end_time_utc.isoformat()}
        
        response = requests.get('https://api.stormglass.io/v2/tide/extremes/point', params=params, headers=headers, timeout=15)
        response.raise_for_status()
        extremes_data = response.json().get('data', [])

        now_utc = datetime.utcnow().replace(tzinfo=None)
        future_extremes = [e for e in extremes_data if datetime.fromisoformat(e['time'].replace('Z', '+00:00')).replace(tzinfo=None) > now_utc]

        next_high_raw = min((e for e in future_extremes if e['type'] == 'high'), key=lambda x: x['time'], default=None)
        next_low_raw = min((e for e in future_extremes if e['type'] == 'low'), key=lambda x: x['time'], default=None)

        _tides_data = {}
        if next_high_raw:
            _tides_data['next_high'] = {'time': datetime.fromisoformat(next_high_raw['time']).astimezone(), 'height': next_high_raw['height']}
        if next_low_raw:
            _tides_data['next_low'] = {'time': datetime.fromisoformat(next_low_raw['time']).astimezone(), 'height': next_low_raw['height']}
        
        # Si aucune marée n'a été trouvée, _tides_data sera vide.
        # On retourne None pour que la logique d'affichage ne tente pas de dessiner.
        if not _tides_data:
            print("[Tides] Aucune marée future trouvée dans les données de l'API pour les prochaines 24h.")
            return None

        data_to_cache = {'data': {}, 'timestamp': datetime.now().isoformat()}
        if _tides_data.get('next_high'):
            data_to_cache['data']['next_high'] = {'time': _tides_data['next_high']['time'].isoformat(), 'height': _tides_data['next_high']['height']}
        if _tides_data.get('next_low'):
            data_to_cache['data']['next_low'] = {'time': _tides_data['next_low']['time'].isoformat(), 'height': _tides_data['next_low']['height']}
        
        with open(TIDES_CACHE_FILE, 'w') as f:
            json.dump(data_to_cache, f, indent=2)
        
        print("[Tides] Données de marée mises à jour et cache sauvegardé.")
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
        _tides_data = None
        return None
 
_hdmi_output = HDMI_OUTPUT
_hdmi_state = None  # variable pour éviter les appels répétitifs

# Gestion de l'alimentation de l'écran via swaymsg
def set_display_power(on: bool):
    global _hdmi_state
    if _hdmi_state == on:
        return
    cmd = ['swaymsg', 'output', _hdmi_output, 'enable' if on else 'disable']
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        _hdmi_state = on
        print(f"Écran {'activé' if on else 'désactivé'} via swaymsg ({_hdmi_output})")
    except Exception as e:
        print(f"Erreur changement état écran via swaymsg : {e}")

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
                icon_size = main_font.get_height()
                icon_key = f"{icon_code}_{icon_size}"

                if icon_key in _icon_cache:
                    icon_surface = _icon_cache[icon_key]
                else:
                    ICON_DIR = PREPARED_BASE_DIR.parent / 'weather_icons'
                    icon_path = ICON_DIR / f"{icon_code}.png"
                    if icon_path.exists():
                        loaded_surface = pygame.image.load(str(icon_path)).convert_alpha()
                        icon_surface = pygame.transform.scale(loaded_surface, (icon_size, icon_size))
                        _icon_cache[icon_key] = icon_surface

                if icon_key in _icon_cache:
                    elements.append({'type': 'icon', 'surface': icon_surface, 'padding': icon_padding})
                
                temp = round(current_weather['main']['temp'])
                description = current_weather['weather'][0]['description'].capitalize()
                weather_str = f"{temp}°C, {description}"
                elements.append({'type': 'text', 'text': " " + weather_str})
            except Exception as e:
                print(f"[Display] Erreur préparation météo actuelle: {e}")

        # Météo du lendemain
        if weather_and_forecast and weather_and_forecast.get('forecast') and len(weather_and_forecast['forecast']) > 0:
            try:
                tomorrow_forecast = weather_and_forecast['forecast'][0]
                
                elements.append({'type': 'text', 'text': separator})

                # Icône pour demain
                tomorrow_icon_code = tomorrow_forecast.get('icon')
                if tomorrow_icon_code:
                    icon_size = main_font.get_height()
                    icon_key = f"{tomorrow_icon_code}_{icon_size}"
                    
                    if icon_key not in _icon_cache:
                        ICON_DIR = PREPARED_BASE_DIR.parent / 'weather_icons'
                        icon_path = ICON_DIR / f"{tomorrow_icon_code}.png"
                        if icon_path.exists():
                            loaded_surface = pygame.image.load(str(icon_path)).convert_alpha()
                            icon_surface = pygame.transform.scale(loaded_surface, (icon_size, icon_size))
                            _icon_cache[icon_key] = icon_surface
                    
                    if icon_key in _icon_cache:
                        elements.append({'type': 'icon', 'surface': _icon_cache[icon_key], 'padding': icon_padding})

                tomorrow_temp_str = f"{tomorrow_forecast['max_temp']}°/{tomorrow_forecast['min_temp']}°"
                tomorrow_weather_str = f"Demain: {tomorrow_temp_str}"
                elements.append({'type': 'text', 'text': " " + tomorrow_weather_str})
            except (IndexError, KeyError) as e:
                print(f"[Display] Erreur préparation météo du lendemain: {e}")

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

            if el['type'] == 'text':
                draw_text_with_outline(screen, el['text'], main_font, text_color, outline_color, (current_x, el_y), anchor="topleft")
            elif el['type'] == 'icon':
                screen.blit(el['surface'], (current_x, el_y))
            
            current_x += el['surface'].get_width()

        # --- Bloc du bas pour les marées ---
        if config.get("show_tides", False):
            tide_data = get_tides(config)
            tide_text = None
            font_to_use = main_font

            if tide_data:
                tide_parts = []
                if tide_data.get('next_high') and tide_data['next_high'].get('time'):
                    tide_parts.append(f"PM: {tide_data['next_high']['time'].strftime('%H:%M')} ({tide_data['next_high']['height']:.1f}m)")
                if tide_data.get('next_low') and tide_data['next_low'].get('time'):
                    tide_parts.append(f"BM: {tide_data['next_low']['time'].strftime('%H:%M')} ({tide_data['next_low']['height']:.1f}m)")
                
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

            # Define pan start and end points (offsets from top-left of scaled image to top-left of screen)
            # Ensure the pan stays within the bounds of the scaled image
            
            # Possible top-left corners of the viewable screen area within the scaled image
            # (x_offset, y_offset)
            possible_start_offsets = [
                (0, 0), # Top-left of scaled image
                (scaled_width - screen_width, 0), # Top-right of scaled image
                (0, scaled_height - screen_height), # Bottom-left of scaled image
                (scaled_width - screen_width, scaled_height - screen_height) # Bottom-right of scaled image
            ]
            
            start_offset = random.choice(possible_start_offsets)
            # Choose an end offset that is different from the start
            end_offset = random.choice([o for o in possible_start_offsets if o != start_offset])

            start_x, start_y = start_offset
            end_x, end_y = end_offset

            clock = pygame.time.Clock()
            start_animation_time = time.time()

            while time.time() - start_animation_time < display_duration:
                elapsed_animation_time = time.time() - start_animation_time
                progress = elapsed_animation_time / display_duration

                # Calculate current pan position
                current_x = int(start_x + (end_x - start_x) * progress)
                current_y = int(start_y + (end_y - start_y) * progress)

                # Blit the portion of the scaled image onto the screen
                screen.blit(scaled_pygame_image, (0, 0), (current_x, current_y, screen_width, screen_height))

                # Draw overlay (clock/date/weather)
                draw_overlay(screen, screen_width, screen_height, config, main_font)
                pygame.display.flip()
                clock.tick(60) # Limit frame rate to 60 FPS for smoother animation
                
    except Exception as e:
        print(f"Erreur affichage photo avec pan/zoom : {e}")
        traceback.print_exc()

# Boucle principale du diaporama
def start_slideshow():
    try: # Global try-except block for robust error handling
        print("[Slideshow] Starting slideshow initialization.")
        config = read_config()
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

        # Chargement police personnalisée (utilisée comme fallback si les polices spécifiques ne sont pas trouvées)
        font_path_config = config.get("clock_font_path", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        clock_font_size_config = int(config.get("clock_font_size", 72)) # Use clock font size for main font
        try:
            main_font_loaded = pygame.font.Font(font_path_config, clock_font_size_config) 
            print(f"[Slideshow] Custom font loaded: {font_path_config}")
        except Exception as e:
            print(f"Erreur chargement police : {e}")
            main_font_loaded = pygame.font.SysFont("Arial", clock_font_size_config)
            print("[Slideshow] Using system font as fallback for main font.")

        try:
            import locale
            locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
            print("[Slideshow] Locale set to fr_FR.UTF-8.")
        except locale.Error:
            print("Avertissement: locale fr_FR.UTF-8 non disponible. Les dates seront en anglais.")
            print("[Slideshow] Locale not set.")

        print("[Slideshow] Entering main slideshow loop.")
        while True:
            config = read_config() # Recharger la config à chaque itération pour prendre en compte les changements
            filter_states = load_filter_states() # Charger les préférences de filtre
            start_time = config.get("active_start", "06:00")
            end_time = config.get("active_end", "20:00")
            duration = config.get("display_duration", 10)
            
            # Initialize transition_duration here to ensure it's always defined within the loop scope
            transition_type = config.get("transition_type", "fade") # Get transition type
            transition_enabled = config.get("transition_enabled", True) # Get transition enabled status
            transition_duration = float(config.get("transition_duration", 1.0)) 
            
            display_sources = config.get("display_sources", ["immich"]) # Nouvelle clé de config
            
            photos = []
            for source in display_sources:
                source_dir = PREPARED_BASE_DIR / source
                if source_dir.is_dir():
                    # Obtenir les photos de base (non-polaroid)
                    base_photos = [f for f in source_dir.iterdir() if f.is_file() and f.suffix.lower() in ('.jpg', '.jpeg', '.png') and not f.name.endswith('_polaroid.jpg')]
                    
                    for photo_path_obj in base_photos:
                        # Créer le chemin relatif utilisé comme clé dans le fichier d'états
                        relative_path_str = f"{source}/{photo_path_obj.name}"
                        active_filter = filter_states.get(relative_path_str)
                        
                        if active_filter == 'polaroid':
                            polaroid_path = photo_path_obj.with_name(f"{photo_path_obj.stem}_polaroid.jpg")
                            if polaroid_path.exists():
                                photos.append(str(polaroid_path))
                            else: # Fallback si la version polaroid n'existe pas
                                photos.append(str(photo_path_obj))
                        else: # Pour tous les autres filtres ou pas de filtre, utiliser la photo de base
                            photos.append(str(photo_path_obj))
            if not photos:
                print("Aucune photo trouvée dans les sources activées. Vérification dans 60 secondes.")
                
                screen.fill((0, 0, 0)) # Fond noir
                
                text_color = parse_color(config.get("clock_color", "#FFFFFF"))
                outline_color = parse_color(config.get("clock_outline_color", "#000000"))
                
                try:
                    font_path = config.get("clock_font_path", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
                    font_size = int(config.get("clock_font_size", 72) * 0.5)
                    message_font = pygame.font.Font(font_path, font_size)
                    ip_font_size = int(config.get("clock_font_size", 72) * 0.65) # Police plus grande pour l'IP
                    ip_font = pygame.font.Font(font_path, ip_font_size)
                    small_font_size = int(config.get("clock_font_size", 72) * 0.35)
                    small_font = pygame.font.Font(font_path, small_font_size)
                except Exception:
                    message_font = pygame.font.SysFont("Arial", 40)
                    ip_font = pygame.font.SysFont("Arial", 50)
                    small_font = pygame.font.SysFont("Arial", 28)

                # --- Logo ---
                logo_surface = None
                logo_height = 0
                logo_spacing = 30
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

                ip_address = get_local_ip()
                messages = [
                    (message_font, "Aucune photo trouvée."),
                    (ip_font, f"Configurez sur : http://{ip_address}:5000"),
                    (small_font, "(Identifiants dans credentials.json à la racine de la SD)"),
                    (message_font, "Nouvelle tentative dans 60 secondes...")
                ]
                
                line_spacing = 20
                text_block_height = sum(font.get_height() for font, text in messages) + (len(messages) - 1) * line_spacing
                total_height = text_block_height + (logo_height + logo_spacing if logo_surface else 0)
                current_y = (SCREEN_HEIGHT - total_height) // 2

                if logo_surface:
                    logo_rect = logo_surface.get_rect(centerx=SCREEN_WIDTH // 2, top=current_y)
                    screen.blit(logo_surface, logo_rect)
                    current_y += logo_height + logo_spacing

                for font, text in messages:
                    text_surface = font.render(text, True, text_color)
                    text_rect = text_surface.get_rect(centerx=SCREEN_WIDTH // 2, top=current_y)
                    draw_text_with_outline(screen, text, font, text_color, outline_color, text_rect.topleft, anchor="topleft")
                    current_y += font.get_height() + line_spacing
                
                pygame.display.flip()

                time.sleep(60)
                continue

            previous_photo_surface = None # Initialize previous_photo_surface before the loop

            random.shuffle(photos)
            for photo_path in photos:
                if not is_within_active_hours(start_time, end_time):
                    print("[Info] Hors période active, écran en veille.")
                    # Nettoyer le fichier d'état quand l'écran s'éteint
                    if os.path.exists(CURRENT_PHOTO_FILE):
                        os.remove(CURRENT_PHOTO_FILE)

                    screen.fill((0, 0, 0))
                    pygame.display.flip()
                    set_display_power(False)
                    while not is_within_active_hours(start_time, end_time):
                        time.sleep(60)
                    break # Sortir de la boucle for pour relancer la boucle while et recharger les photos

                set_display_power(True)
                print(f"[Slideshow] Preparing to display: {photo_path}")

                # Écrire le chemin de la photo actuelle dans le fichier d'état
                try:
                    with open(CURRENT_PHOTO_FILE, "w") as f:
                        # Convertir le chemin absolu en chemin relatif au dossier 'static'
                        relative_path = Path(photo_path).relative_to(Path(BASE_DIR) / 'static')
                        f.write(str(relative_path))
                except Exception as e:
                    print(f"Erreur écriture fichier photo actuelle : {e}")


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
                    print(f"[Slideshow] Photo non trouvée, elle a peut-être été supprimée : {photo_path}. Passage à la suivante.")
                    # On s'assure de ne pas utiliser une ancienne surface pour la prochaine transition
                    previous_photo_surface = None 
                    continue # Passe à la photo suivante dans la boucle
                except Exception as e:
                    print(f"[Slideshow] Error loading or transitioning to photo {photo_path}: {e}")
                    traceback.print_exc()
                    current_pil_image = None # Explicitly set to None on error

                if current_pil_image: # Only proceed if image was successfully loaded
                    # Now display the photo with pan/zoom or statically for its duration
                    display_photo_with_pan_zoom(screen, current_pil_image, SCREEN_WIDTH, SCREEN_HEIGHT, config, main_font_loaded)
                    
                    # Capture the current screen content for the next transition
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

if __name__ == "__main__":
    start_slideshow()
