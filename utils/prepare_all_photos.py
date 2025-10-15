import os
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import json
import pillow_heif
import subprocess, sys
from utils.config import load_config # Import load_config to get screen_height_percent
import piexif
from utils.image_filters import create_polaroid_effect, create_postcard_effect
from utils.exif import get_rotation_angle # Import get_rotation_angle for EXIF rotation
import re
from pathlib import Path

# Configuration
SOURCE_DIR = "static/photos"
# Default target output resolution for prepared images (fallback if screen resolution cannot be detected)
DEFAULT_OUTPUT_WIDTH = 1920
DEFAULT_OUTPUT_HEIGHT = 1080
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv')

# Chemin vers le cache du mappage des descriptions (utilisé par l'import Immich)
DESCRIPTION_MAP_CACHE_FILE = Path("cache") / "immich_description_map.json"
# NOUVEAU: Chemin vers le cache des textes saisis par l'utilisateur
USER_TEXT_MAP_CACHE_FILE = Path("cache") / "user_texts.json"
CANCEL_FLAG = Path('/tmp/pimmich_cancel_import.flag')

def prepare_photo(source_path, dest_path, output_width, output_height, source_type=None, caption=None):
    """Prépare une photo pour l'affichage avec redimensionnement, rotation EXIF et fond flou."""
    config = load_config()
    # Get screen_height_percent from config, default to 100 if not found or invalid
    screen_height_percent = int(config.get("screen_height_percent", "100"))

    # Calculate the effective height for the photo content within the output resolution
    effective_photo_height = int(output_height * (screen_height_percent / 100))

    try:
        # Gestion des fichiers HEIF/HEIC
        if source_path.lower().endswith(('.heic', '.heif')):
            pillow_heif.register_heif_opener()
        
        img = Image.open(source_path)

        # 1. Handle EXIF Orientation
        rotation_angle = get_rotation_angle(img)
        if rotation_angle != 0:
            img = img.rotate(rotation_angle, expand=True)
        
        # Remove EXIF data after rotation to prevent re-interpretation by viewers
        if "exif" in img.info:
            img.info.pop("exif")
        if "icc_profile" in img.info: # Also remove ICC profile as it can sometimes cause issues after rotation
            img.info.pop("icc_profile")

        # Convert to RGB if necessary (for consistency and compatibility with JPEG saving)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')

        # Determine if the image is "portrait-like" relative to the effective display area.
        # This means its aspect ratio is smaller than the display area's aspect ratio.
        img_aspect_ratio = img.width / img.height
        display_area_aspect_ratio = output_width / effective_photo_height

        if img_aspect_ratio < display_area_aspect_ratio:
            # This is a portrait-oriented photo relative to the display area.
            # We will fit its height to effective_photo_height and add a blurred background.

            # Resize the original image to fit within the effective photo height, maintaining aspect ratio
            img_content = img.copy()
            img_content.thumbnail((output_width, effective_photo_height), Image.Resampling.LANCZOS)

            # Create the blurred background image
            # First, resize the original image to fill the entire output_width x output_height area
            # This ensures the blur covers the whole background without black bars from the blur itself
            bg_img = img.copy()
            bg_img.thumbnail((output_width, output_height), Image.Resampling.LANCZOS)
            
            # If the background image is still smaller than the full output size after thumbnail,
            # expand it to fill the full output size (this might crop parts of the image)
            # This is to ensure the blur covers the entire screen.
            if bg_img.width < output_width or bg_img.height < output_height:
                bg_img = bg_img.resize((output_width, output_height), Image.Resampling.LANCZOS)

            # Apply Gaussian blur
            bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=50)) # Radius can be adjusted

            # Create a new blank image for the final output (full screen size)
            final_img = Image.new('RGB', (output_width, output_height), (0, 0, 0))
            
            # Paste the blurred background onto the final image
            final_img.paste(bg_img, (0, 0))

            # Calculate position to center the resized original image (img_content)
            # horizontally and vertically on the final canvas.
            x_offset = (output_width - img_content.width) // 2
            y_offset = (output_height - img_content.height) // 2
            final_img.paste(img_content, (x_offset, y_offset))

        else:
            # Landscape or square photo relative to the display area.
            # Fit its width to OUTPUT_WIDTH or height to effective_photo_height, no blur background, center on black.
            img_content = img.copy()
            img_content.thumbnail((output_width, effective_photo_height), Image.Resampling.LANCZOS)
            final_img = Image.new('RGB', (output_width, output_height), (0, 0, 0))
            
            # Calculate position to center the resized image on the final canvas.
            x_offset = (output_width - img_content.width) // 2
            y_offset = (output_height - img_content.height) // 2
            final_img.paste(img_content, (x_offset, y_offset))
        
        # --- Logique commune pour la création des métadonnées et des versions alternatives ---
        
        # 1. Préparer les métadonnées EXIF avec les coordonnées du contenu
        exif_bytes_to_add = None
        try:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
            bbox_str = f"pimmich_bbox:{x_offset},{y_offset},{img_content.width},{img_content.height}"
            exif_dict["Exif"][piexif.ExifIFD.UserComment] = bbox_str.encode('ascii')
            exif_bytes_to_add = piexif.dump(exif_dict)
        except Exception as exif_e:
            print(f"[EXIF] Avertissement: Impossible de créer les métadonnées pour {os.path.basename(source_path)}: {exif_e}")

        # 2. Générer et sauvegarder la version Polaroid (pour toutes les orientations)
        try:
            polaroid_content = create_polaroid_effect(img_content.copy())
            polaroid_final_img = final_img.copy()
            polaroid_final_img.paste(polaroid_content, (x_offset, y_offset))
            dest_path_obj = Path(dest_path)
            polaroid_dest_path = dest_path_obj.with_name(f"{dest_path_obj.stem}_polaroid.jpg")
            polaroid_final_img.save(polaroid_dest_path, 'JPEG', quality=90, optimize=True, exif=exif_bytes_to_add)
        except Exception as polaroid_e:
            print(f"[Polaroid] Avertissement: Impossible de créer la version Polaroid pour {os.path.basename(source_path)}: {polaroid_e}")

        # Générer et sauvegarder la version Carte Postale.
        # La légende (caption) est utilisée si elle est fournie (ex: depuis Immich ou Telegram).
        # Si cette étape échoue, la photo principale sera quand même disponible.
        try:
            # --- Réduction de la taille de l'image pour la carte postale ---
            # On crée une copie plus petite de l'image de contenu pour s'assurer
            # que la carte postale finale ne sera pas trop grande et laissera des marges
            # pour l'affichage de l'heure et des marées.
            # On la réduit à 85% de la taille de l'écran.
            postcard_img_content = img_content.copy()
            scale_factor = 0.85
            postcard_img_content.thumbnail(
                (int(output_width * scale_factor), int(output_height * scale_factor)), 
                Image.Resampling.LANCZOS
            )

            postcard_content = create_postcard_effect(postcard_img_content, caption=caption)
            # Utiliser une copie de l'image finale (avec son fond flou ou noir) comme base
            # pour la carte postale, au lieu d'un fond noir uni.
            postcard_final_img = final_img.copy()
            postcard_x_offset = (output_width - postcard_content.width) // 2
            postcard_y_offset = (output_height - postcard_content.height) // 2
            postcard_final_img.paste(postcard_content, (postcard_x_offset, postcard_y_offset), postcard_content)
            
            dest_path_obj = Path(dest_path)
            postcard_dest_path = dest_path_obj.with_name(f"{dest_path_obj.stem}_postcard.jpg")
            postcard_final_img.save(postcard_dest_path, 'JPEG', quality=90, optimize=True, exif=exif_bytes_to_add)
        except Exception as postcard_e:
            # Rendre l'erreur plus visible dans les logs pour le débogage.
            # L'importation des autres photos continuera.
            print(f"--- ERREUR CRÉATION CARTE POSTALE pour {os.path.basename(source_path)} ---")
            print(f"Détails de l'erreur : {postcard_e}")
            print("Vérifiez que les polices (static/fonts) et les timbres (static/stamps) sont présents et accessibles.")
            print("--------------------------------------------------------------------")

        # 3. Sauvegarder l'image principale préparée (avec fond flou ou noir)
        img_to_save = final_img
        if exif_bytes_to_add:
            img_to_save.save(dest_path, 'JPEG', quality=85, optimize=True, exif=exif_bytes_to_add)
        else:
            img_to_save.save(dest_path, 'JPEG', quality=85, optimize=True)
            
    except Exception as e:
        # Re-raise with more context
        raise Exception(f"Erreur lors du traitement de l'image '{os.path.basename(source_path)}': {e}")

def prepare_video(source_path, dest_path, output_width, output_height):
    """Prépare une vidéo pour l'affichage et génère sa vignette."""
    
    # --- 1. Préparer la vidéo ---
    try:
        # --- Détection intelligente de l'encodeur matériel ---
        encoder = 'libx264' # Encodeur logiciel par défaut (fallback)
        encoder_params = ['-preset', 'veryfast', '-crf', '23']

        try:
            result = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True, check=True, timeout=5)
            available_encoders = result.stdout
            
            if 'h264_v4l2m2m' in available_encoders:
                encoder = 'h264_v4l2m2m' # Encodeur optimal pour Pi 4/5 (64-bit)
                encoder_params = ['-b:v', '4M']
                print("[Video Prep] Utilisation de l'encodeur matériel optimisé : h264_v4l2m2m")
            elif 'h264_omx' in available_encoders:
                encoder = 'h264_omx' # Encodeur pour Pi 3 et anciens modèles
                encoder_params = ['-b:v', '4M']
                print("[Video Prep] Utilisation de l'encodeur matériel : h264_omx")
            else:
                print("[Video Prep] Aucun encodeur matériel trouvé, utilisation de l'encodeur logiciel (plus lent) : libx264")
                # Forcer un profil compatible avec les décodeurs matériels des RPi (notamment Pi 3)
                encoder_params.extend(['-profile:v', 'high', '-level', '4.0'])
        except Exception as e:
            print(f"[Video Prep] Avertissement : Impossible de détecter les encodeurs ({e}). Utilisation de l'encodeur logiciel par défaut.")

        command = [
            'ffmpeg', '-i', source_path, '-vf', f"scale='min({output_width},iw)':'min({output_height},ih)':force_original_aspect_ratio=decrease,pad={output_width}:{output_height}:(ow-iw)/2:(oh-ih)/2",
            '-c:v', encoder, *encoder_params,
            '-c:a', 'aac', '-b:a', '128k', # Conserver et ré-encoder l'audio
            '-y', dest_path
        ]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as video_e:
        raise Exception(f"Erreur lors du traitement de la vidéo '{os.path.basename(source_path)}' avec ffmpeg: {video_e}")

    # --- 2. Générer la vignette à partir de la vidéo source ---
    thumbnail_path = None
    try:
        dest_path_obj = Path(dest_path)
        thumbnail_path = dest_path_obj.with_name(f"{dest_path_obj.stem}_thumbnail.jpg")
        
        # Commande ffmpeg pour extraire une image à la 1ère seconde
        thumb_command = [
            'ffmpeg', '-i', source_path, '-ss', '00:00:01.000', '-vframes', '1', '-q:v', '2', str(thumbnail_path), '-y'
        ]
        subprocess.run(thumb_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as thumb_e:
        # Ne pas bloquer tout le processus si la vignette échoue, juste afficher un avertissement.
        print(f"[Vignette] Avertissement: Impossible de créer la vignette pour {os.path.basename(source_path)}: {thumb_e}")

def prepare_all_photos_with_progress(screen_width=None, screen_height=None, source_type="unknown", description_map=None):
    """Prépare les photos et retourne des objets structurés (dict) pour le suivi."""
    
    # S'assurer que description_map est un dictionnaire pour éviter les erreurs
    if description_map is None:
        description_map = {}

    # --- NOUVEAU: Charger les textes saisis par l'utilisateur ---
    user_text_map = {}
    if USER_TEXT_MAP_CACHE_FILE.exists():
        try:
            with open(USER_TEXT_MAP_CACHE_FILE, 'r', encoding='utf-8') as f:
                user_text_map = json.load(f)
        except (json.JSONDecodeError, IOError):
            print(f"Avertissement: Impossible de charger le fichier de textes utilisateur {USER_TEXT_MAP_CACHE_FILE}")

    # Déterminer la résolution de sortie réelle, en utilisant les valeurs par défaut si non fournies
    actual_output_width = screen_width if screen_width is not None else DEFAULT_OUTPUT_WIDTH
    actual_output_height = screen_height if screen_height is not None else DEFAULT_OUTPUT_HEIGHT
    
    # --- NOUVEAU: Définir les chemins source et préparé dynamiquement ---
    SOURCE_DIR_FOR_PREP = Path("static") / "photos" / source_type
    PREPARED_SOURCE_DIR = Path("static") / "prepared" / source_type

    if not SOURCE_DIR_FOR_PREP.is_dir():
        yield {"type": "error", "message": f"Le dossier source '{SOURCE_DIR_FOR_PREP}' n'existe pas."}
        return

    PREPARED_SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    # --- Nouvelle logique de synchronisation intelligente ---

    # 1. Obtenir les noms de base des médias sources (sans extension)
    source_files = {f: os.path.splitext(f)[0] for f in os.listdir(SOURCE_DIR_FOR_PREP) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.heif') + VIDEO_EXTENSIONS)}
    source_basenames = set(source_files.values())

    # 2. Obtenir les noms de base des médias déjà préparés
    # Cette logique est plus robuste car elle gère les images, les vidéos et leurs variantes (_polaroid, _thumbnail, etc.)
    prepared_basenames = set()
    if PREPARED_SOURCE_DIR.exists():
        for f in PREPARED_SOURCE_DIR.iterdir():
            if f.is_file():
                # Enlève les suffixes connus pour obtenir le vrai nom de base.
                # ex: 'photo1_polaroid' -> 'photo1', 'video1_thumbnail' -> 'video1', 'photo2' -> 'photo2'
                base = re.sub(r'(_polaroid|_postcard|_thumbnail)$', '', f.stem)
                prepared_basenames.add(base)

    # 3. Déterminer les médias à supprimer (obsolètes)
    # On ne supprime les médias obsolètes que pour les sources qui sont synchronisées (pas pour le smartphone qui est additif)
    basenames_to_delete = set()
    if source_type != "smartphone":
        basenames_to_delete = prepared_basenames - source_basenames
    
    if basenames_to_delete:
        yield {"type": "progress", "stage": "CLEANING", "message": f"Suppression de {len(basenames_to_delete)} médias obsolètes..."}
        for basename in basenames_to_delete:
            # Supprimer tous les fichiers associés à ce nom de base dans le dossier préparé
            for file_to_delete in PREPARED_SOURCE_DIR.glob(f"{basename}*"):
                try:
                    if file_to_delete.is_file():
                        file_to_delete.unlink()
                except OSError as e:
                    yield {"type": "warning", "message": f"Impossible de supprimer {file_to_delete.name} : {e}"}

            # Nettoyer également la sauvegarde correspondante
            backup_dir = PREPARED_SOURCE_DIR.parent.parent / '.backups' / source_type
            if backup_dir.exists():
                for backup_file_to_delete in backup_dir.glob(f"{basename}*"):
                    if backup_file_to_delete.is_file(): backup_file_to_delete.unlink()

    # 4. Déterminer les médias à préparer (nouveaux)
    basenames_to_prepare = source_basenames - prepared_basenames
    files_to_prepare = [f for f, basename in source_files.items() if basename in basenames_to_prepare]
    
    total = len(files_to_prepare)
    
    if total == 0:
        yield {"type": "info", "message": "Aucune nouvelle photo à préparer. Le dossier est à jour."}
        yield {"type": "done", "stage": "PREPARING_COMPLETE", "percent": 100, "message": "Aucune nouvelle photo à préparer."}
        return

    yield {"type": "stats", "stage": "PREPARING_START", "message": f"Début de la préparation de {total} nouvelles photos...", "total": total}

    for i, filename in enumerate(files_to_prepare, start=1):
        # Vérifier si l'annulation a été demandée
        if CANCEL_FLAG.exists():
            yield {"type": "warning", "message": "Préparation annulée par l'utilisateur."}
            return

        src_path = os.path.join(SOURCE_DIR_FOR_PREP, filename)
        
        try:
            base_name, extension = os.path.splitext(filename)
            
            if extension.lower() in VIDEO_EXTENSIONS:
                # C'est une vidéo
                dest_filename = f"{base_name}.mp4"
                dest_path = PREPARED_SOURCE_DIR / dest_filename
                prepare_video(src_path, str(dest_path), actual_output_width, actual_output_height)
                message_type = "vidéo"
            else:
                # C'est une image
                dest_filename = f"{base_name}.jpg"
                dest_path = PREPARED_SOURCE_DIR / dest_filename
                
                # --- MODIFIÉ: Logique de priorité pour la légende ---
                # La clé est le chemin relatif depuis 'prepared', ex: 'immich/photo.jpg'
                relative_path_key = f"{source_type}/{dest_filename}"
                
                # Priorité 1: Texte de l'utilisateur
                caption = user_text_map.get(relative_path_key)
                
                # Priorité 2: Description d'Immich (si aucun texte utilisateur)
                if caption is None:
                    caption = description_map.get(filename)

                prepare_photo(src_path, str(dest_path), actual_output_width, actual_output_height, source_type=source_type, caption=caption)
                message_type = "photo"

            percent = int((i / total) * 100)
            yield {
                "type": "progress", "stage": "PREPARING_PHOTO", "percent": percent, "message": f"Nouveau média préparé ({message_type}) : {filename} ({i}/{total})",
                "current": i, "total": total
            }
        except Exception as e:
            yield {"type": "warning", "message": f"Erreur lors de la préparation de {filename}: {e}"}

    yield {"type": "done", "stage": "PREPARING_COMPLETE", "percent": 100, "message": "Préparation des nouvelles photos terminée."}

def prepare_all_photos(status_callback=None):
    """Version originale avec callback pour compatibilité"""
    for update in prepare_all_photos_with_progress():
        message = update.get("message", str(update))
        if status_callback:
            status_callback(message)
        else:
            print(message)

# Fonction principale pour tests
if __name__ == "__main__":
    print("Test de préparation des photos...")
    prepare_all_photos()
    print("Terminé !")