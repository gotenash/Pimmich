import os
import glob
import psutil
import subprocess
import sys
import time
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
from .display_manager import set_display_power
from .config_manager import load_config

# ============================================================
# Configuration du logging avec émojis
# ============================================================
LOGSDIR = Path(__file__).resolve().parent.parent / "logs"
LOGSDIR.mkdir(exist_ok=True)

class EmojiFormatter(logging.Formatter):
    """Formatter personnalisé avec émojis selon le niveau."""
    EMOJI_MAP = {
        "DEBUG": "🔍",
        "INFO": "ℹ️",
        "WARNING": "😒",
        "ERROR": "❌",
        "CRITICAL": "🔥"
    }
    
    def format(self, record):
        emoji = self.EMOJI_MAP.get(record.levelname, "")
        record.emoji = emoji
        return super().format(record)
# Charger la configuration
config = load_config()

# Créer un logger spécifique pour ce module
logger = logging.getLogger("pimmich.slideshow_manager")

# Récupérer le niveau de log depuis la configuration
level_name = config.get("level_log", "INFO")
level = getattr(logging, level_name.upper(), logging.INFO)
logger.setLevel(level)

# Handler fichier avec rotation (10 Mo max, 3 backups)
file_handler = RotatingFileHandler(
    LOGSDIR / "slideshow.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8"
)
file_handler.setLevel(level)

file_formatter = EmojiFormatter(
    '%(asctime)s %(emoji)s %(message)s',
    datefmt='%d-%m %H:%M:%S'
)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)


file_handler = RotatingFileHandler(
    LOGSDIR / "slideshow.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8"
)
file_handler.setLevel(level)

file_formatter = EmojiFormatter(
    '%(asctime)s %(emoji)s %(message)s',
    datefmt='%d-%m %H:%M:%S'
)
file_handler.setFormatter(file_formatter)


# Ajouter les handlers (éviter doublons si module réimporté)
if not logger.handlers:
    logger.addHandler(file_handler)
    #logger.addHandler(err_handler)

# Messages de démarrage
logger.info("----------------------------------------------------------------")
logger.info("----------------Initialisation Slideshow Manager----------------")
logger.info("----------------------------------------------------------------")

# ============================================================
# Constantes
# ============================================================
PID_FILE = "/tmp/pimmich_slideshow.pid"

# ============================================================
# Fonctions
# ============================================================

def is_slideshow_running():
    """Vérifie si un processus de diaporama est actuellement en cours d'exécution."""
    if not os.path.exists(PID_FILE):
        return False
    
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        
        if not psutil.pid_exists(pid):
            logger.error(f"PID {pid} n'existe plus")
            return False
        
        p = psutil.Process(pid)
        is_running = p.is_running() and any("local_slideshow.py" in s for s in p.cmdline())
        logger.debug(f"Slideshow running: {is_running} (PID: {pid})")
        return is_running
    except (psutil.NoSuchProcess, FileNotFoundError, ValueError) as e:
        logger.error(f"Erreur vérification slideshow: {e}")
        return False


def start_slideshow():
    """Démarre le processus du diaporama."""
    # Nettoyage si un ancien fichier PID existe sans process actif
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read())
            if not psutil.pid_exists(pid):
                os.remove(PID_FILE)
                logger.info(f"Ancien PID file {pid} nettoyé")
        except Exception as e:
            logger.debug(f"Erreur nettoyage PID: {e}")
            pass
    
    # Vérifie si un slideshow est déjà en cours
    if is_slideshow_running():
        logger.info("Slideshow déjà en cours, pas de démarrage")
        return
    
    # Préparer l'environnement
    python_executable = sys.executable
    
    # Lance le diaporama
    try:
        proc = subprocess.Popen(
            [python_executable, "-u", "local_slideshow.py"],
            env=os.environ.copy()
        )
        
        # Sauvegarde le PID du nouveau processus
        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))
        
        logger.info(f"✅ Diaporama démarré avec PID {proc.pid}")
    except Exception as e:
        logger.error(f"Échec démarrage diaporama: {e}")


def _stop_process_by_pid(pid):
    """Arrête un processus de diaporama par son PID."""
    if psutil.pid_exists(pid):
        logger.info(f"Arrêt du processus de diaporama {pid}...")
        p = psutil.Process(pid)
        p.terminate()
        
        try:
            p.wait(timeout=3)
            logger.info(f"Processus {pid} arrêté proprement")
        except psutil.TimeoutExpired:
            logger.warning(f"Le processus {pid} n'a pas répondu, forçage de l'arrêt")
            p.kill()
            logger.info(f"Processus {pid} tué de force")


def stop_slideshow():
    """Arrête le processus du diaporama de manière robuste, en attendant sa terminaison."""
    config = load_config()
    is_smart_plug_enabled = config.get("smart_plug_enabled", False)
    
    logger.info("Arrêt du diaporama demandé")
    
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            _stop_process_by_pid(pid)
        except (IOError, ValueError, psutil.NoSuchProcess) as e:
            logger.error(f"Avertissement lors de l'arrêt du diaporama : {e}")
        finally:
            # S'assurer que le fichier PID est supprimé
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
                logger.debug("Fichier PID supprimé")
    
    # Double sécurité : tuer tous les processus restants qui pourraient être des zombies
    for proc in psutil.process_iter(attrs=["pid", "cmdline"]):
        try:
            if proc.info["cmdline"] and any("local_slideshow.py" in part for part in proc.info["cmdline"]):
                logger.warning(f"Nettoyage d'un processus de diaporama zombie trouvé (PID: {proc.pid})")
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    # Éteindre l'écran proprement (via prise ou DPMS)
    logger.info("Extinction de l'écran")
    set_display_power(on=False)


def restart_slideshow_for_update():
    """
    Redémarre le diaporama après une mise à jour de contenu, sans éteindre l'écran.
    C'est la fonction à utiliser par les workers de mise à jour automatique.
    """
    logger.info("Redémarrage du diaporama pour mise à jour de contenu")
    
    # 1. Arrêter le processus existant (sans appeler set_display_power)
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            _stop_process_by_pid(pid)
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
        except Exception as e:
            logger.error(f"Avertissement lors de l'arrêt pour mise à jour : {e}")
    
    # 2. Démarrer un nouveau processus
    start_slideshow()
    logger.info("✅ Diaporama redémarré pour mise à jour")


def restart_slideshow_process():
    """
    Redémarre uniquement le processus du diaporama, sans affecter l'alimentation de l'écran.
    Idéal pour appliquer les changements de configuration sans cycle de redémarrage complet.
    """
    logger.info("Redémarrage du processus de diaporama demandé")
    
    # 1. Arrêter le processus existant (sans appeler set_display_power)
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            _stop_process_by_pid(pid)
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt: {e}")
        
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except OSError as e:
                logger.warning(f"Impossible de supprimer le fichier PID : {e}")
    
    # Afficher un message de redémarrage sur l'écran
    try:
        python_executable = sys.executable
        message = "Redémarrage du diaporama..."
        
        # Utiliser Popen pour ne pas bloquer, et s'assurer que l'environnement est correct
        env = os.environ.copy()
        if "SWAYSOCK" not in env:
            user_id = os.getuid()
            socks = glob.glob(f"/run/user/{user_id}/sway-ipc.*")
            if socks:
                env["SWAYSOCK"] = socks[0]
        
        subprocess.Popen([python_executable, "utils/display_message.py", message], env=env)
        time.sleep(1)  # Laisser le temps au message de s'afficher
        logger.info("Message de redémarrage affiché")
    except Exception as e:
        logger.warning(f"Impossible d'afficher le message de redémarrage : {e}")
    
    # 2. Démarrer un nouveau processus
    start_slideshow()
    logger.info("✅ Processus de diaporama redémarré")
