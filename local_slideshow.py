import os
import sys
import time
import json
import random
from datetime import datetime
from PIL import Image, ImageFilter
import pygame
import subprocess

CONFIG_PATH = os.path.join("config", "config.json")
PHOTOS_PATH = os.path.join("static", "photos")

def read_config():
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Erreur lecture config.json : {e}")
        return {}

def show_configuration_missing_slide():
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    screen.fill((255, 255, 255))

    font_large = pygame.font.SysFont("Arial", 60)
    font_small = pygame.font.SysFont("Arial", 40)

    try:
        logo = pygame.image.load("static/pimmich_logo.png")
        logo = pygame.transform.smoothscale(logo, (200, 200))
        screen.blit(logo, (screen.get_width() - 220, 20))
    except Exception as e:
        print(f"Erreur chargement logo : {e}")

    text1 = font_large.render("Configuration manquante", True, (200, 0, 0))
    text2 = font_small.render("Connecte-toi à l'adresse suivante :", True, (0, 0, 0))

    try:
        ip = get_local_ip()
        text3 = font_small.render(f"http://{ip}:5000/configure", True, (0, 102, 204))
    except:
        text3 = font_small.render("Adresse IP non trouvée", True, (128, 128, 128))

    screen.blit(text1, text1.get_rect(center=(960, 300)))
    screen.blit(text2, text2.get_rect(center=(960, 500)))
    screen.blit(text3, text3.get_rect(center=(960, 580)))

    pygame.display.flip()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return

def is_within_active_hours(start, end):
    now = datetime.now().time()
    try:
        start_time = datetime.strptime(start, "%H:%M").time()
        end_time = datetime.strptime(end, "%H:%M").time()
    except Exception as e:
        print(f"Erreur de format d'heure : {e}")
        return True

    if start_time <= end_time:
        return start_time <= now <= end_time
    else:
        return now >= start_time or now <= end_time

def set_display_power(state):
    value = "1" if state else "0"
    subprocess.run(["vcgencmd", "display_power", value])
    print(f"[Power] Écran {'activé' if state else 'éteint'} (display_power={value})")

def prepare_image(img_path, screen_size):
    try:
        with Image.open(img_path) as img:
            img = img.convert("RGB")
            screen_w, screen_h = screen_size
            img_w, img_h = img.size
            aspect_img = img_w / img_h
            aspect_screen = screen_w / screen_h

            if aspect_img < aspect_screen:
                blurred = img.resize(screen_size, Image.LANCZOS).filter(ImageFilter.GaussianBlur(20))
                result = blurred.copy()
                img.thumbnail(screen_size, Image.LANCZOS)
                offset = ((screen_w - img.width) // 2, (screen_h - img.height) // 2)
                result.paste(img, offset)
                return result
            else:
                img.thumbnail(screen_size, Image.LANCZOS)
                background = Image.new("RGB", screen_size, (0, 0, 0))
                offset = ((screen_w - img.width) // 2, (screen_h - img.height) // 2)
                background.paste(img, offset)
                return background
    except Exception as e:
        print(f"Erreur préparation image {img_path} : {e}")
        return None

def display_photos():
    config = read_config()
    start_time = config.get("active_start", "00:00")
    end_time = config.get("active_end", "23:59")
    duration = int(config.get("display_duration", 10))  # valeur par défaut = 10 secondes

    pygame.init()
    pygame.mouse.set_visible(False)
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    screen_size = screen.get_size()
    print(f"[Init] Taille écran détectée : {screen_size}")
    print(f"[Config] Durée d'affichage = {duration} sec")

    clock = pygame.time.Clock()

    while True:
        within_hours = is_within_active_hours(start_time, end_time)
        set_display_power(within_hours)

        if not within_hours:
            print("[Info] Hors heures d'activité, fond noir.")
            screen.fill((0, 0, 0))
            pygame.display.flip()
            time.sleep(60)
            continue

        files = [f for f in os.listdir(PHOTOS_PATH) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        if not files:
            print("[Alerte] Aucun fichier image trouvé.")
            time.sleep(30)
            continue

        random.shuffle(files)

        for filename in files:
            if not is_within_active_hours(start_time, end_time):
                print("[Info] Fin de la période active détectée.")
                screen.fill((0, 0, 0))
                pygame.display.flip()
                break

            img_path = os.path.join(PHOTOS_PATH, filename)
            print(f"[Affichage] {img_path}")

            image = prepare_image(img_path, screen_size)
            if image:
                pygame_image = pygame.image.frombuffer(image.tobytes(), image.size, image.mode)
                screen.blit(pygame_image, (0, 0))
                pygame.display.flip()
            else:
                screen.fill((60, 60, 60))
                pygame.display.flip()
                print("[Erreur] Image non affichée, fond neutre utilisé.")

            # Pause en prenant en compte la durée de config.json
            for _ in range(duration * 10):  # 0.1s * 10 = 1s
                if not is_within_active_hours(start_time, end_time):
                    print("[Info] Interruption pendant l'affichage (fin d'heure).")
                    screen.fill((0, 0, 0))
                    pygame.display.flip()
                    break
                time.sleep(0.1)

            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    print("[Interruption] ESC pressé. Fermeture.")
                    pygame.quit()
                    sys.exit()

            clock.tick(1)

if __name__ == "__main__":
    display_photos()
