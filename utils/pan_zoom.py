import time
from PIL import Image, ImageTk

import pygame


def pan_and_zoom_effect(screen, image_path, duration=8):
    img = pygame.image.load(image_path).convert()
    screen_rect = screen.get_rect()
    img = pygame.transform.smoothscale(img, (screen_rect.width * 2, screen_rect.height * 2))
    
    start_time = time.time()
    while time.time() - start_time < duration:
        elapsed = time.time() - start_time
        progress = elapsed / duration
        x = int((1 - progress) * (img.get_width() - screen_rect.width))
        y = int((1 - progress) * (img.get_height() - screen_rect.height))
        screen.blit(img, (0, 0), (x, y, screen_rect.width, screen_rect.height))
        pygame.display.flip()
        pygame.time.delay(30)

def animate_pan_zoom(image, label_widget, root, duration):
    """
    Anime un effet pan & zoom sur l'image affichée dans label_widget.
    
    Args:
        image (PIL.Image): Image source.
        label_widget (tkinter.Label): Label où afficher l'image.
        root (tkinter.Tk): Fenêtre principale pour gérer le timer.
        duration (int): Durée en secondes de l'animation.
    """
    width, height = root.winfo_screenwidth(), root.winfo_screenheight()
    steps = duration * 30  # approx 30fps
    zoom_start = 1.0
    zoom_end = 1.2

    # Coordonnées de départ pour le pan (0 = coin haut gauche)
    start_x = 0
    start_y = 0

    # Coordonnées de fin pour le pan (par exemple un léger déplacement)
    end_x = int(width * 0.1)
    end_y = int(height * 0.1)

    for step in range(steps):
        # Calcul de zoom progressif
        zoom = zoom_start + (zoom_end - zoom_start) * (step / steps)
        # Calcul du déplacement progressif
        x = int(start_x + (end_x - start_x) * (step / steps))
        y = int(start_y + (end_y - start_y) * (step / steps))

        # Calcul de la taille à afficher
        new_width = int(width * zoom)
        new_height = int(height * zoom)

        # Redimensionner l'image avec zoom
        resized = image.resize((new_width, new_height), Image.LANCZOS)

        # Découper la zone visible selon le pan
        crop_box = (x, y, x + width, y + height)
        cropped = resized.crop(crop_box)

        # Convertir en image Tkinter
        photo = ImageTk.PhotoImage(cropped)

        # Mise à jour du label
        label_widget.configure(image=photo)
        label_widget.image = photo

        root.update()
        time.sleep(1 / 30)  # 30fps

