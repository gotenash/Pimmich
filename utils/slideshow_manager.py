import os
import signal
import psutil
import subprocess, sys
from .display_manager import set_display_power # MODIFIÉ

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

    # Active la sortie HDMI via swaymsg
    set_display_power(True) # MODIFIÉ

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
    # Ajout de -u pour un output non bufferisé, crucial pour les logs en temps réel
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
    """Arrête le processus du diaporama de manière robuste, en attendant sa terminaison."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                print(f"Arrêt du processus de diaporama {pid}...")
                p = psutil.Process(pid)
                p.terminate() # Envoyer un signal de terminaison propre
                try:
                    # Attendre un peu plus longtemps pour s'assurer que tout est bien fermé
                    p.wait(timeout=5) 
                    print(f"Processus {pid} terminé proprement.")
                except psutil.TimeoutExpired:
                    print(f"Le processus {pid} n'a pas répondu, forçage de l'arrêt.")
                    p.kill() # Forcer l'arrêt s'il ne répond pas
                    p.wait(timeout=2) # Laisser le temps au kill de faire effet
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

    # 3. Éteindre l’écran proprement
    set_display_power(False)
