from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
import json
import subprocess
import psutil
from utils.download_album import download_and_extract_album
from utils.auth import login_required  # ton décorateur maison
from utils.slideshow_manager import is_slideshow_running, start_slideshow, stop_slideshow

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Ne pas changer à chaque redémarrage

# Chemins
CONFIG_PATH = 'config/config.json'
CREDENTIALS_PATH = '/boot/firmware/credentials.json'


# --- Fonctions utilitaires ---

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


# --- Routes ---

@app.route('/')
def home():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if check_credentials(username, password):
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
    
@app.route('/configure', methods=['GET', 'POST'])
@login_required
def configure():
    config = load_config()


    if request.method == 'POST':
        config['immich_url'] = request.form.get('immich_url', '')
        config['immich_token'] = request.form.get('immich_token', '')
        config['album_name'] = request.form.get('album_name', '')
        config['album_title'] = request.form.get('album_title', '')
        config['display_duration'] = int(request.form.get('display_duration', 10))
        config['active_start'] = request.form.get('active_start', '')
        config['active_end'] = request.form.get('active_end', '')
        config['source'] = request.form.get('source', 'immich')

        save_config(config)

        # Redémarrer le diaporama pour appliquer les nouveaux paramètres
        os.system("pkill -f local_slideshow.py")
        subprocess.Popen(["python3", "local_slideshow.py"])

        flash("Configuration enregistrée et diaporama relancé", "success")
        return redirect(url_for('configure'))

    # Vérifie si le diaporama est en cours d'exécution
    slideshow_running = any(
        'local_slideshow.py' in (p.info['cmdline'] or [])
        for p in psutil.process_iter(attrs=['cmdline'])
    )

    return render_template(
        'configure.html',
        config=config,
        slideshow_running=slideshow_running
    )



@app.route('/toggle_slideshow', methods=['POST'])
@login_required
def toggle_slideshow():
    if is_slideshow_running():
        stop_slideshow()
    else:
        start_slideshow()
    return redirect(url_for('configure'))


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





# --- Lancement de l'app ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
