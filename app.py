from flask import Flask, render_template, request, redirect, url_for, session
import os
from utils.config import load_config, save_config
from utils.slideshow import start_slideshow
from utils.download_album import download_and_extract_album
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Utilisé pour la session Flask
CONFIG_PATH = '/boot/firmware/credentials.json'

@app.route('/')
def index():
    config = load_config(CONFIG_PATH)
    if not config:
        return redirect(url_for('welcome'))
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    return redirect(url_for('slideshow'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    config = load_config(CONFIG_PATH)
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if config and username == config.get('username') and password == config.get('password'):
            session['authenticated'] = True
            return redirect(url_for('configure'))
        return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('login'))

@app.route('/configure', methods=['GET', 'POST'])
def configure():
    if not session.get('authenticated'):
        return redirect(url_for('login'))

    config = load_config(CONFIG_PATH) or {}
    if request.method == 'POST':
        updated_config = request.form.to_dict()
        updated_config['album_ids'] = request.form.getlist('album_ids')
        updated_config['pan_zoom'] = 'pan_zoom' in request.form
        save_config(CONFIG_PATH, updated_config)
        return redirect(url_for('slideshow'))

    return render_template('configure.html', config=config)

@app.route('/slideshow')
def slideshow():
    if not session.get('authenticated'):
        return redirect(url_for('login'))

    config = load_config(CONFIG_PATH)
    if not config:
        return redirect(url_for('configure'))

    current_hour = datetime.now().hour
    if not (int(config.get('start_hour', 0)) <= current_hour <= int(config.get('end_hour', 23))):
        return "Slideshow inactive at this hour"

    # Téléchargement et extraction Immich si besoin
    if config.get('source') == 'immich':
        download_and_extract_album(config)

    start_slideshow(config)
    return "Slideshow started (check your screen)."

@app.route('/welcome')
def welcome():
    return render_template('welcome.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
