import os
import subprocess
import glob
import json

def get_display_output_name():
    """
    Détecte le nom de la sortie d'affichage principale via swaymsg.
    Centralise la logique pour éviter la duplication.
    """
    try:
        if "SWAYSOCK" not in os.environ:
            user_id = os.getuid()
            sock_path_pattern = f"/run/user/{user_id}/sway-ipc.*"
            socks = glob.glob(sock_path_pattern)
            if not socks:
                print("[DisplayManager] AVERTISSEMENT: SWAYSOCK non trouvé, impossible de contrôler l'écran.")
                return None
            os.environ["SWAYSOCK"] = socks[0]

        result = subprocess.run(['swaymsg', '-t', 'get_outputs'], capture_output=True, text=True, check=True)
        outputs = json.loads(result.stdout)
        
        for output in outputs:
            if output.get('active', False):
                return output.get('name')
        if outputs:
            return outputs[0].get('name')
        
        return None
    except Exception as e:
        print(f"[DisplayManager] Erreur lors de la détection de la sortie d'affichage : {e}")
        return None

HDMI_OUTPUT = get_display_output_name()

def set_display_power(on: bool):
    """Active ou désactive l'écran via swaymsg."""
    if not HDMI_OUTPUT:
        print("[DisplayManager] Aucune sortie HDMI détectée, impossible de contrôler l'alimentation.")
        return False, "Aucune sortie HDMI détectée."
    
    cmd = ['swaymsg', 'output', HDMI_OUTPUT, 'enable' if on else 'disable']
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True, f"Écran {'activé' if on else 'désactivé'}."
    except Exception as e:
        return False, f"Erreur swaymsg : {e}"