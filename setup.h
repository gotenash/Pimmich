#!/bin/bash

echo "🚀 Installation du projet Pimmich..."

# Mettre à jour les paquets
sudo apt update && sudo apt upgrade -y

# Installer les dépendances système
sudo apt install -y python3.9 python3.9-venv python3.9-dev python3-pip libjpeg-dev zlib1g-dev libopenjp2-7-dev libtiff5-dev libatlas-base-dev git unzip

# Créer l'environnement virtuel
python3.9 -m venv venv

# Activer l'environnement virtuel
source venv/bin/activate

# Installer les dépendances Python
pip install --upgrade pip
pip install -r requirements.txt

# Créer les répertoires nécessaires
mkdir -p static/uploads static/usb static/photos

# Copier un credentials.json de base si inexistant
CRED_PATH="/boot/firmware/credentials.json"
if [ ! -f "$CRED_PATH" ]; then
  echo "{
    \"source\": \"immich\",
    \"immich_url\": \"http://adresse-immich:2283\",
    \"immich_token\": \"votre_token\",
    \"album_ids\": [],
    \"start_hour\": 8,
    \"end_hour\": 22,
    \"pan_zoom\": true
  }" | sudo tee "$CRED_PATH" > /dev/null
  echo "✅ Fichier credentials.json créé dans /boot/firmware"
else
  echo "ℹ️ Fichier credentials.json déjà présent, inchangé"
fi

echo "✅ Installation terminée. Lance l'application avec :"
echo "   ./start.sh"
