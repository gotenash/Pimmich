import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.json')

def create_default_config():
    """Crée et retourne un dictionnaire de configuration par défaut. Source unique de vérité."""
    return {
        "level_log": "INFO",
        "display_duration": 10,
        "active_start": "07:00",
        "active_end": "22:00",
        "immich_url": "",
        "immich_token": "",
        "album_name": "",
        "display_width": 1920,
        "display_height": 1080,
        "pan_zoom_factor": 1.15,
        "immich_auto_update": False,
        "immich_update_interval_hours": 24,
        "pan_zoom_enabled": False,
        "transition_enabled": True,
        "transition_type": "fade",
        "transition_duration": 1.0,
        "video_audio_enabled": False,
        "video_audio_output": "auto",
        "video_audio_volume": 100,
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
        # --- Paramètres de la prise connectée ---
        "smart_plug_enabled": False,
        "smart_plug_on_url": "",
        "smart_plug_off_url": "",
        "smart_plug_on_delay": 5,
        "smart_plug_status_url": "",
        "home_assistant_token": "",
        "wifi_ssid": "",
        "wifi_country": "FR",
        "wifi_password": "",
        "skip_initial_auto_import": False,
        "info_display_duration": 5,
        "screen_height_percent": 100,
        "favorite_boost_factor": 2,
        "video_hwdec_enabled": False,
        "telegram_bot_enabled": False,
        "telegram_bot_token": "",
        "telegram_authorized_users": "",
        "voice_control_enabled": False,
        "voice_control_language": "fr",
        "porcupine_access_key": "",
        "voice_control_device_index": "",
        "notification_sound_volume": 80,
        
        # --- NOUVELLES VARIABLES : Métadonnées photo ---
        "show_photo_date": False,
        "photo_date_format": "%Y",
        "country_flag_size": "192x144",
        "country_flag_opacity": 1,
        "show_country_flag": True,        
        "show_photo_location": True,
        "photo_location_format": "city_country",
        "photo_metadata_color": "#ffffff",
        "photo_metadata_outline_color": "#000000",
        "photo_metadata_font_size": 23,
        "photo_metadata_font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "photo_metadata_offset_x": 0,
        "photo_metadata_offset_y": 0,
        "photo_metadata_position": "bottom_left",
        "photo_metadata_background_enabled": True,
        "photo_metadata_background_color": "#00000080",
        
        # --- NOUVELLE VARIABLE : Limite de téléchargement ---
        "max_photos_to_download": {
            "immich": 10,
            "telegram": 100
        }
    }

def load_config():
    """Charge la configuration depuis le fichier et la fusionne avec les valeurs par défaut."""
    default_config = create_default_config()
    
    if not os.path.exists(CONFIG_PATH):
        # Si le fichier de config n'existe pas, on le crée avec les valeurs par défaut.
        save_config(default_config)
        return default_config

    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
        
        # Fusionne la configuration utilisateur avec la configuration par défaut.
        # Cela garantit que les nouvelles clés de configuration sont ajoutées
        # sans écraser les réglages existants de l'utilisateur.
        merged_config = default_config.copy()
        merged_config.update(user_config)
        return merged_config
    except (json.JSONDecodeError, IOError) as e:
        # En cas de fichier corrompu ou illisible, on retourne la config par défaut
        # pour éviter un crash de l'application.
        print(f"Avertissement: Impossible de charger {CONFIG_PATH} ({e}). Utilisation de la configuration par défaut.")
        return default_config

def save_config(config):
    """Sauvegarde la configuration dans un fichier JSON."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
