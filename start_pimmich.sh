#!/bin/bash

echo "Lancement du diaporama Pimmich..."

# Aller dans le dossier du projet
cd /home/pi/pimmich || exit 1

# Activer l'environnement virtuel Python
source venv/bin/activate

# S'assurer que les dossiers de logs existent
mkdir -p logs

# Lancer Flask en arrière-plan
echo "=== Lancement de app.py ==="
python3 app.py > logs/log_app.txt 2>&1 &

# Petite pause pour s'assurer que Flask démarre
sleep 2

# Lancer le diaporama en arrière-plan
echo "=== Lancement du diaporama ==="
python3 local_slideshow.py > logs/log_slide.txt 2>&1 &
