import os
import subprocess
import sys
import signal
import psutil
import json
import glob

PID_FILE = "/tmp/pimmich_slideshow.pid"

def get_display_output_name():
    """
    Détecte le nom de la sortie d'affichage principale.
    Retourne le nom (ex: "HDMI-A-1") ou None si non trouvé.
    On ne se base plus sur 'active' car l'écran peut être en veille.
    """
    try:
        # Assurer que SWAYSOCK est défini pour communiquer avec Sway
        if "SWAYSOCK" not in os.environ:
            user_id = os.getuid()
            sock_path_pattern = f"/run/user/{user_id}/sway-ipc.*"
            socks = glob.glob(sock_path_pattern)
            if socks:
                os.environ["SWAYSOCK"] = socks[0]
            else:
                print("AVERTISSEMENT: Variable d'environnement SWAYSOCK non trouvée, impossible de contrôler l'écran.")
                return None

        result = subprocess.run(['swaymsg', '-t', 'get_outputs'], capture_output=True, text=True, check=True, env=os.environ)
        outputs = json.loads(result.stdout)
        
        # On cherche la première sortie qui a un mode configuré.
        # C'est plus fiable que de se baser sur 'active', car l'écran peut être désactivé.
        for output in outputs:
            if output.get('current_mode'):
                output_name = output.get('name')
                print(f"Sortie d'affichage principale détectée : {output_name}")
                return output_name
        
        print("AVERTISSEMENT: Aucune sortie d'affichage avec un mode configuré n'a été trouvée.")
        return None
    except Exception as e:
        print(f"Erreur lors de la détection de la sortie d'affichage : {e}.")
        return None

HDMI_OUTPUT = get_display_output_name()
_log_files = {} # Dictionnaire pour garder les références aux fichiers de log ouverts

def is_slideshow_running():
    if not os.path.exists(PID_FILE):
        return False
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read())
        p = psutil.Process(pid)
        return p.is_running() and "local_slideshow.py" in p.cmdline()
    except Exception:
        return False

def start_slideshow():
    # Nettoyage si un ancien fichier PID existe sans process actif
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read())
            if not psutil.pid_exists(pid):
                os.remove(PID_FILE)
        except Exception:
            pass

    # Vérifie si un slideshow est déjà en cours
    if is_slideshow_running():
        return

    # Active la sortie HDMI via swaymsg
    if HDMI_OUTPUT:
        subprocess.run(["swaymsg", "output", HDMI_OUTPUT, "enable"])

    # Préparer l’environnement Wayland/Sway
    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"] = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    env["WAYLAND_DISPLAY"] = env.get("WAYLAND_DISPLAY", "wayland-1")

    # Créer le dossier de logs et rediriger la sortie du diaporama pour le débogage
    os.makedirs("logs", exist_ok=True)
    try:
        stdout_log = open("logs/slideshow_stdout.log", "a")
        stderr_log = open("logs/slideshow_stderr.log", "a")
    except IOError as e:
        print(f"ERREUR: Impossible d'ouvrir les fichiers de log: {e}")

    # Utiliser le même exécutable python que celui qui lance l'application web
    # pour garantir que le diaporama s'exécute dans le même environnement (venv).
    python_executable = sys.executable
    # Lance le diaporama
    proc = subprocess.Popen(
        [python_executable, "local_slideshow.py"],
        stdout=stdout_log,
        stderr=stderr_log,
        env=env
    )

    # Sauvegarde le PID du nouveau processus
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
    
    # Garder une référence aux fichiers de log pour qu'ils ne soient pas fermés
    _log_files[proc.pid] = (stdout_log, stderr_log)


def stop_slideshow():
    # 1. Tuer le processus avec le PID enregistré
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read())
            
            # Fermer les fichiers de log associés à ce PID
            if pid in _log_files:
                _log_files[pid][0].close() # stdout
                _log_files[pid][1].close() # stderr
                del _log_files[pid]
            os.kill(pid, signal.SIGTERM)

        except Exception:
            pass
        try:
            os.remove(PID_FILE)
        except Exception:
            pass

    # 2. Tuer tous les processus restants avec "local_slideshow.py" dans leur commande
    for proc in psutil.process_iter(attrs=["pid", "cmdline"]):
        try:
            if proc.info["cmdline"] and any("local_slideshow.py" in part for part in proc.info["cmdline"]):
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # 3. Éteindre l’écran proprement
    if HDMI_OUTPUT:
        subprocess.run(["swaymsg", "output", HDMI_OUTPUT, "disable"])
