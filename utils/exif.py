from PIL import Image, ExifTags
from datetime import datetime

def get_rotation_angle(image):
    try:
        exif = image._getexif()
        if not exif:
            return 0

        for tag, value in exif.items():
            decoded = ExifTags.TAGS.get(tag, tag)
            if decoded == "Orientation":
                if value == 3:
                    return 180
                elif value == 6:
                    return 270
                elif value == 8:
                    return 90
        return 0
    except Exception as e:
        print(f"Erreur lors de la lecture EXIF : {e}")
        return 0
        
        
        
# Modification Sigalou 25/01/2026 - Ajout récupération date de prise de vue
def get_photo_date(image):
    """
    Récupère la date de prise de vue de l'image.
    Ordre de priorité:
    1. DateTimeOriginal (date de prise de vue)
    2. DateTimeDigitized (date de numérisation)
    3. DateTime (date de modification)
    
    Retourne: datetime object ou None si aucune date trouvée
    """
    try:
        exif = image._getexif()
        if not exif:
            return None

        # Tags EXIF pour les dates, par ordre de priorité
        date_tags = ["DateTimeOriginal", "DateTimeDigitized", "DateTime"]
        
        for tag, value in exif.items():
            decoded = ExifTags.TAGS.get(tag, tag)
            if decoded in date_tags:
                # Format EXIF standard: "YYYY:MM:DD HH:MM:SS"
                try:
                    photo_date = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                    return photo_date
                except ValueError:
                    # Si le format est différent, continuer avec le prochain tag
                    continue
        
        return None
    except Exception as e:
        print(f"Erreur lors de la lecture de la date EXIF : {e}")
        return None

def get_photo_date_formatted(image, format="%d/%m/%Y"):
    """
    Récupère la date de prise de vue formatée.
    
    Args:
        image: Image PIL
        format: Format de sortie (par défaut: JJ/MM/AAAA)
    
    Retourne: String formatée ou None
    """
    photo_date = get_photo_date(image)
    if photo_date:
        return photo_date.strftime(format)
    return None
<<<<<<< HEAD
# Fin Modification Sigalou 25/01/2026
=======
# Fin Modification Sigalou 25/01/2026
>>>>>>> 585d33c75477652e9a2d7455d8b4e6c4f1b92b2c
