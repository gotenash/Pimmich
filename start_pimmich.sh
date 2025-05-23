#!/bin/bash

# Aller dans le dossier du projet
cd /home/pi/pimmich || exit 1

# Activer l'environnement virtuel Python
source venv/bin/activate

# Lancer le backend Flask et le diaporama en arrière-plan, avec redirection vers des fichiers log
echo "=== Lancement de app.py ==="
python3 app.py > /home/pi/pimmich/logs/log_app.txt 2>&1 &

sleep 2

echo "=== Lancement du diaporama ==="
python3 local_slideshow.py > /home/pi/pimmich/logs/log_slide.txt 2>&1 &
