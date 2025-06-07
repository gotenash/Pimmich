from PIL import Image, ExifTags

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
