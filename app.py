from flask import Flask, render_template, request, redirect, url_for, session, flash, stream_with_context, Response, jsonify
import os
import json
import subprocess
import psutil
import time
from pathlib import Path

# Modules internes
from utils.download_album import download_and_extract_album
from utils.auth import login_required
from utils.slideshow_manager import is_slideshow_running, start_slideshow, stop_slideshow
from utils.prepare_all_photos import prepare_all_photos
from utils.import_usb_photos import import_usb_photos  # Déplacé dans utils/

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Chemins de config
CONFIG_PATH = 'config/config.json'
CREDENTIALS_PATH = '/boot/firmware/credentials.json'


# --- Fonctions utilitaires ---

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
            flash("Connexion réussie", "success")
            return redirect(url_for('configure'))
        else:
            flash("Identifiants invalides", "danger")
    return render_template('login.html')

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('logged_in', None)
    flash("Déconnexion réussie", "success")
    return redirect(url_for('login'))


# --- Configuration & gestion diaporama ---

@app.route('/configure', methods=['GET', 'POST'])
@login_required
def configure():
    config = load_config()

    if request.method == 'POST':
        # On ne remet pas à zéro, on garde les champs existants
        for key in ['immich_url', 'immich_token', 'album_name', 'album_title', 'display_duration', 'active_start', 'active_end', 'source', 'screen_height_percent']:
            if key in request.form:
                value = request.form.get(key)
                config[key] = int(value) if key == 'display_duration' else value
        save_config(config)

        os.system("pkill -f local_slideshow.py")
        subprocess.Popen(["python3", "local_slideshow.py"])

        flash("Configuration enregistrée et diaporama relancé", "success")
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


# --- Téléchargement Immich et Préparation photos ---

@app.route("/progress")
@login_required
def progress():
    @stream_with_context
    def generate():
        try:
            yield "Démarrage de la récupération des photos...\n"
            config = load_config()

            if config.get("source", "immich") == "immich":
                yield "Téléchargement de l'album Immich...\n"
                download_and_extract_album(config)
            else:
                yield "Import depuis la clé USB...\n"
                import_usb_photos()

            yield "Préparation des photos...\n"
            prepare_all_photos()
            yield "Terminé. (100%)\n"
        except Exception as e:
            yield f"Erreur : {str(e)}\n"

    return Response(generate(), mimetype="text/plain")


@app.route("/download", methods=["POST"])
@login_required
def download_photos():
    try:
        config = load_config()
        download_and_extract_album(config)
        flash("Photos téléchargées avec succès", "success")
    except Exception as e:
        flash(f"Erreur téléchargement : {e}", "danger")
    return redirect(url_for("configure"))


# --- Import depuis Clé USB ---

@app.route("/import_usb_progress")
@login_required
def import_usb_progress():
    @stream_with_context
    def generate():
        try:
            yield "Import depuis la clé USB...\n"
            import_usb_photos()
            yield "Préparation des photos...\n"
            prepare_all_photos()
            yield "Terminé. (100%)\n"
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
    if is_slideshow_running():
        stop_slideshow()
    else:
        start_slideshow()
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
    app.run(host='0.0.0.0', port=5000)
