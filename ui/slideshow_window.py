import os
import random
import time
from tkinter import Tk, Label
from PIL import Image, ImageTk
from utils.image_loader import load_images
from utils.pan_zoom import animate_pan_zoom

SLIDESHOW_INTERVAL = 10  # secondes entre chaque image

def start_slideshow(config):
    root = Tk()
    root.attributes("-fullscreen", True)
    root.configure(bg="black")

    image_label = Label(root, bg="black")
    image_label.pack(expand=True)

    image_paths = load_images(config)

    if not image_paths:
        print("❌ Aucune image trouvée. Fermeture.")
        root.destroy()
        return

    def show_next_image():
        path = random.choice(image_paths)
        try:
            img = Image.open(path)
        except Exception as e:
            print(f"Erreur lors du chargement de {path} : {e}")
            root.after(1000, show_next_image)
            return

        if config.get("pan_zoom", False):
            animate_pan_zoom(img, image_label, root, SLIDESHOW_INTERVAL)
        else:
            img = img.resize((root.winfo_screenwidth(), root.winfo_screenheight()), Image.ANTIALIAS)
            photo = ImageTk.PhotoImage(img)
            image_label.configure(image=photo)
            image_label.image = photo
            root.after(SLIDESHOW_INTERVAL * 1000, show_next_image)

    root.after(100, show_next_image)
    root.mainloop()
