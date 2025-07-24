import os
import shutil
from pathlib import Path
from PIL import Image, ImageEnhance, ImageOps, ImageFilter, ImageDraw
import piexif

def _get_content_bbox(image_with_exif):
    """Lit les métadonnées EXIF pour trouver la 'bounding box' du contenu."""
    try:
        exif_dict = piexif.load(image_with_exif.info.get('exif', b''))
        user_comment_bytes = exif_dict.get("Exif", {}).get(piexif.ExifIFD.UserComment, b'')
        user_comment = user_comment_bytes.decode('ascii', errors='ignore')
        
        if user_comment.startswith("pimmich_bbox:"):
            coords_str = user_comment.split(":")[1]
            x, y, w, h = map(int, coords_str.split(','))
            return (x, y, x + w, y + h) # Retourne un tuple (left, top, right, bottom)
    except Exception:
        pass # Si erreur de lecture ou format invalide, on retourne None
    return None

def create_polaroid_effect(image_content):
    """
    Applique un effet de couleur et un cadre Polaroid à une image donnée.
    Prend une image PIL et retourne une nouvelle image PIL.
    """
    # 1. Appliquer les filtres de couleur
    content_filtered = ImageEnhance.Contrast(image_content).enhance(0.8)
    yellow_overlay = Image.new('RGB', content_filtered.size, (255, 248, 220))
    content_filtered = Image.blend(content_filtered, yellow_overlay, 0.25)
    content_filtered = ImageEnhance.Brightness(content_filtered).enhance(1.1)
    blue_overlay = Image.new('RGB', content_filtered.size, (0, 100, 120))
    content_filtered = Image.blend(content_filtered, blue_overlay, 0.08)

    # 2. Dessiner le cadre à l'intérieur de l'image
    draw = ImageDraw.Draw(content_filtered)
    width, height = content_filtered.size
    frame_color = (255, 253, 248)
    padding_top = int(height * 0.05)
    padding_sides = int(height * 0.05)
    padding_bottom = int(height * 0.18)
    draw.rectangle([0, 0, width, padding_top], fill=frame_color)
    draw.rectangle([0, height - padding_bottom, width, height], fill=frame_color)
    draw.rectangle([0, padding_top, padding_sides, height - padding_bottom], fill=frame_color)
    draw.rectangle([width - padding_sides, padding_top, width, height - padding_bottom], fill=frame_color)
    
    return content_filtered

def apply_filter_to_image(image_path_str, filter_name):
    """
    Applique un filtre à une image et la sauvegarde.
    Utilise un système de backup pour ne pas appliquer de filtres sur une image déjà filtrée.
    """
    image_path = Path(image_path_str)
    
    # Détermine le chemin de la sauvegarde. Ex: static/prepared/samba/img.jpg -> static/.backups/samba/img.jpg
    try:
        prepared_index = image_path.parts.index('prepared')
        backup_base_path = Path(*image_path.parts[:prepared_index]) / '.backups'
        backup_path = backup_base_path.joinpath(*image_path.parts[prepared_index+1:])
    except ValueError:
        raise ValueError("Le chemin de la photo ne semble pas être dans un dossier 'prepared'.")

    # S'assure que le dossier de backup existe
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    # Crée une sauvegarde si elle n'existe pas
    if not backup_path.exists():
        shutil.copy2(image_path, backup_path)

    # Le traitement se fait toujours à partir de la sauvegarde (l'original préparé)
    source_for_processing = backup_path

    try:
        img = Image.open(source_for_processing)
        if img.mode != 'RGB':
            img = img.convert('RGB')
    except FileNotFoundError:
        raise ValueError(f"Image source introuvable : {source_for_processing}")

    # Applique le filtre sélectionné
    if filter_name == 'original':
        img_to_save = img
    elif filter_name == 'grayscale':
        img_to_save = ImageOps.grayscale(img).convert('RGB')
    elif filter_name == 'sepia':
        grayscale = ImageOps.grayscale(img)
        # Créer une palette sépia. La palette doit être une liste plate de 768 entiers (256 * RGB).
        sepia_palette = []
        for i in range(256):
            r, g, b = int(i * 1.07), int(i * 0.74), int(i * 0.43)
            sepia_palette.extend([min(255, r), min(255, g), min(255, b)])
        grayscale.putpalette(sepia_palette)
        img_to_save = grayscale.convert('RGB')
    elif filter_name == 'vignette':
        img_to_save = img.copy()
        width, height = img_to_save.size
        mask = Image.new('L', (width, height), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((width * 0.05, height * 0.05, width * 0.95, height * 0.95), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=max(width, height) // 7))
        mask = ImageOps.invert(mask)
        black_layer = Image.new('RGB', img.size, (0, 0, 0))
        img_to_save = Image.composite(img, black_layer, mask)
    elif filter_name == 'vintage':
        # 1. Réduire la saturation des couleurs pour un look délavé
        enhancer = ImageEnhance.Color(img)
        img_vintage = enhancer.enhance(0.5) # 0.0: N&B, 1.0: original
        
        # 2. Appliquer une teinte jaune/orangée pour simuler le vieillissement du papier
        sepia_tint = Image.new('RGB', img_vintage.size, (255, 240, 192)) # Teinte sépia clair
        img_to_save = Image.blend(img_vintage, sepia_tint, alpha=0.3) # alpha contrôle l'intensité
    else:
        raise ValueError(f"Filtre inconnu : '{filter_name}'")

    # Sauvegarde l'image modifiée dans le dossier 'prepared'
    img_to_save.save(image_path, 'JPEG', quality=90, optimize=True)
