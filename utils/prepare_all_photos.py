import os
from PIL import Image, ImageFilter # Import ImageFilter for blurring
import pillow_heif
import subprocess
from utils.config import load_config # Import load_config to get screen_height_percent
import piexif
from utils.image_filters import create_polaroid_effect
from utils.exif import get_rotation_angle # Import get_rotation_angle for EXIF rotation
from pathlib import Path

# Configuration
SOURCE_DIR = "static/photos"
# Default target output resolution for prepared images (fallback if screen resolution cannot be detected)
DEFAULT_OUTPUT_WIDTH = 1920
DEFAULT_OUTPUT_HEIGHT = 1080
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv')

def prepare_photo(source_path, dest_path, output_width, output_height):
    """Prépare une photo pour l'affichage avec redimensionnement, rotation EXIF et fond flou."""
    config = load_config()
    # Get screen_height_percent from config, default to 100 if not found or invalid
    screen_height_percent = int(config.get("screen_height_percent", "100"))

    exif_bytes_to_add = None # Initialiser les données EXIF à ajouter
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
            img_to_save = final_img

            # --- NOUVEAU: Générer et sauvegarder la version Polaroid ---
            try:
                polaroid_content = create_polaroid_effect(img_content.copy())
                polaroid_final_img = final_img.copy()
                polaroid_final_img.paste(polaroid_content, (x_offset, y_offset))
                
                # Construire le chemin pour la version polaroid
                dest_path_obj = Path(dest_path)
                polaroid_dest_path = dest_path_obj.with_name(f"{dest_path_obj.stem}_polaroid.jpg")
                
                polaroid_final_img.save(polaroid_dest_path, 'JPEG', quality=90, optimize=True)
            except Exception as polaroid_e:
                print(f"[Polaroid] Avertissement: Impossible de créer la version Polaroid pour {os.path.basename(source_path)}: {polaroid_e}")
            # --- NOUVEAU: Préparer les métadonnées EXIF avec les coordonnées du contenu ---
            try:
                exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
                # Stocker les coordonnées dans le champ UserComment (non-standard mais sûr)
                # Format: "pimmich_bbox:x,y,w,h"
                bbox_str = f"pimmich_bbox:{x_offset},{y_offset},{img_content.width},{img_content.height}"
                exif_dict["Exif"][piexif.ExifIFD.UserComment] = bbox_str.encode('ascii')
                exif_bytes_to_add = piexif.dump(exif_dict)
            except Exception as exif_e:
                print(f"[EXIF] Avertissement: Impossible de créer les métadonnées pour {os.path.basename(source_path)}: {exif_e}")

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
            img_to_save = final_img
        
        # Save the prepared image as JPEG
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
        # Commande ffmpeg pour redimensionner la vidéo tout en gardant le ratio.
        # On conserve systématiquement la piste audio et on la ré-encode en AAC pour une compatibilité maximale.
        command = [
            'ffmpeg', '-i', source_path, '-vf', f"scale='min({output_width},iw)':'min({output_height},ih)':force_original_aspect_ratio=decrease,pad={output_width}:{output_height}:(ow-iw)/2:(oh-ih)/2",
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k', # Conserver et ré-encoder l'audio
            '-y', dest_path
        ]

        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as video_e:
        raise Exception(f"Erreur lors du traitement de la vidéo '{os.path.basename(source_path)}' avec ffmpeg: {video_e}")

    # --- 2. Générer la vignette à partir de la vidéo source ---
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

def prepare_all_photos_with_progress(screen_width=None, screen_height=None, source_type="unknown"):
    """Prépare les photos et retourne des objets structurés (dict) pour le suivi."""
    # Déterminer la résolution de sortie réelle, en utilisant les valeurs par défaut si non fournies
    actual_output_width = screen_width if screen_width is not None else DEFAULT_OUTPUT_WIDTH
    actual_output_height = screen_height if screen_height is not None else DEFAULT_OUTPUT_HEIGHT

    PREPARED_SOURCE_DIR = Path("static") / "prepared" / source_type

    if not os.path.isdir(SOURCE_DIR):
        yield {"type": "error", "message": f"Le dossier source '{SOURCE_DIR}' n'existe pas."}
        return

    PREPARED_SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    # --- Nouvelle logique de synchronisation intelligente ---

    # 1. Obtenir les noms de base des photos sources (sans extension)
    source_files = {f: os.path.splitext(f)[0] for f in os.listdir(SOURCE_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.heif') + VIDEO_EXTENSIONS)}
    source_basenames = set(source_files.values())

    # 2. Obtenir les noms de base des photos déjà préparées
    prepared_basenames = {os.path.splitext(f.name)[0] for f in PREPARED_SOURCE_DIR.iterdir() if f.is_file() and f.suffix.lower() == '.jpg' and not f.name.endswith('_polaroid.jpg')}

    # 3. Déterminer les photos à supprimer (obsolètes)
    # On ne supprime les photos obsolètes que pour les sources qui sont synchronisées (pas pour le smartphone qui est additif)
    if source_type != "smartphone":
        basenames_to_delete = prepared_basenames - source_basenames
        if basenames_to_delete:
            yield {"type": "progress", "stage": "CLEANING", "message": f"Suppression de {len(basenames_to_delete)} photos obsolètes..."}
            for basename in basenames_to_delete:
                prepared_photo_path = PREPARED_SOURCE_DIR / f"{basename}.jpg"
                polaroid_photo_path = PREPARED_SOURCE_DIR / f"{basename}_polaroid.jpg"
                backup_photo_path = PREPARED_SOURCE_DIR.parent.parent / '.backups' / source_type / f"{basename}.jpg"
                
                try:
                    if prepared_photo_path.is_file():
                        prepared_photo_path.unlink()
                    if polaroid_photo_path.is_file():
                        polaroid_photo_path.unlink()
                    if backup_photo_path.is_file():
                        backup_photo_path.unlink()
                except OSError as e:
                    yield {"type": "warning", "message": f"Impossible de supprimer {basename}.jpg : {e}"}

    # 4. Déterminer les photos à préparer (nouvelles)
    basenames_to_prepare = source_basenames - prepared_basenames
    files_to_prepare = [f for f, basename in source_files.items() if basename in basenames_to_prepare]
    
    total = len(files_to_prepare)
    
    if total == 0:
        yield {"type": "info", "message": "Aucune nouvelle photo à préparer. Le dossier est à jour."}
        yield {"type": "done", "stage": "PREPARING_COMPLETE", "percent": 100, "message": "Aucune nouvelle photo à préparer."}
        return

    yield {"type": "stats", "stage": "PREPARING_START", "message": f"Début de la préparation de {total} nouvelles photos...", "total": total}

    for i, filename in enumerate(files_to_prepare, start=1):
        src_path = os.path.join(SOURCE_DIR, filename)
        
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
                prepare_photo(src_path, str(dest_path), actual_output_width, actual_output_height)
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