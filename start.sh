#!/bin/bash

# Activer l'environnement virtuel
source venv/bin/activate

# Lancer le serveur Flask
export FLASK_APP=app.py
export FLASK_ENV=production
flask run --host=0.0.0.0 --port=5000
