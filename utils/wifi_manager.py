import subprocess
import os
import re
import time

WPA_SUPPLICANT_CONF = "/etc/wpa_supplicant/wpa_supplicant.conf"

def _run_sudo_command(cmd_list):
    """Exécute une commande avec sudo et gère les erreurs."""
    try:
        print(f"[WiFi Manager] Exécution de la commande sudo: {' '.join(cmd_list)}")
        result = subprocess.run(['sudo'] + cmd_list, capture_output=True, text=True, check=True, timeout=30)
        print(f"[WiFi Manager] Commande réussie: {result.stdout}")
        if result.stderr:
            print(f"[WiFi Manager] Erreurs/Avertissements: {result.stderr}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[WiFi Manager] Erreur d'exécution (code {e.returncode}): {e.stderr}")
        raise Exception(f"La commande sudo a échoué: {e.stderr}")
    except subprocess.TimeoutExpired:
        print("[WiFi Manager] La commande sudo a expiré.")
        raise Exception("La commande sudo a expiré.")
    except FileNotFoundError:
        print(f"[WiFi Manager] Commande non trouvée: {cmd_list[0]}. Est-elle installée et dans le PATH?")
        raise Exception(f"Commande non trouvée: {cmd_list[0]}.")
    except Exception as e:
        print(f"[WiFi Manager] Erreur inattendue lors de l'exécution de la commande sudo: {e}")
        raise Exception(f"Erreur inattendue: {e}")

def set_wifi_config(ssid: str, password: str):
    """
    Configure le Wi-Fi du système.
    Essaie d'abord avec nmcli, puis avec wpa_supplicant.conf.
    """
    print(f"[WiFi Manager] Tentative de configuration Wi-Fi pour SSID: {ssid}")

    # 1. Essai avec nmcli (NetworkManager)
    try:
        print("[WiFi Manager] Tentative avec nmcli...")
        # Supprimer la connexion existante si elle a le même SSID
        _run_sudo_command(['nmcli', 'connection', 'delete', ssid])
        # Ajouter et activer la nouvelle connexion
        _run_sudo_command(['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password])
        print("[WiFi Manager] Configuration Wi-Fi appliquée avec nmcli.")
        return
    except Exception as e:
        print(f"[WiFi Manager] Échec de nmcli: {e}. Fallback sur wpa_supplicant.conf.")

    # 2. Fallback sur wpa_supplicant.conf
    try:
        print("[WiFi Manager] Tentative avec wpa_supplicant.conf...")
        # Lire le contenu actuel
        current_content = ""
        if os.path.exists(WPA_SUPPLICANT_CONF):
            with open(WPA_SUPPLICANT_CONF, 'r') as f:
                current_content = f.read()

        # Supprimer les blocs réseau existants pour ce SSID
        new_content = re.sub(r'network={\s*ssid="' + re.escape(ssid) + r'".*?}', '', current_content, flags=re.DOTALL)

        # Ajouter le nouveau bloc réseau
        network_block = f"""
network={{
    ssid="{ssid}"
    psk="{password}"
}}
"""
        # Assurer que les lignes de contrôle sont présentes
        if "ctrl_interface" not in new_content:
            new_content = "ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\n" + new_content

        new_content += network_block

        # Écrire le nouveau contenu (nécessite sudo)
        _run_sudo_command(['bash', '-c', f'echo "{new_content}" > {WPA_SUPPLICANT_CONF}'])
        _run_sudo_command(['systemctl', 'restart', 'wpa_supplicant.service'])
        print("[WiFi Manager] Configuration Wi-Fi appliquée avec wpa_supplicant.conf.")
    except Exception as e:
        print(f"[WiFi Manager] Échec total de la configuration Wi-Fi: {e}")
        raise Exception(f"Impossible de configurer le Wi-Fi: {e}")

if __name__ == "__main__":
    # Exemple d'utilisation pour les tests (à exécuter avec sudo python3 wifi_manager.py)
    # set_wifi_config("MonSSID", "MonMotDePasse")
    print("Ce script est destiné à être importé. Exécutez-le avec des privilèges sudo pour les tests.")