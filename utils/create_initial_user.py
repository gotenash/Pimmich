import json
import secrets
from werkzeug.security import generate_password_hash
import argparse
import sys

def generate_random_password(length=12):
    """Génère un mot de passe aléatoire sécurisé et facile à taper."""
    # Alphabet sans caractères ambigus (I, l, 1, O, 0) et sans ponctuation pour faciliter la saisie
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    password = ''.join(secrets.choice(alphabet) for i in range(length))
    return password

def create_credentials_file(output_path, username="admin"):
    """Génère un nouveau mot de passe, le hache et crée le fichier credentials.json."""
    password = generate_random_password()
    flask_secret_key = secrets.token_hex(24) # Génère une clé sécurisée de 24 octets pour Flask
    
    # Hacher le mot de passe en utilisant une méthode sécurisée.
    # Werkzeug gère automatiquement le salage (salt).
    password_hash = generate_password_hash(password)
    
    credentials = {
        "username": username,
        "password_hash": password_hash,
        "flask_secret_key": flask_secret_key
    }
    
    try:
        with open(output_path, 'w') as f:
            json.dump(credentials, f, indent=2)
        
        # Afficher les identifiants pour que l'utilisateur les note.
        # C'est la seule fois où le mot de passe en clair sera affiché.
        print("\n" + "="*60, file=sys.stderr)
        print("✅ Fichier d'identification sécurisé créé.", file=sys.stderr)
        print("\n" + "-"*60, file=sys.stderr)
        print("⚠️  NOTEZ CES IDENTIFIANTS, ILS NE SERONT PLUS AFFICHÉS  ⚠️", file=sys.stderr)
        print(f"   Utilisateur : {username}", file=sys.stderr)
        print(f"   Mot de passe: {password}", file=sys.stderr)
        print("="*60 + "\n", file=sys.stderr)

    except Exception as e:
        print(f"ERREUR: Impossible de créer le fichier d'identification à '{output_path}'.", file=sys.stderr)
        print(f"Détails: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crée un fichier credentials.json sécurisé avec un mot de passe aléatoire.")
    parser.add_argument(
        '--output',
        required=True,
        help="Chemin complet du fichier credentials.json à créer."
    )
    parser.add_argument(
        '--username',
        default='admin',
        help="Nom de l'utilisateur à créer (par défaut: admin)."
    )
    
    args = parser.parse_args()
    
    create_credentials_file(args.output, args.username)