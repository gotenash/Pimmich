import os
import subprocess
import sys
import signal
import psutil

PID_FILE = "/tmp/pimmich_slideshow.pid"
HDMI_OUTPUT = "HDMI-A-1"

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
    subprocess.run(["swaymsg", "output", HDMI_OUTPUT, "enable"])

    # Préparer l’environnement Wayland/Sway
    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"] = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    env["WAYLAND_DISPLAY"] = env.get("WAYLAND_DISPLAY", "wayland-1")

    # Créer le dossier de logs et rediriger la sortie du diaporama pour le débogage
    os.makedirs("logs", exist_ok=True)
    stdout_log = open("logs/slideshow_stdout.log", "a")
    stderr_log = open("logs/slideshow_stderr.log", "a")

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


def stop_slideshow():
    # 1. Tuer le processus avec le PID enregistré
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read())
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
    subprocess.run(["swaymsg", "output", HDMI_OUTPUT, "disable"])
<<<<<<< HEAD
=======

>>>>>>> 3363f89ea41d3158a19361a4baae8bd99d8e9f99
