import json
import subprocess
from werkzeug.security import generate_password_hash

CREDENTIALS_PATH = '/boot/firmware/credentials.json'

def change_password(new_password: str):
    """
    Met à jour le mot de passe dans le fichier credentials.json en le hachant.
    Nécessite des droits sudo pour écrire dans /boot/firmware/.
    """
    if not new_password:
        raise ValueError("Le nouveau mot de passe ne peut pas être vide.")

    try:
        # Lire le contenu actuel pour conserver le nom d'utilisateur
        with open(CREDENTIALS_PATH, 'r') as f:
            credentials = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        # Si le fichier n'existe pas ou est corrompu, on en crée un nouveau avec l'utilisateur par défaut 'admin'
        print(f"Avertissement: Impossible de lire {CREDENTIALS_PATH} ({e}). Un nouveau sera créé.")
        credentials = {'username': 'admin'}

    # Mettre à jour le mot de passe avec un hash sécurisé
    credentials['password_hash'] = generate_password_hash(new_password)
    # Supprimer l'ancien mot de passe en clair s'il existe
    credentials.pop('password', None)

    # Préparer le contenu à écrire
    new_content = json.dumps(credentials, indent=2)

    # Utiliser 'sudo tee' pour écrire le fichier avec les permissions root
    try:
        subprocess.run(
            ['sudo', '/usr/bin/tee', CREDENTIALS_PATH],
            input=new_content,
            text=True,
            capture_output=True,
            check=True,
            timeout=10
        )
        print(f"Mot de passe mis à jour avec succès dans {CREDENTIALS_PATH}")
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        error_message = f"Impossible d'écrire dans {CREDENTIALS_PATH}: {e}"
        print(error_message)
        raise Exception(error_message)