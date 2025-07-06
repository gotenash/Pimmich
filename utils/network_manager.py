import subprocess
import re

def get_interface_status(interface_name: str):
    """
    Récupère l'état (UP/DOWN) et l'adresse IP d'une interface réseau.
    """
    status = {"name": interface_name, "state": "DOWN", "ip_address": "N/A"}
    try:
        # Commande pour obtenir les détails de l'interface
        ip_addr_output = subprocess.check_output(
            ['ip', 'addr', 'show', interface_name],
            text=True,
            stderr=subprocess.DEVNULL
        ).strip()

        if "state UP" in ip_addr_output:
            status["state"] = "UP"
        
        # Extraire l'adresse IP si elle existe
        ip_match = re.search(r"inet (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", ip_addr_output)
        if ip_match:
            status["ip_address"] = ip_match.group(1)

    except (subprocess.CalledProcessError, FileNotFoundError):
        # L'interface n'existe probablement pas ou la commande a échoué
        status["state"] = "NOT_FOUND"
    
    return status

def set_interface_state(interface_name: str, state: str):
    """
    Active ('connect') ou désactive ('disconnect') une interface réseau via NetworkManager.
    """
    # 'up' devient 'connect', 'down' devient 'disconnect' pour nmcli
    action = 'connect' if state == 'up' else 'disconnect'
    
    try:
        # Utiliser nmcli pour gérer l'état de l'interface
        subprocess.run(
            ['sudo', 'nmcli', 'device', action, interface_name],
            check=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        print(f"Interface {interface_name} passée à l'état '{action}'.")
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        stderr = getattr(e, 'stderr', str(e))
        error_message = f"Impossible de changer l'état de l'interface {interface_name}: {stderr}"
        print(error_message)
        raise Exception(error_message)