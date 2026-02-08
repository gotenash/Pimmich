#!/usr/bin/env python3
import os
import subprocess
import time
import json
import glob
import requests
import logging
from pathlib import Path
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
logger = logging.getLogger("pimmich.display_manager")

# Récupérer le niveau de log depuis la configuration
level_name = config.get("level_log", "INFO")
level = getattr(logging, level_name.upper(), logging.INFO)
logger.setLevel(level)
logger.propagate = False

# Handler fichier avec rotation (10 Mo max, 3 backups)
from logging.handlers import RotatingFileHandler
file_handler = RotatingFileHandler(
    LOGSDIR / "pimmich.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8"
)
file_handler.setLevel(level)
file_formatter = EmojiFormatter(
    '%(emoji)s🟩%(asctime)s %(message)s',
    datefmt='%d-%m %H:%M:%S'
)
file_handler.setFormatter(file_formatter)

# Ajouter le handler (éviter doublons si module réimporté)
if not logger.handlers:
    logger.addHandler(file_handler)

# Messages de démarrage
logger.debug("--------------------Lancement de Display_Manager----------------------")
logger.info(f"Le mode de log actif est : {level_name}")
logger.debug("🔍=Debug")
logger.info("ℹ️=Info")
logger.warning("😒=Warning")
logger.error("❌=Error")
logger.info("🟨=App")
logger.info("🟪=Slideshow_Manager")
logger.info("🟦=Local_Slideshow")
logger.info("🟩=Display_Manager")

# ============================================================
# Fonctions du module
# ============================================================

def get_display_output_name():
    """Trouve le nom de la sortie HDMI active (Wayfire/Sway)."""
    #logger.info("get_display_output_name() LANCÉ")
    
    try:
        # Test wlr-randr (Wayfire/Pi OS)
        logger.debug("🖥 Test wlr-randr...")
        result = subprocess.run(
            ["wlr-randr"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5
        )
        #logger.debug(f"🖥 wlr-randr RC={result.returncode} STDOUT={result.stdout}")
        
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line and not line[0].isspace():
                    output = line.split()[0]
                    logger.info(f"✅ Output détecté: {output}")
                    #print(f"SORTIE: {output}")  # Info user
                    return output
        
        # Fallback Sway
        logger.debug("🖥 Fallback sway...")
        env = os.environ.copy()
        if "SWAYSOCK" not in env:
            uid = os.getuid()
            socks = glob.glob(f"/run/user/{uid}/sway-ipc.*")
            if socks:
                env["SWAYSOCK"] = socks[0]
        
        result = subprocess.run(
            ["swaymsg", "-t", "get_outputs"],
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
            check=False
        )
        
        if result.returncode == 0:
            outputs = json.loads(result.stdout)
            logger.debug(f"🖥 sway: {len(outputs)} outputs")
            
            for o in outputs:
                name = o.get("name", "?")
                active = o.get("active", False)
                logger.debug(f"sway: {name} active={active}")
                
                if active or o.get("current_mode"):
                    logger.info(f"✅ SWAY HDMI: {name}")
                    return name
        
        logger.warning("😒 0x0 - AUCUNE SORTIE")
        return None
        
    except Exception as e:
        logger.error(f"❌ ERREUR: {e}")
        return None


def send_smart_plug_command(url):
    """Envoi commande HTTP à la prise connectée."""
    if not url:
        return False, "Pas d'URL"
    
    try:
        logger.info(f"Envoi commande prise: {url}")
        r = requests.post(url, timeout=5)
        logger.debug(f"Prise réponse: {r.status_code}")
        
        if 200 <= r.status_code < 300:
            print(f"Commande prise envoyée: {url}")
            logger.info("✅ Commande prise OK")
            return True, "OK"
        
        logger.warning(f"😒 Erreur HTTP: {r.status_code}")
        return False, f"Erreur {r.status_code}"
        
    except Exception as e:
        logger.error(f"❌ Exception requête: {e}")
        return False, str(e)


def set_display_power(on=True):
    """Allume/éteint l'écran (prise ou logiciel)."""
    logger.info(f"⏻ set_display_power({on})")
    config = load_config()
    
    if config.get("smart_plug_enabled"):
        if on:
            # Allumage prise
            on_url = config.get("smart_plug_on_url")
            success, msg = send_smart_plug_command(on_url)
            
            if not success:
                logger.error(f"❌ Échec prise: {msg}")
                return False, f"Échec prise: {msg}"
            
            delay = int(config.get("smart_plug_on_delay", 5))
            logger.info(f"⏳ Attente {delay}s pour init écran...")
            time.sleep(delay)
            
            # Reboot pour HDMI stable
            flag_path = LOGSDIR / "pimmich_reboot_flag.tmp"
            flag_path.parent.mkdir(exist_ok=True)
            flag_path.touch()
            logger.info("✅ ⏻ Reboot pour résolution HDMI...")
            os.system("sudo reboot")
            return True, "Reboot initié"
        else:
            # Extinction DPMS puis prise
            logger.info("⏻ Extinction DPMS puis prise")
            set_software_display_power(False)
            time.sleep(1)
            
            off_url = config.get("smart_plug_off_url")
            success, msg = send_smart_plug_command(off_url)
            
            if success:
                logger.info("✅ Prise éteinte OK")
            else:
                logger.warning(f"😒 Échec extinction prise: {msg}")
            
            return success, msg
    else:
        logger.info("⏻ Pas de prise, DPMS uniquement.")
        return set_software_display_power(on)


def set_software_display_power(on=True):
    """Active/désactive DPMS via wlr-randr/swaymsg."""
    #logger.info(f"set_software_display_power({on})")
    output = get_display_output_name()
    
    if not output:
        logger.warning("🖥😒 Pas de HDMI.")
        return False, "Pas de HDMI"
    
    state = "on" if on else "off"
    
    try:
        # Test wlr-randr
        cmd = ["wlr-randr", "--output", output, f"--{state}"]
        logger.info(f"🖥️ Commande: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            timeout=5,
            capture_output=True,
            text=True,
            check=False
        )
        logger.debug(f"🖥️ wlr DPMS: RC={result.returncode} STDOUT={result.stdout.strip()} ERR={result.stderr.strip()}")
        
        if result.returncode == 0:
            logger.info(f"🖥️✅ Écran {output} -> {state} via wlr-randr.")
            return True, "OK"
        
        # Fallback swaymsg
        logger.info("🖥️Fallback swaymsg DPMS...")
        result = subprocess.run(
            ["swaymsg", "output", output, "dpms", state],
            timeout=5,
            capture_output=True,
            text=True
        )
        logger.debug(f"🖥️sway DPMS: RC={result.returncode}")
        
        if result.returncode == 0:
            logger.info(f"🖥️✅ Écran {output} -> {state} via swaymsg.")
            return True, "OK"
        else:
            logger.warning(f"🖥️😒 Échec swaymsg DPMS: RC={result.returncode}")
            return False, "Échec DPMS"
            
    except Exception as e:
        err_msg = f"🖥️Erreur DPMS: {e}"
        logger.error(f"❌ {err_msg}")
        return False, err_msg
