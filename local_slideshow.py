import os
import random
import time
import pygame
import traceback
import requests
from PIL import Image
import subprocess
from datetime import datetime
import json
from pathlib import Path

# Définition des chemins
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREPARED_BASE_DIR = Path(BASE_DIR) / 'static' / 'prepared'
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'config.json')

# Charger la configuration
def read_config():
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Erreur lecture config.json : {e}")
        return {}

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

# Détecter automatiquement la sortie HDMI active via swaymsg
def get_hdmi_output_name():
    try:
        result = subprocess.run(['swaymsg', '-t', 'get_outputs'], capture_output=True, text=True, check=True)
        outputs = json.loads(result.stdout)
        for output in outputs:
            if output.get('name', '').startswith('HDMI') and output.get('active', False):
                return output['name']
        for output in outputs:
            if output.get('name', '').startswith('HDMI'):
                return output['name']
    except Exception as e:
        print(f"Erreur détection sortie HDMI : {e}")
    return "HDMI-A-1"  # fallback

# --- Gestion de la météo ---
_weather_data = None
_last_weather_fetch = None

def get_weather(config):
    global _weather_data, _last_weather_fetch
    
    api_key = config.get("weather_api_key")
    city = config.get("weather_city")
    units = config.get("weather_units", "metric")
    try:
        # Assurer que la valeur est un entier, car elle vient d'un formulaire HTML
        interval_minutes = int(config.get("weather_update_interval_minutes", 30))
    except (ValueError, TypeError):
        interval_minutes = 30 # Fallback en cas de valeur non valide

    if not api_key or not city:
        print("[Weather] Clé API ou ville manquante dans la configuration.")
        return None

    now = datetime.now()
    if _last_weather_fetch and (now - _last_weather_fetch).total_seconds() < interval_minutes * 60:
        # print("[Weather] Utilisation des données météo en cache.")
        return _weather_data

    print("[Weather] Tentative de récupération des données météo...")
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units={units}&lang=fr"
        print(f"[Weather] URL: {url}")
        response = requests.get(url, timeout=10)
        print(f"[Weather] Réponse reçue, statut: {response.status_code}")
        response.raise_for_status()
        _weather_data = response.json()
        _last_weather_fetch = now
        print(f"[Weather] Météo mise à jour pour {city}: {_weather_data.get('main', {}).get('temp')}°C")
        return _weather_data
    except requests.exceptions.RequestException as e:
        print(f"[Weather] Erreur réseau lors de la récupération de la météo : {e}")
        _last_weather_fetch = now 
        return None
    except Exception as e:
        print(f"[Weather] Erreur générale lors de la récupération de la météo : {e}")
        _last_weather_fetch = now 
        return None

_hdmi_output = get_hdmi_output_name()
_hdmi_state = None  # variable pour éviter les appels répétitifs

# Gestion de l'alimentation de l'écran via swaymsg
def set_display_power(on: bool):
    global _hdmi_state
    if _hdmi_state == on:
        return
    cmd = ['swaymsg', 'output', _hdmi_output, 'enable' if on else 'disable']
    try:
        subprocess.run(cmd, check=True)
        _hdmi_state = on
        print(f"Écran {'activé' if on else 'désactivé'} via swaymsg ({_hdmi_output})")
    except Exception as e:
        print(f"Erreur changement état écran via swaymsg : {e}")

# Affiche un texte avec contour pour meilleure lisibilité
def draw_text_with_outline(screen, text, font, text_color, outline_color, pos, anchor="center"):
    # Rendu des surfaces une seule fois
    text_surface = font.render(text, True, text_color)
    outline_surface = font.render(text, True, outline_color)

    # Obtenir le rectangle pour le positionnement
    text_rect = text_surface.get_rect(**{anchor: pos})
    
    # Dessiner le contour en décalant la surface
    offsets = [(-2, -2), (-2, 2), (2, -2), (2, 2)]
    for ox, oy in offsets:
        screen.blit(outline_surface, text_rect.move(ox, oy))
    
    # Dessiner le texte principal
    screen.blit(text_surface, text_rect)

# Helper function to parse hex colors (including alpha)
def parse_color(hex_color):
    hex_color = str(hex_color).lstrip('#')
    if len(hex_color) == 6: # RRGGBB
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    elif len(hex_color) == 8: # RRGGBBAA
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4, 6))
    else:
        return (255, 255, 255) # Default to white if invalid

# New function to draw the overlay elements (clock, date, weather)
def draw_overlay(screen, screen_width, screen_height, config, main_font):

    if config.get("show_clock", False):
        # --- Configuration (basée sur les paramètres de l'horloge pour un style unifié) ---
        text_color = parse_color(config.get("clock_color", "#FFFFFF"))
        outline_color = parse_color(config.get("clock_outline_color", "#000000"))
        clock_font_size = int(config.get("clock_font_size", 72))

        separator = "  |  "
        icon_padding = 10

        # --- Préparation des éléments à afficher ---
        elements = []

        # Heure
        time_str = datetime.now().strftime(config.get("clock_format", "%H:%M"))
        elements.append({'type': 'text', 'text': time_str})

        # Date
        if config.get("show_date", False):
            date_str = datetime.now().strftime(config.get("date_format", "%A %d %B %Y"))
            elements.append({'type': 'text', 'text': separator + date_str})

        # Météo
        if config.get("show_weather", False):
            weather_data = get_weather(config)
            if weather_data:
                try:
                    # Icône
                    icon_code = weather_data['weather'][0]['icon']
                    icon_size = main_font.get_height() # L'icône s'adapte à la hauteur de la police
                    ICON_DIR = PREPARED_BASE_DIR.parent / 'weather_icons'
                    ICON_DIR.mkdir(exist_ok=True)
                    icon_path = ICON_DIR / f"{icon_code}.png"
                    if not icon_path.exists():
                        icon_url = f"http://api.openweathermap.org/img/wn/{icon_code}@2x.png"
                        icon_response = requests.get(icon_url, timeout=10) # Increased timeout for icon download
                        icon_response.raise_for_status()
                        with open(icon_path, "wb") as f:
                            f.write(icon_response.content)
                    if icon_path.exists():
                        icon_surface = pygame.image.load(str(icon_path)).convert_alpha()
                        icon_surface = pygame.transform.scale(icon_surface, (icon_size, icon_size))
                        elements.append({'type': 'icon', 'surface': icon_surface, 'padding': icon_padding})
                    
                    # Texte météo
                    temp = round(weather_data['main']['temp'])
                    description = weather_data['weather'][0]['description'].capitalize()
                    weather_str = f"{temp}°C, {description}"
                    elements.append({'type': 'text', 'text': " " + weather_str}) # Espace avant le texte
                except Exception as e:
                    print(f"[Display] Erreur préparation météo: {e}")

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
        
        block_y = (screen_height // 2 + offset_y) - (max_height // 2)

        # --- Dessin du fond semi-transparent ---
        if config.get("clock_background_enabled", False):
            bg_color_hex = config.get("clock_background_color", "#00000080")
            bg_color_rgba = parse_color(bg_color_hex)
            
            # Ensure alpha is present, default to 255 if not provided in hex (e.g., #RRGGBB)
            if len(bg_color_rgba) == 3:
                bg_color_rgba = bg_color_rgba + (255,) # Add full opacity
            
            # Créer une surface qui s'étend sur toute la largeur de l'écran
            bg_surface = pygame.Surface((screen_width, max_height + 20), pygame.SRCALPHA) # Utiliser screen_width
            bg_surface.fill(bg_color_rgba)
            
            # Afficher le fond à la position y du bloc de texte, mais en partant de x=0
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

# Fonction pour afficher une image et l'heure
def show_image(image_path, screen, screen_width, screen_height, config, main_font):
    """Affiche une image préparée et l'heure sur l'écran."""
    try:
        # Open the prepared image. It should already be at the correct resolution (e.g., 1920x1080)
        # and have the blur/padding applied if necessary by prepare_all_photos.py.
        image = Image.open(image_path)
        
        # Ensure it's in a compatible mode for Pygame (RGB is generally safe)
        if image.mode != 'RGB':
            image = image.convert('RGB')

        pan_zoom_enabled = config.get("pan_zoom_enabled", False)
        display_duration = config.get("display_duration", 10)
        
        # Always blit the base image first (this will be overwritten by animation if enabled)
        pygame_image_base = pygame.image.fromstring(image.tobytes(), image.size, image.mode)
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
            scaled_pil_image = image.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
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
                draw_overlay(screen, screen_width, screen_height, config, main_font) # Pass main_font

                pygame.display.flip()
                clock.tick(60) # Limit frame rate to 60 FPS for smoother animation
                
    except Exception as e:
        print(f"Erreur affichage {image_path} : {e}")
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
            start_time = config.get("active_start", "06:00")
            end_time = config.get("active_end", "20:00")
            duration = config.get("display_duration", 10)
            display_sources = config.get("display_sources", ["immich"]) # Nouvelle clé de config
            
            photos = []
            for source in display_sources: # This loop should be inside the while True loop
                source_dir = PREPARED_BASE_DIR / source
                if source_dir.is_dir():
                    photos.extend([str(f) for f in source_dir.iterdir() if f.is_file() and f.suffix.lower() in ('.jpg', '.jpeg', '.png')])

            if not photos:
                print("Aucune photo trouvée dans les sources activées. Vérification dans 60 secondes.")
                time.sleep(60)
                continue

            random.shuffle(photos)
            for photo_path in photos:
                if not is_within_active_hours(start_time, end_time):
                    print("[Info] Hors période active, écran en veille.")
                    screen.fill((0, 0, 0))
                    pygame.display.flip()
                    set_display_power(False)
                    while not is_within_active_hours(start_time, end_time):
                        time.sleep(60)
                    break # Sortir de la boucle for pour relancer la boucle while et recharger les photos

                set_display_power(True)
                print(f"[Slideshow] Displaying image: {photo_path}")
                show_image(photo_path, screen, SCREEN_WIDTH, SCREEN_HEIGHT, config, main_font_loaded) # Pass main_font_loaded
                print(f"[Slideshow] Image displayed. Sleeping for {duration} seconds.")
                # time.sleep(duration) is now handled by the show_image function itself for pan/zoom

    except KeyboardInterrupt:
        print("Arrêt manuel du diaporama.")
    except Exception as e:
        print(f"FATAL ERROR IN SLIDESHOW: {e}")
        traceback.print_exc() # Print full traceback for any unhandled error
    finally:
        set_display_power(False)
        pygame.quit()

if __name__ == "__main__":
    start_slideshow()
