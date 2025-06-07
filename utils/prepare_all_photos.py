import os
from PIL import Image, ImageFilter
import pygame
from PIL import ExifTags
import json

# Détection de la taille de l'écran
pygame.init()
SCREEN_WIDTH, SCREEN_HEIGHT = pygame.display.Info().current_w, pygame.display.Info().current_h
pygame.quit()

# Répertoires source et destination
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = os.path.join(BASE_DIR, 'static', 'photos')
PREPARED_DIR = os.path.join(BASE_DIR, 'static', 'prepared')

CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'config.json')

def get_screen_height_percent():
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        percent = int(config.get('screen_height_percent', 70))
        return max(10, min(100, percent)) / 100  # sécurité : entre 10% et 100%
    except Exception as e:
        print(f"[Erreur lecture config.json] : {e}")
        return 0.7  # fallback

def prepare_photo(image_path, output_path):
    with Image.open(image_path) as img:
        orientation_value = None

        try:
            exif = img._getexif() if hasattr(img, "_getexif") else None
            if exif:
                orientation_key = next((key for key, value in ExifTags.TAGS.items() if value == 'Orientation'), None)
                if orientation_key and orientation_key in exif:
                    orientation_value = exif[orientation_key]
                    if orientation_value == 3:
                        img = img.rotate(180, expand=True)
                    elif orientation_value == 6:
                        img = img.rotate(-90, expand=True)
                    elif orientation_value == 8:
                        img = img.rotate(90, expand=True)
        except Exception as e:
            print(f"[EXIF ignoré] {image_path} : {e}")

        img = img.convert("RGB")

        # Marges en haut et en bas (ex : 5% en haut et en bas)
        usable_height = int(SCREEN_HEIGHT * get_screen_height_percent())
        margin_top_bottom = (SCREEN_HEIGHT - usable_height) // 2

        w, h = img.size
        img_ratio = w / h
        screen_ratio = SCREEN_WIDTH / usable_height

        treat_as_portrait = img_ratio < 1 or img_ratio < screen_ratio * 0.95

        if treat_as_portrait:
            background = img.resize((SCREEN_WIDTH, SCREEN_HEIGHT)).filter(ImageFilter.GaussianBlur(30))
            new_height = usable_height
            new_width = int(new_height * img_ratio)
            img_resized = img.resize((new_width, new_height))
            offset = ((SCREEN_WIDTH - new_width) // 2, margin_top_bottom)
            background.paste(img_resized, offset)
            background.save(output_path)
        else:
            img.thumbnail((SCREEN_WIDTH, usable_height))
            background = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (0, 0, 0))
            offset = ((SCREEN_WIDTH - img.width) // 2, (SCREEN_HEIGHT - img.height) // 2)
            background.paste(img, offset)
            background.save(output_path)


def prepare_all_photos():
    if not os.path.isdir(SOURCE_DIR):
        print(f"Le dossier source n'existe pas : {SOURCE_DIR}")
        return

    os.makedirs(PREPARED_DIR, exist_ok=True)

    photos = [f for f in os.listdir(SOURCE_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]

    for filename in photos:
        src_path = os.path.join(SOURCE_DIR, filename)
        dest_path = os.path.join(PREPARED_DIR, filename)
        try:
            prepare_photo(src_path, dest_path)
            print(f"[Préparé] {filename}")
        except Exception as e:
            print(f"[Erreur] {filename} : {e}")

if __name__ == '__main__':
    prepare_all_photos()
