import subprocess
import time
import re

def get_wifi_status():
    """
    Récupère l'état actuel de la connexion Wi-Fi (SSID et adresse IP).
    Retourne un dictionnaire avec les informations.
    """
    status = {"ssid": "Non connecté", "ip_address": "N/A", "is_connected": False}
    try:
        # Utiliser nmcli pour obtenir un statut fiable
        cmd = ['/usr/bin/nmcli', '-t', '-f', 'GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS', 'dev', 'show', 'wlan0']
        output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
        
        lines = output.split('\n')
        state_line = lines[0]
        conn_line = lines[1]
        ip_line = lines[2]

        if '100 (connecté)' in state_line or 'connected' in state_line:
            status["is_connected"] = True
            # Extraire le SSID
            ssid_match = re.search(r'GENERAL.CONNECTION:(.*)', conn_line)
            if ssid_match:
                status["ssid"] = ssid_match.group(1)
            
            # Extraire l'IP
            ip_match = re.search(r'IP4.ADDRESS\[1\]:(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', ip_line)
            if ip_match:
                status["ip_address"] = ip_match.group(1)

    except (subprocess.CalledProcessError, FileNotFoundError):
        pass # Les commandes échouent si non connecté, le statut par défaut est correct.
    return status

def set_wifi_config(ssid: str, password: str, country_code: str = "FR"):
    """
    Configure le pays du Wi-Fi, met à jour les identifiants dans wpa_supplicant.conf,
    et se connecte en utilisant nmcli (NetworkManager).
    """
    if not country_code:
        raise ValueError("Le code pays est obligatoire.")

    # 1. Définir le pays du Wi-Fi via raspi-config
    try:
        print(f"Définition du pays Wi-Fi sur : {country_code}")
        subprocess.run(
            ['sudo', '/usr/bin/raspi-config', 'nonint', 'do_wifi_country', country_code],
            check=True, capture_output=True, text=True, timeout=15
        )
    except subprocess.CalledProcessError as e:
        raise Exception(f"Impossible de définir le pays Wi-Fi : {e.stderr}")
    except subprocess.TimeoutExpired:
        raise Exception("La commande raspi-config a expiré.")
    except FileNotFoundError:
        raise Exception("La commande 'raspi-config' est introuvable. Ce script est-il exécuté sur un Raspberry Pi OS?")

    # 2. Se connecter en utilisant nmcli
    try:
        print(f"Tentative de connexion au Wi-Fi '{ssid}' via nmcli...")
        
        # Supprimer l'ancienne connexion si elle existe pour forcer une nouvelle configuration
        # Le `|| true` à la fin évite une erreur si la connexion n'existe pas.
        subprocess.run(f"sudo nmcli connection delete '{ssid}' || true", shell=True, capture_output=True)
        
        # Créer la nouvelle connexion
        cmd = ['sudo', '/usr/bin/nmcli', 'device', 'wifi', 'connect', ssid]
        if password:
            cmd.extend(['password', password])
        
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
        print(f"Connexion Wi-Fi réussie : {result.stdout}")
        
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        stderr = getattr(e, 'stderr', str(e))
        print(f"Erreur lors de la connexion via nmcli : {stderr}")
        raise Exception(f"La connexion Wi-Fi a échoué. Détails: {stderr}")