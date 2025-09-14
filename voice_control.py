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

# --- I18N Command Definitions ---
COMMANDS = {
    'fr': {
        'simple_commands': {
            "photo suivante": ("command_next", lambda: send_simple_api_command("slideshow/next")),
            "photo précédente": ("command_previous", lambda: send_simple_api_command("slideshow/previous")),
            "pause": ("command_pause", lambda: send_simple_api_command("slideshow/toggle_pause")),
            "lecture": ("command_play", lambda: send_simple_api_command("slideshow/toggle_pause")),
            "éteindre le cadre": ("command_shutdown", lambda: send_simple_api_command("system/shutdown")),
            "passer en mode veille": ("command_sleep", lambda: send_simple_api_command("display/power", data={'state': 'off'})),
            "réveiller le cadre": ("command_wakeup", lambda: send_simple_api_command("display/power", data={'state': 'on'})),
            "afficher les cartes postales": ("command_show_postcards", lambda: send_simple_api_command("sources/play/telegram")),
            "revenir au diaporama principal": ("command_back_to_main", lambda: send_simple_api_command("slideshow/restart_standard")),
        },
        'duration_regex': r"(?:durée|pendant)\s+(\d+)\s*seconde?s?",
        'playlist_regex': r"(?:lance|lancer)\s+la\s+playliste?\s+(.+)",
        'source_regex_trigger': "la source",
        'source_action_map': {"désactiver": "off", "activer": "on"},
        'num2words_lang': 'fr',
        'wake_word_message': "En attente du mot-clé 'Cadre Magique'...",
        'listening_message': "J'écoute votre commande..."
    },
    'en': {
        'simple_commands': {
            "next photo": ("command_next", lambda: send_simple_api_command("slideshow/next")),
            "previous photo": ("command_previous", lambda: send_simple_api_command("slideshow/previous")),
            "pause": ("command_pause", lambda: send_simple_api_command("slideshow/toggle_pause")),
            "play": ("command_play", lambda: send_simple_api_command("slideshow/toggle_pause")),
            "shut down the frame": ("command_shutdown", lambda: send_simple_api_command("system/shutdown")),
            "sleep mode": ("command_sleep", lambda: send_simple_api_command("display/power", data={'state': 'off'})),
            "wake up the frame": ("command_wakeup", lambda: send_simple_api_command("display/power", data={'state': 'on'})),
            "show postcards": ("command_show_postcards", lambda: send_simple_api_command("sources/play/telegram")),
            "return to main slideshow": ("command_back_to_main", lambda: send_simple_api_command("slideshow/restart_standard")),
        },
        'duration_regex': r"(?:duration|for)\s+(\d+)\s*seconds?",
        'playlist_regex': r"play(?:list)?\s+(.+)",
        'source_regex_trigger': "source",
        'source_action_map': {"disable": "off", "enable": "on", "activate": "on", "deactivate": "off"},
        'num2words_lang': 'en',
        'wake_word_message': "Waiting for wake word...",
        'listening_message': "Listening for your command..."
    }
}

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

def send_simple_api_command(endpoint, method='POST', data=None, timeout=5):
    """Fonction générique pour envoyer des commandes simples à l'API."""
    api_url = f"http://127.0.0.1:5000/api/{endpoint}"
    try:
        print(f"[Voice] Envoi de la commande vers : {api_url} (timeout: {timeout}s)")
        if method.upper() == 'POST':
            response = requests.post(api_url, json=data, timeout=timeout)
        else:
            response = requests.get(api_url, timeout=timeout)

        # Log de débogage pour voir la réponse BRUTE du serveur
        print(f"[Voice] Réponse reçue. Statut: {response.status_code}. Contenu: {response.text}")

        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        error_message = f"Erreur API ({endpoint}): {e}"
        print(f"[Voice] {error_message}")
        update_status_file({"status": "error", "message": error_message})
        return None

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

def play_playlist_by_name(recognized_text, lang='fr'):
    """
    Trouve une playlist par son nom et demande sa lecture.
    Utilise une reconnaissance approximative sur plusieurs alias (nom original, nom "parlé") pour plus de robustesse.
    """
    print(f"[Voice] Trying to play playlist by matching: '{recognized_text}'")
    try:
        # 1. Récupérer la liste des playlists
        response = requests.get("http://127.0.0.1:5000/api/playlists", timeout=5)
        response.raise_for_status()
        playlists = response.json()

        if not playlists:
            print("[Voice] Aucune playlist trouvée sur le serveur.")
            play_sound('not_understood')
            return

        # 2. Créer un dictionnaire de "noms de recherche" (alias) vers les données de la playlist
        search_map = {}
        for p in playlists:
            original_name = p['name']
            
            # Alias 1: nom original en minuscules
            search_map[original_name.lower()] = {'id': p['id'], 'name': original_name}
            
            # Alias 2: nom "parlé" avec les chiffres convertis en mots
            spoken_name_parts = []
            for word in original_name.lower().split():
                if word.isdigit():
                    try:
                        spoken_name_parts.append(num2words(int(word), lang=COMMANDS[lang]['num2words_lang']).replace('-', ' '))
                    except ValueError:
                        spoken_name_parts.append(word) # Fallback si ce n'est pas un vrai nombre
                else:
                    spoken_name_parts.append(word)
            spoken_name = ' '.join(spoken_name_parts)
            
            if spoken_name != original_name.lower():
                 search_map[spoken_name] = {'id': p['id'], 'name': original_name}

        # 3. Trouver la correspondance la plus proche dans tous les alias
        best_match, score = process.extractOne(recognized_text, search_map.keys())

        # On utilise un seuil de 80 pour être assez confiant
        if score >= 80:
            playlist_data = search_map[best_match]
            target_playlist_id = playlist_data['id']
            original_playlist_name = playlist_data['name']
            
            play_sound('command_playlist')
            print(f"Commande '{recognized_text}' correspond à la playlist '{original_playlist_name}' (alias: '{best_match}', score: {score}).")
            
            # 4. Lancer la lecture avec l'ID
            # Utiliser un timeout plus long car le redémarrage du diaporama peut prendre du temps.
            play_response = send_simple_api_command("playlists/play", data={'id': target_playlist_id}, timeout=30)
            
            # Vérifier si la commande a été acceptée par le serveur.
            if play_response and play_response.get('success'):
                print(f"[Voice] Commande de lecture pour la playlist '{original_playlist_name}' envoyée avec succès.")
            else:
                error_msg = play_response.get('message') if play_response else "Timeout ou erreur de communication."
                print(f"[Voice] Échec de l'envoi de la commande de lecture : {error_msg}")
                play_sound('not_understood')
        else:
            print(f"[Voice] Playlist '{recognized_text}' non trouvée (meilleur résultat '{best_match}' avec un score de {score} est trop bas).")
            play_sound('not_understood')

    except requests.RequestException as e:
        error_message = f"Erreur API Playlist: {e}"
        print(f"[Voice] {error_message}")
        update_status_file({"status": "error", "message": error_message})

def process_command(command_text, lang='fr'):
    """Interprète le texte de la commande et envoie l'action correspondante."""
    if not command_text:
        print("[Voice] Aucune commande audible n'a été comprise.")
        play_sound('not_understood')
        return

    print(f"[Voice] Commande reconnue ({lang}): '{command_text}'")
    
    lang_commands = COMMANDS.get(lang, COMMANDS['fr']) # Fallback sur le français

    # Commandes simples
    for phrase, (sound, action) in lang_commands['simple_commands'].items():
        if phrase in command_text:
            play_sound(sound)
            action()
            return

    # Commande pour changer la durée
    duration_match = re.search(lang_commands['duration_regex'], command_text)
    if duration_match:
        try:
            duration = int(duration_match.group(1))
            if 5 <= duration <= 120: # Limites raisonnables (5s à 2 minutes)
                play_sound('command_duration_set')
                send_simple_api_command("slideshow/set_duration", data={'duration': duration})
                return
            else:
                print(f"[Voice] Durée demandée ({duration}s) hors des limites (5-120s).") # Message en FR, ok pour les logs
                play_sound('not_understood')
                return
        except (ValueError, IndexError):
            pass # L'extraction a échoué, on continue pour voir si une autre commande correspond

    # Commandes complexes (avec arguments)
    match = re.search(lang_commands['playlist_regex'], command_text)
    if match:
        playlist_name = match.group(1).strip()
        if playlist_name:
            play_playlist_by_name(playlist_name, lang)
        else:
            play_sound('playlist_name_missing')
        return

    # Commande pour activer/désactiver une source
    if lang_commands['source_regex_trigger'] in command_text:
        parts = command_text.split(lang_commands['source_regex_trigger'])
        if len(parts) > 1: # Assure qu'il y a bien du texte avant et après le trigger
            action_phrase = parts[0].strip()
            source_name = parts[1].strip()
            
            # Trouver l'action (on/off)
            action = None
            for word, state in lang_commands['source_action_map'].items():
                if word in action_phrase:
                    action = state
                    break
            
            # Mapper les noms de source parlés aux noms techniques
            source_map = {
                "samba": "samba", "immich": "immich", "usb": "usb", "u s b": "usb",
                "telegram": "telegram", "smartphone": "smartphone"            }
            
            if action and source_name in source_map:
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
        lang = config.get('voice_control_language', 'fr')
        lang_commands = COMMANDS.get(lang, COMMANDS['fr'])
        
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
            'command_back_to_main': 'command_back_to_main.wav',
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
        
        # --- Sélection du modèle Porcupine basé sur la langue ---
        if lang == 'fr':
            keyword_filename = 'cadre-magique_raspberry-pi.ppn'
            porcupine_model_path = os.path.join(os.path.dirname(pvporcupine.__file__), 'lib/common/porcupine_params_fr.pv')
            if not os.path.exists(porcupine_model_path):
                raise FileNotFoundError(f"Modèle de langue FR Porcupine non trouvé: {porcupine_model_path}")
        else: # 'en' et autres langues par défaut
            keyword_filename = 'magic-frame_raspberry-pi_en.ppn' # Nom de fichier d'exemple
            porcupine_model_path = None # Utilise le modèle anglais par défaut

        keyword_path = str(BASE_DIR / "voice_models" / keyword_filename)
        if not os.path.exists(keyword_path):
            raise FileNotFoundError(f"Modèle de mot-clé '{keyword_path}' non trouvé. Veuillez l'entraîner sur la console Picovoice et le nommer correctement.")

        try:
            porcupine = pvporcupine.create(
                access_key=porcupine_access_key,
                keyword_paths=[keyword_path],
                model_path=porcupine_model_path
            )
        except pvporcupine.PorcupineInvalidArgumentError as e:
            raise ValueError(
                f"Le fichier de mot-clé '{keyword_filename}' est incorrect. "
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
        
        if lang == 'fr':
            vosk_model_path = str(BASE_DIR / "models" / "vosk-model-small-fr-0.22")
        else:
            vosk_model_path = str(BASE_DIR / "models" / "vosk-model-small-en-us-0.15")

        if not os.path.exists(vosk_model_path):
            raise FileNotFoundError(f"Modèle Vosk non trouvé : {vosk_model_path}. Veuillez lancer setup.sh.")
        
        print(f"[Voice] Chargement du modèle Vosk depuis : {vosk_model_path}")
        vosk_model = Model(vosk_model_path)
        # Initialiser Vosk avec la fréquence cible
        recognizer = KaldiRecognizer(vosk_model, TARGET_SAMPLERATE)

        # --- NOUVEAU: Définir une grammaire pour améliorer la précision ---
        playlist_names = get_playlist_names_for_grammar()
        
        # Construire le vocabulaire basé sur la langue
        if lang == 'fr':
            base_commands = [
                "photo", "suivante", "précédente", "pause", "lecture", "lance", "lancer", "la", "playlist",
                "éteindre", "le", "cadre", "passer", "en", "mode", "veille", "réveiller", "revenir", "au", "diaporama", "principal",
                "afficher", "les", "cartes", "postales", "reçues", "activer", "désactiver", "source", "samba", "immich",
                "usb", "u", "s", "b", "telegram", "smartphone",
                "durée", "pendant", "secondes", "cinq", "dix", "quinze", "vingt", "trente", "soixante", "[unk]"
            ]
        else: # English
            base_commands = [
                "photo", "next", "previous", "pause", "play", "playlist", "shut", "down", "the", "frame", "sleep", "mode", "return", "to", "main", "slideshow",
                "wake", "up", "show", "postcards", "enable", "disable", "activate", "deactivate", "source", "samba", "immich", 
                "usb", "telegram", "smartphone", "duration", "for", "seconds", "five", "ten", "fifteen", "twenty", "thirty", "sixty", "[unk]"
            ]

        for name in playlist_names:
            for word in name.split():
                if word.isdigit():
                    # Convertit "2025" en "deux mille vingt-cinq" et ajoute chaque mot
                    try:
                        num_in_words = num2words(int(word), lang=lang_commands['num2words_lang'])
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
        update_status_file({"status": "running", "message": lang_commands['wake_word_message']})

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
                        print(f"[Voice] Wake word detected!")
                        play_sound('listening')
                        listening_for_command = True
                        command_timeout = time.time() + 5  # 5 secondes pour donner une commande
                        audio_buffer = [] # Réinitialiser le buffer pour la nouvelle commande
                        update_status_file({"status": "listening", "message": lang_commands['listening_message']})
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
                        process_command(command_to_process, lang)
                        
                        # Et on sort du mode écoute
                        listening_for_command = False
                        update_status_file({"status": "running", "message": lang_commands['wake_word_message']})

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