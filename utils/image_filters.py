from PIL import Image, ImageFilter, ImageOps, ImageDraw
from pathlib import Path
import shutil

def _apply_grayscale(image):
    """Applique un filtre noir et blanc."""
    return ImageOps.grayscale(image)

def _apply_sepia(image):
    """Applique un filtre sépia."""
    # Travailler sur une copie pour éviter de modifier l'original en place
    img_copy = image.copy()
    
    if img_copy.mode != 'RGB':
        img_copy = img_copy.convert('RGB')
    
    width, height = img_copy.size
    pixels = img_copy.load()

    for py in range(height):
        for px in range(width):
            r, g, b = pixels[px, py] # Lire depuis l'objet pixels est plus efficace
            
            tr = int(0.393 * r + 0.769 * g + 0.189 * b)
            tg = int(0.349 * r + 0.686 * g + 0.168 * b)
            tb = int(0.272 * r + 0.534 * g + 0.131 * b)
            
            pixels[px, py] = (min(255, tr), min(255, tg), min(255, tb))

    return img_copy

def _apply_vignette(image):
    """Applique un effet de vignettage à l'image."""
    # S'assurer que l'image est en mode RGBA pour la composition alpha
    img_copy = image.copy().convert("RGBA")

    # Créer un masque radial pour le vignettage
    mask = Image.new("L", img_copy.size, 0) # 'L' pour 8-bit pixels, black and white
    draw = ImageDraw.Draw(mask)

    # Dessiner une ellipse blanche au centre (la zone qui restera claire)
    x0, y0 = int(img_copy.width * 0.15), int(img_copy.height * 0.15)
    x1, y1 = img_copy.width - x0, img_copy.height - y0
    draw.ellipse((x0, y0, x1, y1), fill=255)

    # Flouter le masque pour créer un dégradé doux
    mask = mask.filter(ImageFilter.GaussianBlur(radius=img_copy.width // 7))

    # Créer une couche de vignettage noire et semi-transparente
    # On inverse le masque pour que le centre soit transparent et les bords opaques
    vignette_layer = Image.new("RGBA", img_copy.size, (0, 0, 0, 0))
    vignette_layer.putalpha(mask.point(lambda i: 255 - i))

    # Appliquer la couche de vignettage sur l'image
    return Image.alpha_composite(img_copy, vignette_layer)

def apply_filter_to_image(image_path_str, filter_name):
    """
    Ouvre une image, applique un filtre et l'enregistre en écrasant l'original.
    Gère également la restauration à l'original.
    """
    image_path = Path(image_path_str)
    # Le nom du dossier de backup est basé sur le nom de la source (parent de l'image)
    backup_dir = image_path.parent.parent.parent / '.backups' / image_path.parent.name
    backup_path = backup_dir / image_path.name

    # Si on demande de revenir à l'original
    if filter_name == 'original':
        if backup_path.exists():
            shutil.copy2(backup_path, image_path)
            backup_path.unlink() # Supprime la sauvegarde après restauration
        # Si pas de backup, on ne fait rien (l'image est déjà l'originale)
        return

    filters = {
        'grayscale': _apply_grayscale,
        'sepia': _apply_sepia,
        'vignette': _apply_vignette,
    }

    if filter_name not in filters:
        raise ValueError(f"Filtre inconnu : '{filter_name}'.")

    # Créer une sauvegarde si elle n'existe pas déjà (avant la première modification)
    if not backup_path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image_path, backup_path)

    with Image.open(image_path) as img:
        # Conserver les données EXIF si possible
        exif = img.info.get('exif')

        filtered_img = filters[filter_name](img)

        # Pour assurer la compatibilité, on convertit l'image en RGB avant de la sauvegarder
        # en tant que JPEG, ce qui est le format standard pour les photos préparées.
        if filtered_img.mode != 'RGB':
            filtered_img = filtered_img.convert('RGB')

        # Sauvegarder l'image en écrasant l'ancienne, en format JPEG
        save_kwargs = {
            'quality': 85,
            'optimize': True
        }
        if exif:
            save_kwargs['exif'] = exif
        
        filtered_img.save(image_path, 'JPEG', **save_kwargs)