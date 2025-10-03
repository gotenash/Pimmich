import os
import subprocess
import time
import json
import glob
import requests
from pathlib import Path
from .config_manager import load_config

def get_display_output_name():
    """
    Trouve le nom de la sortie d'affichage principale (celle qui est active ou a un mode).
    """
    try:
        if "SWAYSOCK" not in os.environ:
            user_id = os.getuid()
            sock_path_pattern = f"/run/user/{user_id}/sway-ipc.*"
            socks = glob.glob(sock_path_pattern)
            if socks:
                os.environ["SWAYSOCK"] = socks[0]
            else:
                return None

        result = subprocess.run(['swaymsg', '-t', 'get_outputs'], capture_output=True, text=True, check=True, env=os.environ)
        outputs = json.loads(result.stdout)
        
        for output in outputs:
            if output.get('active', False) or output.get('current_mode'):
                return output.get('name')
        return None
    except Exception as e:
        print(f"Erreur lors de la récupération du nom de la sortie d'affichage : {e}")
        return None

def _send_smart_plug_command(url):
    """Envoie une requête HTTP à l'URL de la prise connectée."""
    if not url:
        return False, "URL de la prise connectée non configurée."
    try:
        # Utiliser un timeout court pour ne pas bloquer le système
        response = requests.post(url, timeout=5)
        # On considère que c'est un succès si la requête aboutit (code 2xx)
        if 200 <= response.status_code < 300:
            print(f"Commande prise connectée envoyée avec succès à {url}")
            return True, "Commande envoyée à la prise."
        else:
            error_msg = f"La prise connectée a répondu avec une erreur {response.status_code}."
            print(error_msg)
            return False, error_msg
    except requests.RequestException as e:
        error_msg = f"Erreur de communication avec la prise connectée : {e}"
        print(error_msg)
        return False, error_msg

def set_display_power(on=True):
    """
    Allume ou éteint l'écran, en utilisant une prise connectée si configurée,
    sinon en utilisant la commande logicielle (swaymsg).
    """
    config = load_config()

    if config.get("smart_plug_enabled"):
        # --- Logique de la prise connectée ---
        if on:
            # --- SÉQUENCE D'ALLUMAGE AVEC REDÉMARRAGE SYSTÈME ---
            print("[Display Manager] Allumage de la prise connectée...")
            on_url = config.get("smart_plug_on_url")
            success, message = _send_smart_plug_command(on_url)
            if not success:
                return False, f"Échec de l'allumage de la prise : {message}"
            
            # Attendre que l'écran s'allume avant de redémarrer
            delay = int(config.get("smart_plug_on_delay", 5))
            print(f"Attente de {delay} secondes pour l'initialisation de l'écran...")
            time.sleep(delay)

            # Créer un fichier drapeau pour indiquer qu'un redémarrage est intentionnel
            # pour éviter une boucle de redémarrage.
            # On le place dans le dossier 'cache' pour qu'il persiste après le redémarrage.
            flag_path = Path(__file__).resolve().parent.parent / 'cache' / 'pimmich_reboot_flag.tmp'
            flag_path.parent.mkdir(exist_ok=True) # S'assurer que le dossier cache existe
            flag_path.touch()

            print("[Display Manager] Lancement du redémarrage du système pour garantir la bonne résolution...")
            os.system('sudo reboot')
            # Le script s'arrêtera ici car le système redémarre.
            return True, "Redémarrage système initié."
        else:
            # --- SÉQUENCE D'EXTINCTION ---
            # 1. Mettre l'écran en veille logicielle d'abord
            _set_software_display_power(on=False)
            time.sleep(1) # Petite pause
            # 2. Couper l'alimentation de la prise
            off_url = config.get("smart_plug_off_url")
            return _send_smart_plug_command(off_url)
    else:
        # --- Logique logicielle par défaut ---
        return _set_software_display_power(on)
        
def _set_software_display_power(on=True):
    """Allume ou éteint l'écran en utilisant swaymsg (contrôle logiciel)."""
    output_name = get_display_output_name()
    if not output_name:
        return False, "Aucune sortie d'affichage principale trouvée."
    
    state = "on" if on else "off"
    try:
        subprocess.run(['swaymsg', 'output', output_name, 'dpms', state], check=True, capture_output=True, text=True)
        print(f"Écran '{output_name}' passé en mode DPMS '{state}'.")
        return True, f"Écran passé en mode {state}."
    except Exception as e:
        error_message = f"Erreur lors du changement d'état de l'écran : {e}"
        print(error_message)
        return False, error_message