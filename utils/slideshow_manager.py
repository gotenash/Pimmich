import os
import signal
import psutil
import subprocess, sys
import time
from .display_manager import set_display_power
from .config_manager import load_config

PID_FILE = "/tmp/pimmich_slideshow.pid"
_log_files = {} # Dictionnaire pour garder les références aux fichiers de log ouverts

def is_slideshow_running():
    if not os.path.exists(PID_FILE):
        return False
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        if not psutil.pid_exists(pid):
            return False
        p = psutil.Process(pid)
        return p.is_running() and any("local_slideshow.py" in s for s in p.cmdline())
    except (psutil.NoSuchProcess, FileNotFoundError, ValueError):
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

    # Préparer l’environnement Wayland/Sway

    # Utiliser le même exécutable python que celui qui lance l'application web
    # pour garantir que le diaporama s'exécute dans le même environnement (venv).
    python_executable = sys.executable
    # Lance le diaporama
    stdout_log = open("logs/slideshow_stdout.log", "a")
    stderr_log = open("logs/slideshow_stderr.log", "a")
    proc = subprocess.Popen([python_executable, "-u", "local_slideshow.py"], stdout=stdout_log, stderr=stderr_log, env=os.environ.copy())

    # Sauvegarde le PID du nouveau processus
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
    
    # Garder une référence aux fichiers de log pour qu'ils ne soient pas fermés
    _log_files[proc.pid] = (stdout_log, stderr_log)

def _stop_process_by_pid(pid):
    """Helper function to stop a process and close its log files."""
    if psutil.pid_exists(pid):
        print(f"Arrêt du processus de diaporama {pid}...")
        p = psutil.Process(pid)
        p.terminate()
        try:
            p.wait(timeout=3)
        except psutil.TimeoutExpired:
            print(f"Le processus {pid} n'a pas répondu, forçage de l'arrêt.")
            p.kill()
    # Fermer et supprimer les références aux fichiers de log
    if pid in _log_files:
        for log_file in _log_files[pid]:
            if not log_file.closed: log_file.close()
        del _log_files[pid]

def stop_slideshow():
    """Arrête le processus du diaporama de manière robuste, en attendant sa terminaison."""
    config = load_config()
    is_smart_plug_enabled = config.get("smart_plug_enabled", False)

    # Si une prise connectée est utilisée, on arrête d'abord le diaporama
    # avant de couper l'alimentation de l'écran.
    # Sinon, on arrête juste le diaporama et on laisse set_display_power gérer le DPMS.

    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            _stop_process_by_pid(pid)
        except (IOError, ValueError, psutil.NoSuchProcess) as e:
            print(f"Avertissement lors de l'arrêt du diaporama : {e}")
        finally:
            # S'assurer que le fichier PID est supprimé
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)

    # Double sécurité : tuer tous les processus restants qui pourraient être des zombies
    for proc in psutil.process_iter(attrs=["pid", "cmdline"]):
        try:
            if proc.info["cmdline"] and any("local_slideshow.py" in part for part in proc.info["cmdline"]):
                print(f"Nettoyage d'un processus de diaporama zombie trouvé (PID: {proc.pid}).")
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Éteindre l’écran proprement (via prise ou DPMS)
    set_display_power(False)

def restart_slideshow_process():
    """
    Redémarre uniquement le processus du diaporama, sans affecter l'alimentation de l'écran.
    Idéal pour appliquer les changements de configuration sans cycle de redémarrage complet.
    """
    print("[Slideshow Manager] Redémarrage du processus de diaporama demandé.")
    
    # 1. Arrêter le processus existant (sans appeler set_display_power)
    if os.path.exists(PID_FILE):
        with open(PID_FILE, "r") as f: pid = int(f.read().strip())
        _stop_process_by_pid(pid)
        if os.path.exists(PID_FILE): os.remove(PID_FILE)

    # --- NOUVEAU: Afficher un message de redémarrage ---
    try:
        python_executable = sys.executable
        message = "Redémarrage du diaporama..."
        # On lance le script d'affichage de message et on ne l'attend pas (il se fermera tout seul)
        subprocess.Popen([python_executable, "utils/display_message.py", message], env=os.environ.copy())
        time.sleep(0.5) # Petite pause pour laisser le message s'afficher
    except Exception as e:
        print(f"Avertissement: Impossible d'afficher le message de redémarrage : {e}")

    # 2. Démarrer un nouveau processus
    start_slideshow()
