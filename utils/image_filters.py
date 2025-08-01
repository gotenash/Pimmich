import os
import shutil
from pathlib import Path
from PIL import Image, ImageEnhance, ImageOps, ImageFilter, ImageDraw, ImageFont
import random
import piexif
from datetime import date

POLAROID_FONT_PATH = Path(__file__).parent.parent / "static" / "fonts" / "Caveat-Regular.ttf"

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

def _draw_rounded_rectangle(draw, xy, corner_radius, fill=None):
    """
    Dessine un rectangle avec des coins arrondis.
    """
    x1, y1, x2, y2 = xy
    # Corps du rectangle
    draw.rectangle((x1 + corner_radius, y1, x2 - corner_radius, y2), fill=fill)
    draw.rectangle((x1, y1 + corner_radius, x2, y2 - corner_radius), fill=fill)
    # Coins arrondis
    draw.pieslice((x1, y1, x1 + corner_radius * 2, y1 + corner_radius * 2), 180, 270, fill=fill)
    draw.pieslice((x2 - corner_radius * 2, y1, x2, y1 + corner_radius * 2), 270, 360, fill=fill)
    draw.pieslice((x1, y2 - corner_radius * 2, x1 + corner_radius * 2, y2), 90, 180, fill=fill)
    draw.pieslice((x2 - corner_radius * 2, y2 - corner_radius * 2, x2, y2), 0, 90, fill=fill)

def add_stamp_and_postmark(card_image):
    """
    Ajoute un timbre et une oblitération aléatoires sur une image de carte.
    Prend une image PIL (la carte) et retourne la carte modifiée.
    """
    try:
        stamps_dir = Path('static/stamps')
        if not stamps_dir.is_dir():
            print("[Stamp] Le dossier 'static/stamps' n'existe pas.")
            return card_image

        stamps = [f for f in stamps_dir.iterdir() if f.suffix.lower() == '.png']
        if not stamps:
            print("[Stamp] Aucun timbre (.png) trouvé dans le dossier 'static/stamps'.")
            return card_image

        postcard = card_image.copy()
        random_stamp_path = random.choice(stamps)
        stamp = Image.open(random_stamp_path).convert("RGBA")

        stamp.thumbnail((160, 160), Image.Resampling.LANCZOS)

        draw = ImageDraw.Draw(stamp)
        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except IOError:
            font = ImageFont.load_default()

        # Dessiner des lignes ondulées pour l'oblitération
        for i in range(0, stamp.height, 15):
            draw.line([(0, i), (stamp.width, i + 10)], fill=(0, 0, 0, 100), width=2)
            draw.line([(0, i+5), (stamp.width, i - 5)], fill=(0, 0, 0, 100), width=2)

        # Dessiner un cercle pour la date
        circle_pos = (stamp.width // 4, stamp.height // 4, stamp.width * 3 // 4, stamp.height * 3 // 4)
        draw.ellipse(circle_pos, outline=(0, 0, 0, 150), width=3)

        # Ajouter la date
        date_text = date.today().strftime("%d %b\n%Y").upper()
        draw.multiline_text((stamp.width/2, stamp.height/2), date_text, font=font, fill=(0,0,0,180), anchor="mm", align="center")

        # Coller le timbre sur la carte, avec une marge par rapport au bord de la carte
        margin = 35 # Augmentation de la marge pour plus d'espace
        position = (postcard.width - stamp.width - margin, margin) # Position en haut à droite
        postcard.paste(stamp, position, stamp)

        return postcard

    except Exception as e:
        print(f"[Stamp] Erreur lors de l'ajout du timbre : {e}")
        return card_image

def create_postcard_effect(img_content, caption=None):
    """Crée un effet de carte postale inclinée avec bordure et ombre."""
    # Définir les paramètres de l'effet
    border_size = 35  # Bordure blanche principale augmentée pour un texte plus grand
    
    # --- MODIFICATION DE L'ANGLE ---
    # Inclinaison aléatoire réduite pour une meilleure lisibilité, entre 5 et 10 degrés
    angle = random.uniform(5, 10)
    rotation_angle = random.choice([-1, 1]) * angle
    
    shadow_offset = (15, 15)
    shadow_blur_radius = 25
    shadow_color = (0, 0, 0)

    # --- AJOUT D'UNE BORDURE INTÉRIEURE SUBTILE ---
    # Pour mieux délimiter la photo du cadre blanc, créant un effet de "bord"
    draw = ImageDraw.Draw(img_content)
    draw.rectangle(
        [(0, 0), (img_content.width - 1, img_content.height - 1)],
        outline=(220, 220, 220), # Gris très clair
        width=1
    )

    # --- NOUVELLE LOGIQUE : AJOUT DE LA LÉGENDE DIRECTEMENT SUR LA PHOTO ---
    # Cela garantit que le texte est toujours lisible, quelle que soit l'inclinaison.
    if caption and caption.strip():
        # On travaille sur une copie pour pouvoir utiliser alpha_composite pour la transparence
        img_with_text = img_content.copy()
        if img_with_text.mode != 'RGBA':
            img_with_text = img_with_text.convert('RGBA')

        # Créer une couche transparente pour le bandeau et le texte
        overlay = Image.new('RGBA', img_with_text.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        try:
            # Taille de police relative à la hauteur de l'image pour la robustesse
            font_size = int(img_with_text.height * 0.06)
            font = ImageFont.truetype(str(POLAROID_FONT_PATH), font_size)
        except IOError:
            font = ImageFont.load_default()
        
        # Calculer la hauteur du bandeau en fonction de la taille du texte
        _, text_top, _, text_bottom = font.getbbox(caption)
        text_height = text_bottom - text_top
        band_padding = int(font_size * 0.3)
        band_height = text_height + (band_padding * 2)
        
        # Positionner le bandeau en bas de l'image
        band_y0 = img_with_text.height - band_height
        draw.rectangle([(0, band_y0), (img_with_text.width, img_with_text.height)], fill=(0, 0, 0, 128)) # Noir semi-transparent (50% opacité)
        
        # Positionner et dessiner le texte en blanc, centré dans le bandeau
        text_x = img_with_text.width / 2
        text_y = band_y0 + (band_height / 2)
        draw.text((text_x, text_y), caption, font=font, fill=(255, 255, 255), anchor="mm")
        
        # Combiner l'image et l'overlay, puis reconvertir en RGB
        img_content = Image.alpha_composite(img_with_text, overlay).convert('RGB')

    # 1. Créer la carte avec sa bordure blanche
    card_size = (img_content.width + 2 * border_size, img_content.height + 2 * border_size)
    card = Image.new('RGBA', card_size, (255, 255, 255, 255))
    card.paste(img_content, (border_size, border_size))

    # Ajouter le timbre sur la carte avant de la faire pivoter
    card = add_stamp_and_postmark(card)

    # 2. Incliner la carte
    rotated_card = card.rotate(rotation_angle, expand=True, resample=Image.BICUBIC)

    # 3. Créer l'ombre
    shadow_layer = Image.new('RGBA', rotated_card.size, (0, 0, 0, 0))
    # Créer une forme noire de la même taille que la carte tournée pour l'ombre
    shadow_draw = ImageDraw.Draw(shadow_layer)
    shadow_draw.bitmap((0,0), rotated_card.split()[3], fill=shadow_color) # Utiliser le canal alpha de la carte tournée comme masque
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_blur_radius))

    # 4. Assembler l'ombre et la carte sur une image finale transparente
    final_size = (shadow_layer.width + abs(shadow_offset[0]), shadow_layer.height + abs(shadow_offset[1]))
    final_image = Image.new('RGBA', final_size, (0, 0, 0, 0))
    final_image.paste(shadow_layer, shadow_offset, shadow_layer)
    final_image.paste(rotated_card, (0, 0), rotated_card)

    return final_image

def create_polaroid_effect(image_content):
    """
    Applique un effet de couleur et un cadre Polaroid à une image donnée.
    Prend une image PIL et retourne une nouvelle image PIL.
    """
    # On travaille directement sur une copie de l'image originale pour ne pas modifier les couleurs.
    content_with_frame = image_content.copy()

    # 2. Dessiner le cadre à l'intérieur de l'image
    draw = ImageDraw.Draw(content_with_frame)
    width, height = content_with_frame.size
    frame_color = (255, 253, 248)
    padding_top = int(height * 0.05)
    padding_sides = int(height * 0.05)
    padding_bottom = int(height * 0.18)
    draw.rectangle([0, 0, width, padding_top], fill=frame_color)
    draw.rectangle([0, height - padding_bottom, width, height], fill=frame_color)
    draw.rectangle([0, padding_top, padding_sides, height - padding_bottom], fill=frame_color)
    draw.rectangle([width - padding_sides, padding_top, width, height - padding_bottom], fill=frame_color)
    
    return content_with_frame

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
        # Conserver les métadonnées EXIF pour les réinjecter à la sauvegarde
        exif_bytes = img.info.get('exif')
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
    elif filter_name == 'polaroid_vintage':
        # --- NOUVELLE LOGIQUE POUR CIBLER LE CONTENU DE L'IMAGE ---
        content_bbox = _get_content_bbox(img)
        if not content_bbox:
            print(f"Avertissement: Bounding box non trouvée pour {image_path_str}. Le filtre Polaroid Vintage ne peut être appliqué correctement.")
            img_to_save = img # On ne fait rien pour éviter un résultat incorrect.
        else:
            # 1. Isoler le contenu de l'image
            content_img = img.crop(content_bbox)

            # 2. Appliquer les filtres de couleur vintage au contenu.
            #    MODIFIEZ LES VALEURS CI-DESSOUS POUR AJUSTER L'INTENSITÉ.
            
            # Contraste (1.0 = original, < 1.0 = moins de contraste). Exemple plus léger : 0.9
            content_filtered = ImageEnhance.Contrast(content_img).enhance(0.8)
            
            # Teinte jaune (alpha de 0.0 à 1.0, 0.0 = pas de teinte). Exemple plus léger : 0.15
            yellow_overlay = Image.new('RGB', content_filtered.size, (255, 248, 220))
            content_filtered = Image.blend(content_filtered, yellow_overlay, 0.25)
            
            # Luminosité (1.0 = original, > 1.0 = plus lumineux). Exemple plus léger : 1.05
            content_filtered = ImageEnhance.Brightness(content_filtered).enhance(1.1)
            
            # Teinte bleue dans les ombres (alpha de 0.0 à 1.0). Exemple plus léger : 0.05
            blue_overlay = Image.new('RGB', content_filtered.size, (0, 100, 120))
            content_filtered = Image.blend(content_filtered, blue_overlay, 0.08)

            # 3. Dessiner le cadre Polaroid sur le contenu filtré
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
            
            # 4. Replacer le contenu modifié dans l'image complète
            img_to_save = img.copy()
            img_to_save.paste(content_filtered, content_bbox)
    else:
        raise ValueError(f"Filtre inconnu : '{filter_name}'")

    # Sauvegarde l'image modifiée dans le dossier 'prepared'
    if exif_bytes:
        img_to_save.save(image_path, 'JPEG', quality=90, optimize=True, exif=exif_bytes)
    else:
        img_to_save.save(image_path, 'JPEG', quality=90, optimize=True)

def add_text_to_image(image_path_str, text):
    """
    Ajoute un texte sur n'importe quelle image avec un fond semi-transparent.
    Modifie l'image sur place. Utilise le système de backup pour la réversibilité.
    """
    image_path = Path(image_path_str)
    
    # Logique de backup, similaire à apply_filter_to_image
    try:
        prepared_index = image_path.parts.index('prepared')
        backup_base_path = Path(*image_path.parts[:prepared_index]) / '.backups'
        backup_path = backup_base_path.joinpath(*image_path.parts[prepared_index+1:])
    except ValueError:
        raise ValueError("Le chemin de la photo ne semble pas être dans un dossier 'prepared'.")

    # Crée une sauvegarde si elle n'existe pas
    if not backup_path.exists():
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image_path, backup_path)

    # Toujours partir de la version propre (le backup)
    img = Image.open(backup_path)
    exif_bytes = img.info.get('exif')
    
    # Si le texte est vide, on restaure simplement le backup et on arrête
    if not text or not text.strip():
        img_to_save = img.convert('RGB') # Convertir en RGB pour sauvegarder en JPEG
        if exif_bytes:
            img_to_save.save(image_path, 'JPEG', quality=90, optimize=True, exif=exif_bytes)
        else:
            img_to_save.save(image_path, 'JPEG', quality=90, optimize=True)
        return

    # Convertir l'image de base en RGBA pour le compositing
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    # Créer une couche de dessin transparente
    overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = img.size

    # --- Paramètres du texte et du fond ---
    try:
        font_path = str(POLAROID_FONT_PATH)
        font_size = int(height * 0.05)
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        font = ImageFont.load_default()

    # Utiliser font.getlength() et font.getbbox() pour des métriques précises
    text_width = font.getlength(text)
    _, text_top, _, text_bottom = font.getbbox(text)
    text_height = text_bottom - text_top

    rect_padding = int(font_size * 0.4)
    rect_height = text_height + (rect_padding * 2)
    rect_width = text_width + (rect_padding * 2)
    rect_x1 = (width - rect_width) / 2
    rect_y1 = height - rect_height - (height * 0.03) # Positionné à 3% du bas
    rect_x2 = rect_x1 + rect_width
    rect_y2 = rect_y1 + rect_height
    
    _draw_rounded_rectangle(draw, (rect_x1, rect_y1, rect_x2, rect_y2), int(font_size * 0.3), fill=(255, 255, 255, 180))
    # Utiliser l'ancre "mm" (middle-middle) pour un centrage parfait du texte dans le rectangle
    draw.text((rect_x1 + rect_width / 2, rect_y1 + rect_height / 2), text, font=font, fill=(0, 0, 0, 255), anchor="mm")
    img_composited = Image.alpha_composite(img, overlay)
    img_to_save = img_composited.convert('RGB')
    
    if exif_bytes:
        img_to_save.save(image_path, 'JPEG', quality=90, optimize=True, exif=exif_bytes)
    else:
        img_to_save.save(image_path, 'JPEG', quality=90, optimize=True)

def add_text_to_polaroid(polaroid_path_str, text):
    """
    Ajoute ou met à jour un texte sur une image Polaroid existante.
    """
    polaroid_path = Path(polaroid_path_str)
    if not polaroid_path.exists():
        raise FileNotFoundError(f"L'image Polaroid n'existe pas : {polaroid_path}")

    img = Image.open(polaroid_path)
    # Conserver les métadonnées EXIF pour les réinjecter à la sauvegarde
    exif_bytes = img.info.get('exif')

    draw = ImageDraw.Draw(img)

    # --- Utiliser la 'bounding box' du contenu pour un positionnement correct ---
    content_bbox = _get_content_bbox(img)
    if not content_bbox:
        print(f"Avertissement: Impossible de trouver la 'bounding box' du contenu pour {polaroid_path}. Le texte ne sera pas ajouté.")
        # On ne fait rien si on ne sait pas où est le contenu.
        return

    # Coordonnées du contenu (left, top, right, bottom)
    content_x, content_y, content_right, content_bottom = content_bbox
    content_width = content_right - content_x
    content_height = content_bottom - content_y

    # Définir la couleur du cadre et les dimensions de la marge inférieure
    frame_color = (255, 253, 248) # Doit correspondre à la couleur du cadre
    # Les paddings sont relatifs à la taille du *contenu* polaroid, pas de l'écran
    padding_bottom = int(content_height * 0.18)
    padding_sides = int(content_height * 0.05)

    # 1. Effacer l'ancien texte en redessinant la marge du bas du polaroid
    draw.rectangle([content_x, content_bottom - padding_bottom, content_right, content_bottom], fill=frame_color)

    # 2. Ajouter le nouveau texte si fourni
    if text and text.strip():
        try:
            # La taille de la police est relative à la taille de la marge
            font_size = int(padding_bottom * 0.4)
            font = ImageFont.truetype(str(POLAROID_FONT_PATH), font_size)
            
            # Calculer le centre de la zone de texte du polaroid
            text_area_center_x = (content_x + content_right) / 2
            text_area_center_y = content_bottom - (padding_bottom / 2)
            # Dessiner le texte en utilisant l'ancre 'mm' pour un centrage parfait
            draw.text((text_area_center_x, text_area_center_y), text, font=font, fill=(80, 80, 80), anchor="mm")
        except IOError:
            print(f"Avertissement: Police non trouvée à {POLAROID_FONT_PATH}. Le texte ne sera pas ajouté.")
    # 3. Sauvegarder l'image modifiée en conservant les EXIF
    if exif_bytes:
        img.save(polaroid_path, 'JPEG', quality=95, optimize=True, exif=exif_bytes)
    else:
        img.save(polaroid_path, 'JPEG', quality=95, optimize=True)
