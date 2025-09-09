import os
import subprocess
import sys
import signal
import psutil
import json

PID_FILE = "/tmp/pimmich_voice_control.pid"
STATUS_FILE = "logs/voice_control_status.json"
_log_files = {}

def update_status_file(status_dict):
    """Met à jour le fichier de statut JSON."""
    try:
        os.makedirs("logs", exist_ok=True)
        with open(STATUS_FILE, "w") as f:
            json.dump(status_dict, f)
    except IOError as e:
        # Cette erreur sera visible dans les logs de app.py
        print(f"[VoiceManager] Erreur écriture fichier statut : {e}")

def is_voice_control_running():
    """Vérifie si le processus de contrôle vocal est en cours d'exécution."""
    if not os.path.exists(PID_FILE):
        return False
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        if not psutil.pid_exists(pid):
            return False
        p = psutil.Process(pid)
        # Vérifie que le processus existe et que la ligne de commande correspond
        return p.is_running() and any("voice_control.py" in s for s in p.cmdline())
    except (psutil.NoSuchProcess, FileNotFoundError, ValueError):
        return False

def start_voice_control():
    """Démarre le script de contrôle vocal et redirige sa sortie vers les logs."""
    if is_voice_control_running():
        print("Le contrôle vocal est déjà en cours.")
        return

    print("Démarrage du service de contrôle vocal...")
    python_executable = sys.executable
    # Ajout du flag -u pour un output non bufferisé, crucial pour les logs en temps réel
    command = [python_executable, "-u", "voice_control.py"]
    
    os.makedirs("logs", exist_ok=True)
    try:
        # Ouvre les fichiers de log en mode 'write' pour effacer les anciens logs à chaque démarrage
        stdout_log = open("logs/voice_control_stdout.log", "w")
        stderr_log = open("logs/voice_control_stderr.log", "w")
        
        proc = subprocess.Popen(command, stdout=stdout_log, stderr=stderr_log)
        
        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))
            
        print(f"Service de contrôle vocal démarré avec PID {proc.pid}.")
    except Exception as e:
        print(f"Erreur lors du démarrage du contrôle vocal : {e}")

def stop_voice_control():
    """Arrête le processus de contrôle vocal."""
    if not is_voice_control_running():
        return
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        p = psutil.Process(pid)
        p.terminate()
        p.wait(timeout=3)
    except (psutil.NoSuchProcess, psutil.TimeoutExpired, FileNotFoundError, ValueError, IOError) as e:
        print(f"Avertissement lors de l'arrêt du contrôle vocal : {e}")
    finally:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        if os.path.exists(STATUS_FILE):
            os.remove(STATUS_FILE)