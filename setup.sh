#!/bin/bash

echo "=== [1/6] Mise à jour des paquets ==="
sudo apt update && sudo apt upgrade -y

echo "=== [2/6] Installation des dépendances ==="
sudo apt install -y sway xterm python3 python3-venv python3-pip libjpeg-dev libopenjp2-7-dev libtiff-dev libatlas-base-dev ffmpeg git

echo "=== [3/6] Création de l’environnement Python ==="
cd "$(dirname "$0")"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "=== [4/6] Configuration du lancement automatique de Sway ==="
BASH_PROFILE="/home/pi/.bash_profile"
if ! grep -q 'exec sway' "$BASH_PROFILE"; then
    echo 'if [[ -z $DISPLAY ]] && [[ $(tty) = /dev/tty1 ]]; then' >> "$BASH_PROFILE"
    echo '  exec sway' >> "$BASH_PROFILE"
    echo 'fi' >> "$BASH_PROFILE"
    echo "Ajout du démarrage automatique de Sway dans $BASH_PROFILE"
else
    echo "✅ Sway déjà configuré pour se lancer automatiquement"
fi

echo "=== [5/6] Configuration du lancement automatique de Pimmich dans Sway ==="
SWAY_CONFIG_DIR="/home/pi/.config/sway"
SWAY_CONFIG_FILE="$SWAY_CONFIG_DIR/config"
mkdir -p "$SWAY_CONFIG_DIR"

# Ajoute le lancement de start_pimmich.sh si pas déjà présent
if ! grep -q 'start_pimmich.sh' "$SWAY_CONFIG_FILE" 2>/dev/null; then
    echo 'exec xterm -e bash ~/pimmich/start_pimmich.sh' >> "$SWAY_CONFIG_FILE"
    echo "Ajout de start_pimmich.sh dans la config sway"
else
    echo "✅ start_pimmich.sh déjà présent dans la config sway"
fi

echo "✅ Installation terminée. Tu peux redémarrer le Raspberry Pi pour lancer automatiquement Pimmich."
