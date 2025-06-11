import os
import random
import time
import pygame
from PIL import Image
import subprocess
from datetime import datetime
import json

# Définition des chemins
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PHOTO_DIR = os.path.join(BASE_DIR, 'static', 'prepared')
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

# Fonction pour afficher une image
def show_image(image_path, screen, screen_width, screen_height):
    try:
        image = Image.open(image_path)
        image = image.convert("RGB")
        image = image.resize((screen_width, screen_height))
        mode = image.mode
        data = image.tobytes()
        pygame_image = pygame.image.fromstring(data, (screen_width, screen_height), mode)
        screen.blit(pygame_image, (0, 0))
        pygame.display.flip()
    except Exception as e:
        print(f"Erreur affichage {image_path} : {e}")

# Boucle principale du diaporama
def start_slideshow():
    config = read_config()
    start_time = config.get("active_start", "06:00")
    end_time = config.get("active_end", "20:00")
    duration = config.get("display_duration", 10)

    pygame.init()
    info = pygame.display.Info()
    SCREEN_WIDTH, SCREEN_HEIGHT = info.current_w, info.current_h
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)

    try:
        while True:
            photos = [f for f in os.listdir(PHOTO_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            if not photos:
                print("Aucune photo trouvée.")
                time.sleep(60)
                continue

            random.shuffle(photos)
            for photo in photos:
                if not is_within_active_hours(start_time, end_time):
                    print("[Info] Hors période active, écran en veille.")
                    screen.fill((0, 0, 0))
                    pygame.display.flip()
                    set_display_power(False)
                    time.sleep(60)
                    break

                set_display_power(True)
                path = os.path.join(PHOTO_DIR, photo)
                show_image(path, screen, SCREEN_WIDTH, SCREEN_HEIGHT)
                time.sleep(duration)

    except KeyboardInterrupt:
        print("Arrêt manuel du diaporama.")
    finally:
        set_display_power(False)
        pygame.quit()

if __name__ == "__main__":
    start_slideshow()
