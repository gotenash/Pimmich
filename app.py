from flask import Flask, render_template, request, redirect, url_for, session, flash, stream_with_context, Response, jsonify
import os
import json
import re
import subprocess
import psutil
import time
import requests
from pathlib import Path

# Modules internes
from utils.download_album import download_and_extract_album
from utils.auth import login_required
from utils.slideshow_manager import is_slideshow_running, start_slideshow, stop_slideshow
from utils.prepare_all_photos import prepare_all_photos_with_progress
from utils.import_usb_photos import import_usb_photos  # Déplacé dans utils

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Chemins de config
CONFIG_PATH = 'config/config.json'
CREDENTIALS_PATH = '/boot/firmware/credentials.json'


# --- Fonctions utilitaires ---

def check_and_start_slideshow_on_boot():
    from datetime import datetime

    print("== Verification du créneau horaire au demarrage ==")

    config = load_config()
    try:
        # Extraire l'heure entière depuis "HH:MM"
        start_str = config.get("active_start", "0:00")
        end_str = config.get("active_end", "24:00")
        start = int(start_str.split(":")[0])
        end = int(end_str.split(":")[0])
    except (ValueError, AttributeError, IndexError) as e:
        print(f"Erreur de parsing des horaires : {e}")
        return

    now = datetime.now().hour
    print(f"Heure actuelle : {now} / CrÃ©neau actif : {start}-{end}")

    if start <= now < end:
        print("Dans la plage horaire, on dÃ©marre le slideshow.")
        if not is_slideshow_running():
            start_slideshow()
    else:
        print("Hors plage horaire, on ne dÃ©marre pas le slideshow.")



def get_photo_previews():
    photo_dir = Path("static/photos")
    return sorted([f.name for f in photo_dir.glob("*") if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".gif"]])

def load_credentials():
    try:
        with open(CREDENTIALS_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def check_credentials(username, password):
    credentials = load_credentials()
    return username == credentials.get("username") and password == credentials.get("password")

def load_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_config(config):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)

def get_prepared_photos():
    folder = Path("static/prepared")
    return sorted([f.name for f in folder.glob("*") if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".gif"]])




# --- Routes principales ---

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if check_credentials(request.form['username'], request.form['password']):
            session['logged_in'] = True
            flash("Connexion rÃ©ussie", "success")
            return redirect(url_for('configure'))
        else:
            flash("Identifiants invalides", "danger")
    return render_template('login.html')

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('logged_in', None)
    flash("DÃ©connexion rÃ©ussie", "success")
    return redirect(url_for('login'))


# --- Configuration & gestion diaporama ---

@app.route('/configure', methods=['GET', 'POST'])
def configure():
    config = load_config()

    if request.method == 'POST':
        for key in [
            'immich_url', 'immich_token', 'album_name', 'album_title',
            'display_duration', 'active_start', 'active_end', 'source',
            'screen_height_percent', 'clock_font_size', 'clock_position',
            'clock_color', 'clock_format', 'clock_offset_x',
            'clock_offset_y', 'clock_outline_color', 'clock_font_path'
        ]:
            if key in request.form:
                value = request.form.get(key)
                if key == 'display_duration' or key in ['clock_offset_x', 'clock_offset_y', 'clock_font_size']:
                    config[key] = int(value)
                else:
                    config[key] = value

        #  Traitement spÃ©cial pour la checkbox
        config["show_clock"] = 'show_clock' in request.form

        save_config(config)
        stop_slideshow()
        start_slideshow()
        flash("Configuration enregistrÃ©e et diaporama relancÃ©", "success")
        return redirect(url_for('configure'))

    slideshow_running = any(
        'local_slideshow.py' in (p.info['cmdline'] or []) for p in psutil.process_iter(attrs=['cmdline'])
    )
    prepared_photos = get_prepared_photos()

    return render_template(
        'configure.html',
        config=config,
        photos=prepared_photos,
        slideshow_running=slideshow_running
    )

@app.route("/import-usb")
@login_required
def progress():
    @stream_with_context
    def generate():
        try:
            yield "data: 0% [RECHERCHE] Recherche de la clé USB...\n\n"
            time.sleep(0.5)
            
            total_photos = 0
            imported_count = 0
            
            # Étape 1 : import USB avec comptage
            for message in import_usb_photos():
                message = message.strip()
                
                # Détecter les messages de comptage
                if "photos importées" in message and "INFO" in message:
                    # Extraire le nombre de photos
                    match = re.search(r'(\d+) photos importées', message)
                    if match:
                        total_photos = int(match.group(1))
                
                # Formater les messages avec des indicateurs texte
                if "Clé USB détectée" in message:
                    yield f"data: 10% [DETECTE] {message}\n\n"
                elif "Import en cours" in message:
                    # Extraire le pourcentage si présent
                    match = re.search(r'(\d+)%', message)
                    if match:
                        percent = min(int(match.group(1)), 75)  # Limiter à 75% pour l'import
                        yield f"data: {percent}% [COPIE] Copie des photos en cours... {message.split('(')[-1] if '(' in message else ''}\n\n"
                    else:
                        yield f"data: 50% [COPIE] {message}\n\n"
                elif "STATS" in message and "images trouvées" in message:
                    # Extraire le nombre d'images
                    match = re.search(r'(\d+) images trouvées', message)
                    if match:
                        total_photos = int(match.group(1))
                        yield f"data: 20% [STATS] {total_photos} photos trouvées, import en cours...\n\n"
                elif "Erreur" in message or "ERREUR" in message:
                    yield f"data: [ERREUR] {message}\n\n"
                    return
                elif "ALERTE" in message:
                    yield f"data: [ALERTE] {message}\n\n"
                elif message.strip():  # Éviter les messages vides
                    yield f"data: {message}\n\n"

            if total_photos > 0:
                yield f"data: 80% [SUCCES] {total_photos} photos importées avec succès\n\n"
                yield "data: 85% [PREPARATION] Préparation des photos pour l'affichage...\n\n"
                
                # Étape 2 : préparation avec feedback amélioré
                prepare_count = 0
                for message in prepare_all_photos_with_progress():
                    if "Préparé" in message or "SUCCES" in message:
                        prepare_count += 1
                        progress = 85 + int((prepare_count / total_photos) * 15)
                        yield f"data: {progress}% [PHOTO] Préparation: {prepare_count}/{total_photos} photos\n\n"
                    elif "Erreur" in message or "ERREUR" in message:
                        yield f"data: [ALERTE] {message}\n\n"
                
                yield "data: 100% [TERMINE] Import terminé ! Toutes les photos sont prêtes pour le diaporama.\n\n"
            else:
                yield "data: [ERREUR] Aucune photo trouvée ou importée\n\n"

        except Exception as e:
            yield f"data: [ERREUR] Erreur critique : {str(e)}\n\n"

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive"
    })


@app.route("/import-immich")
@login_required
def import_immich():
    config = load_config()
    
    def generate():
        try:
            yield "data: 0% [CONNEXION] Connexion au serveur Immich...\n\n"
            time.sleep(0.5)
            
            nb_photos = 0
            messages_buffer = []

            def enhanced_status_callback(message):
                messages_buffer.append(message)

            # 1) Téléchargement + extraction avec feedback amélioré
            try:
                nb_photos = download_and_extract_album(config, status_callback=enhanced_status_callback)
                
                # Traiter les messages du buffer
                for msg in messages_buffer:
                    if "Connexion à Immich" in msg:
                        yield "data: 5% [ETABLI] Connexion établie avec Immich\n\n"
                    elif "Récupération de la liste" in msg:
                        yield "data: 15% [ANALYSE] Analyse de l'album en cours...\n\n"
                    elif "Téléchargement de l'archive" in msg:
                        if nb_photos > 0:
                            yield f"data: 25% [DOWNLOAD] Téléchargement de {nb_photos} photos...\n\n"
                        else:
                            yield "data: 25% [DOWNLOAD] Téléchargement de l'archive...\n\n"
                    elif "Extraction des photos" in msg:
                        yield "data: 60% [EXTRACTION] Extraction de l'archive en cours...\n\n"
                    elif "%" in msg:
                        yield f"data: {msg}\n\n"
                
                messages_buffer.clear()
                
                yield f"data: 80% [SUCCES] {nb_photos} photos téléchargées depuis Immich\n\n"
                
            except Exception as e:
                yield f"data: [ERREUR] Erreur lors du téléchargement : {str(e)}\n\n"
                return

            # 2) Préparation des photos
            if nb_photos > 0:
                yield "data: 85% [PREPARATION] Préparation des photos pour l'affichage...\n\n"
                
                prepare_count = 0
                for message in prepare_all_photos_with_progress():
                    if "Préparé" in message or "SUCCES" in message:
                        prepare_count += 1
                        progress = 85 + int((prepare_count / nb_photos) * 15)
                        yield f"data: {progress}% [PHOTO] Préparation: {prepare_count}/{nb_photos} photos\n\n"
                    elif "Erreur" in message or "ERREUR" in message:
                        yield f"data: [ALERTE] {message}\n\n"

                yield "data: 100% [TERMINE] Import Immich terminé ! Toutes les photos sont prêtes.\n\n"
            else:
                yield "data: [ERREUR] Aucune photo récupérée depuis Immich\n\n"

        except Exception as e:
            yield f"data: [ERREUR] Erreur critique : {str(e)}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive"
    })



# --- Téléchargement Immich et Préparation photos ---


@app.route("/download", methods=["POST"])
@login_required
def download_photos():
    try:
        config = load_config()
        download_and_extract_album(config)
        flash("Photos tÃ©lÃ©chargÃ©es avec succÃ¨s", "success")
    except Exception as e:
        flash(f"Erreur tÃ©lÃ©chargement : {e}", "danger")
    return redirect(url_for("configure"))


# --- Import depuis Clé USB ---

@app.route("/import_usb_progress")
@login_required
def import_usb_progress():
    @stream_with_context
    def generate():
        try:
            yield "Import depuis la clÃ© USB...\n"
            import_usb_photos()
            yield "PrÃ©paration des photos...\n"
            prepare_all_photos()
            yield "TerminÃ©. (100%)\n"
        except Exception as e:
            yield f"Erreur : {str(e)}\n"
    return Response(generate(), mimetype="text/plain")


# --- Gestion Diaporama ---

@app.route("/slideshow")
@login_required
def slideshow():
    return render_template("slideshow.html")

@app.route('/slideshow_view')
def slideshow_view():
    photos = get_prepared_photos()
    return render_template('slideshow_view.html', photos=photos)

@app.route('/toggle_slideshow', methods=['POST'])
@login_required
def toggle_slideshow():
    config = load_config()

    # On lit l'état actuel du slideshow
    running = is_slideshow_running()

    # Si le slideshow est lancÃ©, on l'arrète, sinon on le dÃ©marre
    if running:
        stop_slideshow()
        config['manual_override'] = True  # Forcer l'arrêt manuel
    else:
        start_slideshow()
        config['manual_override'] = True  # Forcer le demarrage manuel

    save_config(config)

    return redirect(url_for('configure'))
    
# --- Suppression photo ---
@app.route('/delete_photo/<photo>', methods=['DELETE'])
@login_required
def delete_photo(photo):
    try:
        photo_path = os.path.join('static', 'prepared', photo)
        if os.path.isfile(photo_path):
            os.remove(photo_path)
            return '', 204
        return 'Not found', 404
    except Exception as e:
        return str(e), 500
# --- Contrôle système ---

@app.route('/shutdown', methods=['POST'])
@login_required
def shutdown():
    os.system('sudo shutdown now')
    return redirect(url_for('configure'))

@app.route('/reboot', methods=['POST'])
@login_required
def reboot():
    os.system('sudo reboot')
    return redirect(url_for('configure'))


# --- Lancement de l'application ---
if __name__ == '__main__':
    check_and_start_slideshow_on_boot()
    app.run(host='0.0.0.0', port=5000)
