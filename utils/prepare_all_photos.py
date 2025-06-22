import os
from PIL import Image
import pillow_heif

# Configuration
SOURCE_DIR = "static/photos"
PREPARED_DIR = "static/photos_prepared"
MAX_WIDTH = 1920
MAX_HEIGHT = 1080

def prepare_photo(source_path, dest_path):
    """Prépare une photo pour l'affichage"""
    try:
        # Gestion des fichiers HEIF/HEIC
        if source_path.lower().endswith(('.heic', '.heif')):
            pillow_heif.register_heif_opener()
        
        with Image.open(source_path) as img:
            # Conversion en RGB si nécessaire
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            # Redimensionnement si nécessaire
            if img.width > MAX_WIDTH or img.height > MAX_HEIGHT:
                img.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)
            
            # Sauvegarde optimisée
            img.save(dest_path, 'JPEG', quality=85, optimize=True)
            
    except Exception as e:
        raise Exception(f"Erreur lors du traitement de l'image : {e}")

def prepare_all_photos_with_progress():
    """Version générateur pour feedback en temps réel"""
    if not os.path.isdir(SOURCE_DIR):
        yield f"[ERREUR] Le dossier source n'existe pas : {SOURCE_DIR}"
        return

    os.makedirs(PREPARED_DIR, exist_ok=True)

    # Nettoyer le dossier de destination
    for f in os.listdir(PREPARED_DIR):
        file_path = os.path.join(PREPARED_DIR, f)
        if os.path.isfile(file_path):
            os.remove(file_path)

    photos = [f for f in os.listdir(SOURCE_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.heif'))]
    total = len(photos)
    
    if total == 0:
        yield "[ERREUR] Aucune photo à préparer"
        return

    yield f"[PREPARATION] Préparation de {total} photos pour l'écran..."

    for i, filename in enumerate(photos, start=1):
        src_path = os.path.join(SOURCE_DIR, filename)
        
        # Convertir l'extension pour le fichier de destination
        base_name = os.path.splitext(filename)[0]
        dest_filename = f"{base_name}.jpg"
        dest_path = os.path.join(PREPARED_DIR, dest_filename)
        
        try:
            prepare_photo(src_path, dest_path)
            yield f"[SUCCES] Préparé {i}/{total} : {filename}"
        except Exception as e:
            yield f"[ERREUR] Erreur avec {filename} : {e}"

def prepare_all_photos(status_callback=None):
    """Version originale avec callback pour compatibilité"""
    for message in prepare_all_photos_with_progress():
        if status_callback:
            status_callback(message)
        else:
            print(message)

# Fonction principale pour tests
if __name__ == "__main__":
    print("Test de préparation des photos...")
    prepare_all_photos()
    print("Terminé !")
