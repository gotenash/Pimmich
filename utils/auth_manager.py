import json
import subprocess

CREDENTIALS_PATH = '/boot/firmware/credentials.json'

def change_password(new_password: str):
    """
    Met à jour le mot de passe dans le fichier credentials.json.
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

    # Mettre à jour le mot de passe
    credentials['password'] = new_password

    # Préparer le contenu à écrire
    new_content = json.dumps(credentials, indent=2)

    # Utiliser 'sudo tee' pour écrire le fichier avec les permissions root
    try:
        subprocess.run(
            ['sudo', 'tee', CREDENTIALS_PATH],
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