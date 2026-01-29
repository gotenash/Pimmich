#!/usr/bin/env python3
# Gestionnaire d'affichage Pimmich - VERSION IDÉALE SIGALOU 2026-01-25
# MODIFICATION SIGALOU - 25/01/2026: Fusion des versions stables pour corriger cycles HDMI/signal perdu.
# RAISON: wlr-randr prioritaire pour Wayfire/Pi OS (évite BadRROutput), logs debug pour tracer, timeouts anti-blocage.
# ÉLÉMENTS CONSERVÉS: Détection robuste HDMI, smartplug + DPMS séquentiel, reboot flag pour résolution stable.
# SUPPRIMÉ: Prints excessifs (gardés en log), doublons ; ajouté timeout=5s partout.

import os
import subprocess
import time
import json
import glob
import requests
from pathlib import Path
from .config_manager import load_config

# Logs debug pour tracer cycles HDMI sans spam console
LOGSDIR = Path(__file__).resolve().parent.parent / "logs"
DEBUGLOG = LOGSDIR / "displaydebug.log"

def log_debug(msg):
    """Log debug avec timestamp dans fichier + console réduite."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"{timestamp} [DISPLAY_DEBUG] {msg}"
    print(full_msg, file=open("slideshowstdout.log", "a"))  # Backup console
    try:
        LOGSDIR.mkdir(exist_ok=True)
        with open(DEBUGLOG, "a", encoding="utf-8") as f:
            f.write(full_msg + "\n")
            f.flush()
    except:
        pass  # Ignore erreurs disque

log_debug("DISPLAY_MANAGER CHARGÉ SANS CRASH - VERSION SIGALOU")

def get_display_output_name():
    """Trouve nom sortie HDMI active (Wayfire/Sway)."""
    # MODIFICATION SIGALOU - 25/01/2026: wlr-randr prioritaire pour Pi OS Wayfire.
    # RAISON: Corrige détection 0x0 -> 1920x1080, évite écran noir/HDMI perdu.
    log_debug("get_display_output_name LANCÉ")
    try:
        # Test wlr-randr (Wayfire/Pi OS)
        log_debug("wlr-randr...")
        result = subprocess.run(["wlr-randr"], capture_output=True, text=True, check=False, timeout=5)
        log_debug(f"wlr RC:{result.returncode} STDOUT:{result.stdout[:200]}...")
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line and not line[0].isspace():
                    output = line.split()[0]
                    log_debug(f"Output detected: {output}")
                    print(f"SORTIE {output}")  # Info user
                    return output
        # Fallback Sway
        log_debug("sway...")
        env = os.environ.copy()
        if "SWAYSOCK" not in env:
            uid = os.getuid()
            socks = glob.glob(f"/run/user/{uid}/sway-ipc.*")
            if socks:
                env["SWAYSOCK"] = socks[0]
        result = subprocess.run(["swaymsg", "-t", "get_outputs"], capture_output=True, text=True,
                                env=env, timeout=5, check=False)
        if result.returncode == 0:
            outputs = json.loads(result.stdout)
            log_debug(f"sway {len(outputs)} outputs")
            for o in outputs:
                name = o.get("name", "?")
                active = o.get("active", False)
                log_debug(f"sway {name} active:{active}")
                if active or o.get("current_mode"):
                    log_debug(f"SWAY HDMI: {name}")
                    return name
        log_debug("0x0 - AUCUNE SORTIE")
        return None
    except Exception as e:
        log_debug(f"ERREUR: {e}")
        return None

def send_smartplug_command(url):
    """Envoi HTTP à prise connectée."""
    if not url:
        return False, "Pas d'URL"
    try:
        log_debug(f"Envoi commande prise: {url}")
        r = requests.post(url, timeout=5)
        log_debug(f"Prise réponse: {r.status_code}")
        if 200 <= r.status_code < 300:
            print(f"Commande prise envoyée: {url}")
            return True, "OK"
        return False, f"Erreur {r.status_code}"
    except Exception as e:
        return False, str(e)

def set_display_power(on):
    """Allume/éteint écran (prise ou logiciel)."""
    # MODIFICATION SIGALOU - 25/01/2026: Séquence sûre prise+DPMS.
    # RAISON: Évite cycles HDMI brutaux ; reboot force résolution post-prise.
    log_debug(f"set_display_power({on})")
    config = load_config()
    if config.get("smartplug_enabled"):
        if on:
            # Allumage prise + reboot pour HDMI stable
            on_url = config.get("smartplug_on_url")
            success, msg = send_smartplug_command(on_url)
            if not success:
                return False, f"Échec prise: {msg}"
            delay = int(config.get("smartplug_on_delay", 5))
            print(f"Attente {delay}s pour init écran...")
            time.sleep(delay)
            # Flag + reboot
            flag_path = LOGSDIR / "pimmichrebootflag.tmp"
            flag_path.parent.mkdir(exist_ok=True)
            flag_path.touch()
            print("Display Manager: Reboot pour résolution HDMI...")
            os.system("sudo reboot")
            return True, "Reboot initié"
        else:
            # Extinction: DPMS puis prise
            set_software_display_power(False)
            time.sleep(1)  # Pause stabilise
            off_url = config.get("smartplug_off_url")
            return send_smartplug_command(off_url)
    else:
        # Logiciel only
        print("Display Manager: Pas de prise, DPMS uniquement.")
        return set_software_display_power(on)

def set_software_display_power(on):
    """DPMS via wlr-randr/swaymsg."""
    # MODIFICATION SIGALOU - 25/01/2026: wlr-randr --on/off prioritaire.
    # RAISON: Fix Wayfire "BadRROutput" -> HDMI stable, no signal perdu.
    log_debug(f"set_software_display_power({on})")
    output = get_display_output_name()
    if not output:
        print("Display Manager: Pas de HDMI.")
        return False, "Pas de HDMI"
    state = "on" if on else "off"
    try:
        # wlr-randr first (Wayfire/Pi)
        cmd = ["wlr-randr", "--output", output, f"--{state}"]
        log_debug(f"Commande: {' '.join(cmd)}")
        result = subprocess.run(cmd, timeout=5, capture_output=True, text=True, check=False)
        log_debug(f"wlr DPMS RC:{result.returncode} STDOUT:{result.stdout.strip()} ERR:{result.stderr.strip()}")
        if result.returncode == 0:
            print(f"Écran {output} -> {state} via wlr-randr.")
            return True, "OK"
        # Fallback sway
        log_debug("Fallback swaymsg DPMS...")
        result = subprocess.run(["swaymsg", "output", output, "dpms", state],
                                timeout=5, capture_output=True, text=True)
        log_debug(f"sway DPMS RC:{result.returncode}")
        print(f"Écran {output} -> {state} via swaymsg.")
        return True, "OK"
    except Exception as e:
        err_msg = f"Erreur DPMS: {e}"
        log_debug(err_msg)
        return False, err_msg
