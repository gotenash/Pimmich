import os
import json
import sys
import time
import traceback
from pathlib import Path
import re

import requests
import sounddevice as sd
import pvporcupine
import numpy as np
import resampy
import pygame
from vosk import KaldiRecognizer, Model
from thefuzz import process
from num2words import num2words

from utils.config_manager import load_config
from utils.voice_control_manager import PID_FILE as VOICE_PID_FILE, update_status_file

# --- NOUVEAU: Gestion des sons ---
sounds = {}

def play_sound(sound_name):
    """Joue un son préchargé depuis le dictionnaire 'sounds'."""
    if sound_name in sounds and sounds[sound_name]:
        # Attendre qu'un autre son finisse de jouer pour éviter les superpositions
        while pygame.mixer.get_busy():
            time.sleep(0.1)
        sounds[sound_name].play()
    else:
        print(f"[Voice] Avertissement: Son '{sound_name}.wav' non trouvé ou non chargé.")

# --- Configuration ---
BASE_DIR = Path(__file__).resolve().parent

# --- Fonctions d'appel API ---

def send_simple_api_command(endpoint, method='POST', data=None):
    """Fonction générique pour envoyer des commandes simples à l'API."""
    api_url = f"http://127.0.0.1:5000/api/{endpoint}"
    try:
        print(f"[Voice] Envoi de la commande vers : {api_url}")
        if method.upper() == 'POST':
            response = requests.post(api_url, json=data, timeout=5)
        else:
            response = requests.get(api_url, timeout=5)

        # Log de débogage pour voir la réponse BRUTE du serveur
        print(f"[Voice] Réponse reçue. Statut: {response.status_code}. Contenu: {response.text}")

        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        error_message = f"Erreur API ({endpoint}): {e}"
        print(f"[Voice] {error_message}")
        update_status_file({"status": "error", "message": error_message})
        return None

def send_slideshow_command(command):
    send_simple_api_command(f"slideshow/{command}")

def get_playlist_names_for_grammar():
    """Tente de récupérer les noms de playlists, avec quelques tentatives pour gérer les race conditions au démarrage."""
    for i in range(3): # Tenter 3 fois
        try:
            response = requests.get("http://127.0.0.1:5000/api/playlists", timeout=5)
            if response.ok:
                playlists = response.json()
                if isinstance(playlists, list):
                    print("[Voice] Playlists récupérées avec succès pour la grammaire.")
                    return [p['name'].lower() for p in playlists]
            print(f"[Voice] Tentative {i+1}/3: Le serveur n'a pas retourné de playlists valides (code: {response.status_code}).")
        except requests.RequestException as e:
            print(f"[Voice] Tentative {i+1}/3: Erreur de connexion pour récupérer les playlists : {e}")
        
        if i < 2: time.sleep(3) # Attendre 3 secondes avant de réessayer
    
    print("[Voice] AVERTISSEMENT: Impossible de récupérer les playlists pour la grammaire vocale après plusieurs tentatives.")
    return []

def play_playlist_by_name(recognized_text):
    """Trouve une playlist par son nom et demande sa lecture en utilisant la reconnaissance approximative."""
    print(f"[Voice] Trying to play playlist by matching: '{recognized_text}'")
    try:
        # 1. Récupérer la liste des playlists
        response = requests.get("http://127.0.0.1:5000/api/playlists", timeout=5)
        response.raise_for_status()
        playlists = response.json()

        if not playlists:
            print("[Voice] Aucune playlist trouvée sur le serveur.")
            return

        # 2. Créer un dictionnaire de "noms parlés" pour le matching
        spoken_name_map = {}
        for p in playlists:
            original_name = p['name']
            spoken_name_parts = []
            for word in original_name.lower().split():
                if word.isdigit():
                    # Convertit "2025" en "deux mille vingt-cinq"
                    spoken_name_parts.append(num2words(int(word), lang='fr').replace('-', ' '))
                else:
                    spoken_name_parts.append(word)
            spoken_name = ' '.join(spoken_name_parts)
            spoken_name_map[spoken_name] = {'id': p['id'], 'name': original_name}

        # 3. Trouver la correspondance la plus proche dans les noms parlés
        best_match_spoken, score = process.extractOne(recognized_text, spoken_name_map.keys())

        # On peut être un peu plus tolérant sur le score car la conversion n'est pas parfaite
        if score >= 70:
            playlist_data = spoken_name_map[best_match_spoken]
            target_playlist_id = playlist_data['id']
            original_playlist_name = playlist_data['name']
            
            play_sound('command_playlist')
            print(f"Commande '{recognized_text}' correspond à la playlist '{original_playlist_name}' (score: {score}).")
            
            # 4. Lancer la lecture avec l'ID
            play_response = requests.post(
                "http://127.0.0.1:5000/api/playlists/play",
                json={'id': target_playlist_id},
                timeout=5
            )
            play_response.raise_for_status()
            print(f"[Voice] Commande de lecture envoyée pour la playlist '{original_playlist_name}'.")
        else:
            print(f"[Voice] Playlist '{recognized_text}' non trouvée (meilleur résultat '{best_match_spoken}' avec un score de {score} est trop bas).")
            play_sound('not_understood')
            return

    except requests.RequestException as e:
        error_message = f"Erreur API Playlist: {e}"
        print(f"[Voice] {error_message}")
        update_status_file({"status": "error", "message": error_message})

def process_command(command_text):
    """Interprète le texte de la commande et envoie l'action correspondante."""
    if not command_text:
        print("[Voice] Aucune commande audible n'a été comprise.")
        play_sound('not_understood')
        return

    print(f"[Voice] Commande reconnue: '{command_text}'")

    # Commandes simples
    simple_commands = {
        "photo suivante": ("command_next", lambda: send_simple_api_command("slideshow/next")),
        "photo précédente": ("command_previous", lambda: send_simple_api_command("slideshow/previous")),
        "pause": ("command_pause", lambda: send_simple_api_command("slideshow/toggle_pause")),
        "lecture": ("command_play", lambda: send_simple_api_command("slideshow/toggle_pause")),
        "éteindre le cadre": ("command_shutdown", lambda: send_simple_api_command("system/shutdown")),
        "passer en mode veille": ("command_sleep", lambda: send_simple_api_command("display/power", data={'state': 'off'})),
        "réveiller le cadre": ("command_wakeup", lambda: send_simple_api_command("display/power", data={'state': 'on'})),
        "afficher les cartes postales": ("command_show_postcards", lambda: send_simple_api_command("sources/play/telegram")),
    }

    for phrase, (sound, action) in simple_commands.items():
        if phrase in command_text:
            play_sound(sound)
            action()
            return

    # Commande pour changer la durée
    duration_match = re.search(r"(?:durée|pendant)\s+(\d+)\s*seconde?s?", command_text)
    if duration_match:
        try:
            duration = int(duration_match.group(1))
            if 5 <= duration <= 120: # Limites raisonnables (5s à 2 minutes)
                play_sound('command_duration_set')
                send_simple_api_command("slideshow/set_duration", data={'duration': duration})
                return
            else:
                print(f"[Voice] Durée demandée ({duration}s) hors des limites (5-120s).")
                play_sound('not_understood')
                return
        except (ValueError, IndexError):
            pass # L'extraction a échoué, on continue pour voir si une autre commande correspond

    # Commandes complexes (avec arguments)
    # Match "lance la playlist <nom>" or "lancer la playlist <nom>" (also with "playliste")
    match = re.search(r"(?:lance|lancer)\s+la\s+playliste?\s+(.+)", command_text)
    if match:
        playlist_name = match.group(1).strip()
        if playlist_name:
            play_playlist_by_name(playlist_name)
        else:
            play_sound('playlist_name_missing')
        return
    if "activer la source" in command_text or "désactiver la source" in command_text:
        parts = command_text.split("la source")
        if len(parts) > 1:
            # CORRECTION: On vérifie "désactiver" en premier pour éviter la confusion
            # car "activer" est contenu dans "désactiver".
            action = "off" if "désactiver" in parts[0] else "on"
            source_name = parts[1].strip()
            
            # Mapper les noms de source parlés aux noms techniques
            source_map = {
                "samba": "samba", "immich": "immich", "usb": "usb", "u s b": "usb",
                "telegram": "telegram", "smartphone": "smartphone"            }
            
            if source_name in source_map:
                play_sound('command_source_toggle')
                send_simple_api_command("sources/toggle", data={'source': source_map[source_name], 'state': action})
            else:
                play_sound('not_understood')
            return

    play_sound('not_understood')
    print(f"[Voice] Commande non comprise: '{command_text}'")

def save_and_play_debug_audio(audio_buffer, samplerate):
    """Sauvegarde l'audio du buffer et le joue pour le débogage."""
    if not audio_buffer:
        return
    
    full_audio_data = np.concatenate(audio_buffer)
    max_amplitude = np.max(np.abs(full_audio_data))
    print(f"[Voice] Débogage audio : Amplitude maximale de la commande = {max_amplitude:.0f}")
    if max_amplitude < 1000:
        print("[Voice] AVERTISSEMENT: Le volume de la commande est très faible. Vérifiez les réglages du microphone (ex: 'alsamixer').")

    import wave
    debug_wav_path = "/tmp/last_command.wav"
    try:
        with wave.open(debug_wav_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2) # 16-bit
            wf.setframerate(samplerate)
            wf.writeframes(full_audio_data.tobytes())
        
        # La lecture de l'audio de débogage est maintenant désactivée.
        # print("[Voice] Lecture de la commande enregistrée pour le débogage...")
        # pygame.mixer.Sound(debug_wav_path).play()
    except Exception as e:
        print(f"[Voice] Erreur lors de la sauvegarde/lecture de l'audio de débogage : {e}")

def main():
    """Fonction principale du contrôle vocal."""
    try:
        # --- Initialisation ---
        update_status_file({"status": "starting", "message": "Démarrage du service vocal..."})
        config = load_config()
        
        # --- NOUVEAU: Initialisation de Pygame et chargement des sons ---
        pygame.mixer.init()
        sound_files = {
            'listening': 'listening.wav',
            'not_understood': 'not_understood.wav',
            'command_next': 'command_next.wav',
            'command_previous': 'command_previous.wav',
            'command_pause': 'command_pause.wav',
            'command_play': 'command_play.wav',
            'command_playlist': 'command_playlist.wav', 'playlist_name_missing': 'playlist_name_missing.wav',
            'command_shutdown': 'command_shutdown.wav', 'command_sleep': 'command_sleep.wav',
            'command_wakeup': 'command_wakeup.wav', 'command_show_postcards': 'command_show_postcards.wav',
            'command_source_toggle': 'command_source_toggle.wav',
            'command_duration_set': 'command_duration_set.wav' # Son pour confirmer le changement de durée
        }
        sounds_dir = BASE_DIR / 'static' / 'sounds'
        for name, filename in sound_files.items():
            path = sounds_dir / filename
            if path.exists():
                try:
                    sounds[name] = pygame.mixer.Sound(str(path))
                    print(f"[Voice] Son '{filename}' chargé.")
                except Exception as e:
                    print(f"[Voice] Avertissement: Impossible de charger le son '{filename}': {e}")
                    sounds[name] = None
            else:
                # Ce n'est pas une erreur, l'utilisateur n'a peut-être pas créé tous les sons
                sounds[name] = None

        # --- Porcupine (Wake Word) ---
        porcupine_access_key = config.get("porcupine_access_key")
        if not porcupine_access_key or not porcupine_access_key.strip():
            raise ValueError("La clé d'accès Porcupine est manquante ou vide dans la configuration.")
        
        keyword_path = str(BASE_DIR / "voice_models" / "cadre-magique_raspberry-pi.ppn")
        if not os.path.exists(keyword_path):
            raise FileNotFoundError(f"Modèle de mot-clé '{keyword_path}' non trouvé. Veuillez l'entraîner sur la console Picovoice.")

        # Le mot-clé "Cadre Magique" est en français, nous devons donc charger
        # le modèle de langue français fourni avec la bibliothèque Porcupine.
        try:
            porcupine_dir = os.path.dirname(pvporcupine.__file__)
            model_path_fr = os.path.join(porcupine_dir, 'lib/common/porcupine_params_fr.pv')
        except Exception as e:
            raise IOError(f"Impossible de construire le chemin vers le modèle de langue Porcupine : {e}")

        if not os.path.exists(model_path_fr):
            raise FileNotFoundError(
                f"Le modèle de langue français de Porcupine est introuvable ici : {model_path_fr}. "
                "Vérifiez l'installation du paquet 'pvporcupine'. Essayez : pip install --force-reinstall pvporcupine"
            )

        try:
            porcupine = pvporcupine.create(
                access_key=porcupine_access_key,
                keyword_paths=[keyword_path],
                model_path=model_path_fr # Spécifier le modèle français
            )
        except pvporcupine.PorcupineInvalidArgumentError as e:
            raise ValueError(
                "Le fichier de mot-clé (.ppn) est incorrect. "
                "Assurez-vous de l'avoir généré pour la plateforme 'Raspberry Pi' sur la console Picovoice. "
                f"Erreur originale: {e}"
            )
        
        TARGET_SAMPLERATE = porcupine.sample_rate # C'est 16000

        # --- NOUVEAU: Déterminer la fréquence native et adapter la taille de lecture ---
        # Logique de sélection de microphone plus robuste
        try:
            device_index_str = config.get("voice_control_device_index")
            device_info = None

            # Essayer d'utiliser l'index spécifié s'il est valide
            if device_index_str and str(device_index_str).strip():
                try:
                    device_index = int(device_index_str)
                    # On vérifie que le périphérique existe ET qu'il est bien une entrée
                    queried_device = sd.query_devices(device_index)
                    if queried_device['max_input_channels'] > 0:
                        device_info = queried_device
                        print(f"[Voice] Utilisation du microphone spécifié : [{device_index}] {device_info['name']}")
                    else:
                        print(f"[Voice] AVERTISSEMENT: Le périphérique {device_index} n'est pas un microphone. Utilisation du périphérique par défaut.")
                except (ValueError, TypeError):
                    print(f"[Voice] AVERTISSEMENT: Index de périphérique invalide '{device_index_str}'. Utilisation du périphérique par défaut.")
                except Exception: # Catches errors from query_devices if index is out of bounds
                     print(f"[Voice] AVERTISSEMENT: Périphérique avec l'index {device_index_str} non trouvé. Utilisation du périphérique par défaut.")

            # Si aucun périphérique n'a été trouvé ou si l'index était invalide, on prend le défaut
            if device_info is None:
                device_info = sd.query_devices(kind='input')
                print(f"[Voice] Utilisation du microphone par défaut : {device_info['name']}")

            native_samplerate = int(device_info['default_samplerate'])
            print(f"[Voice] Fréquence native du micro : {native_samplerate} Hz.")
        except Exception as e:
            raise IOError(f"Impossible de récupérer les informations du microphone. Erreur: {e}")

        # Calculer le nombre de frames à lire à la fréquence native pour obtenir
        # l'équivalent d'un frame_length à la fréquence cible.
        read_frame_length = int(porcupine.frame_length * native_samplerate / TARGET_SAMPLERATE)
        print(f"[Voice] Lecture de blocs de {read_frame_length} samples pour obtenir {porcupine.frame_length} samples à {TARGET_SAMPLERATE}Hz.")

        # --- Vosk (Speech-to-Text) ---
        update_status_file({"status": "starting", "message": "Chargement du modèle de langue (Vosk)..."})
        print("[Voice] Loading Vosk language model...")
        vosk_model_path = str(BASE_DIR / "models" / "vosk-model-small-fr-0.22")
        if not os.path.exists(vosk_model_path):
            raise FileNotFoundError(f"Modèle Vosk non trouvé : {vosk_model_path}. Veuillez lancer setup.sh.")
        
        vosk_model = Model(vosk_model_path)
        # Initialiser Vosk avec la fréquence cible
        recognizer = KaldiRecognizer(vosk_model, TARGET_SAMPLERATE)

        # --- NOUVEAU: Définir une grammaire pour améliorer la précision ---
        playlist_names = get_playlist_names_for_grammar()

        # 2. Construire le vocabulaire
        base_commands = [
            "photo", "suivante", "précédente", "pause", "lecture", "lance", "lancer", "la", "playlist",
            "éteindre", "le", "cadre", "passer", "en", "mode", "veille", "réveiller",
            "afficher", "les", "cartes", "postales", "reçues", "activer", "désactiver", "source", "samba", "immich",
            "usb", "u", "s", "b", "telegram", "smartphone",
            "durée", "pendant", "secondes", "cinq", "dix", "quinze", "vingt", "trente", "soixante", "[unk]"
        ]
        for name in playlist_names:
            for word in name.split():
                if word.isdigit():
                    # Convertit "2025" en "deux mille vingt-cinq" et ajoute chaque mot
                    try:
                        num_in_words = num2words(int(word), lang='fr')
                        # Sépare les mots comme "vingt-cinq" en "vingt" et "cinq"
                        base_commands.extend(num_in_words.replace('-', ' ').split())
                    except ValueError:
                        # Au cas où ce n'est pas un vrai nombre, on l'ajoute tel quel
                        base_commands.append(word)
                else:
                    base_commands.append(word)

        vocabulary = list(set(base_commands))
        grammar = json.dumps(vocabulary, ensure_ascii=False)
        # Log détaillé pour le débogage
        print(f"[Voice] Grammaire de reconnaissance vocale définie avec {len(vocabulary)} mots : {', '.join(vocabulary)}")
        recognizer.SetGrammar(grammar)

        # --- Audio Stream ---
        device_index = config.get("voice_control_device_index")
        # CORRECTION: Gérer le cas où la valeur est une chaîne vide (pour "Périphérique par défaut")
        if device_index is not None and str(device_index).strip() != "":
            try:
                device_index = int(device_index)
            except (ValueError, TypeError):
                print(f"[Voice] Index de périphérique invalide '{device_index}', utilisation du périphérique par défaut.")
                device_index = None
        else:
            # Si la valeur est vide ou None, on utilise le périphérique par défaut.
            device_index = None

        print(f"[Voice] Opening audio stream on device: {'Default' if device_index is None else device_index}")
        update_status_file({"status": "running", "message": "En attente du mot-clé 'Cadre Magique'..."})

        with sd.RawInputStream(
            samplerate=native_samplerate, # On utilise la fréquence native
            blocksize=read_frame_length,
            device=device_index,
            dtype='int16',
            channels=1
        ) as stream:
            print("[Voice] Service démarré. En écoute...")
            listening_for_command = False
            audio_buffer = []
            command_timeout = 0

            while True:
                # Lire un bloc de données audio
                pcm_bytes, _ = stream.read(read_frame_length)

                # Convertir en numpy array pour le ré-échantillonnage
                audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

                # Ré-échantillonner vers la fréquence cible de Porcupine/Vosk
                resampled_audio = resampy.resample(
                    audio_np,
                    native_samplerate,
                    TARGET_SAMPLERATE,
                    filter='kaiser_fast' # Bon compromis performance/qualité
                )
                
                # Convertir le résultat en int16
                frame = (resampled_audio * 32767).astype(np.int16)

                # S'assurer que le frame a la bonne taille (512)
                if len(frame) > porcupine.frame_length:
                    frame = frame[:porcupine.frame_length]
                elif len(frame) < porcupine.frame_length:
                    padding = np.zeros(porcupine.frame_length - len(frame), dtype=np.int16)
                    frame = np.concatenate([frame, padding])

                if not listening_for_command:
                    # Phase 1: Détection du mot-clé
                    result = porcupine.process(frame)
                    if result >= 0:
                        print("[Voice] Wake word 'Cadre Magique' detected!")
                        play_sound('listening')
                        listening_for_command = True
                        command_timeout = time.time() + 5  # 5 secondes pour donner une commande
                        audio_buffer = [] # Réinitialiser le buffer pour la nouvelle commande
                        update_status_file({"status": "listening", "message": "J'écoute votre commande..."})
                else:
                    # Phase 2: Reconnaissance de la commande
                    audio_buffer.append(frame)
                    
                    command_to_process = None
                    
                    # On vérifie si Vosk a détecté une fin de phrase (plus réactif).
                    if recognizer.AcceptWaveform(frame.tobytes()):
                        res = json.loads(recognizer.Result())
                        command_to_process = res.get('text', '').lower().strip()
                    
                    # On vérifie aussi le timeout comme sécurité.
                    elif time.time() > command_timeout:
                        res = json.loads(recognizer.FinalResult())
                        command_to_process = res.get('text', '').lower().strip()

                    # Si une commande a été détectée (par l'une ou l'autre méthode)
                    if command_to_process is not None:
                        # Sauvegarder l'audio pour un éventuel débogage, mais sans le jouer.
                        save_and_play_debug_audio(audio_buffer, TARGET_SAMPLERATE)
                        
                        # On traite la commande
                        process_command(command_to_process)
                        
                        # Et on sort du mode écoute
                        listening_for_command = False
                        update_status_file({"status": "running", "message": "En attente du mot-clé 'Cadre Magique'..."})

    except Exception as e:
        print(f"[Voice] FATAL ERROR: {e}")
        traceback.print_exc()
        update_status_file({"status": "error", "message": str(e)})
    finally:
        if 'porcupine' in locals() and porcupine:
            porcupine.delete()
        if os.path.exists(VOICE_PID_FILE):
            os.remove(VOICE_PID_FILE)
        print("[Voice] Service arrêté.")

if __name__ == "__main__":
    try:
        with open(VOICE_PID_FILE, "w") as f:
            f.write(str(os.getpid()))
        main()
    except Exception as e:
        update_status_file({"status": "error", "message": f"Erreur au lancement: {e}"})
        if os.path.exists(VOICE_PID_FILE):
            os.remove(VOICE_PID_FILE)
        sys.exit(1)