#!/bin/bash

set -e

echo "== 📦 Mise à jour du système =="
sudo apt update && sudo apt upgrade -y

echo "== 🧰 Installation des dépendances =="
sudo apt install -y \
  python3 python3-venv python3-pip \
  git sway grim slurp jq libjpeg-dev libatlas-base-dev \
  fonts-dejavu-core fonts-freefont-ttf

echo "== 🌱 Création de l’environnement Python virtuel =="
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "== 🖥️ Activation automatique de Sway au démarrage =="
BASH_PROFILE="$HOME/.bash_profile"
if ! grep -q "exec sway" "$BASH_PROFILE" 2>/dev/null; then
  echo "" >> "$BASH_PROFILE"
  echo "if [[ -z \$DISPLAY ]] && [[ \$(tty) = /dev/tty1 ]]; then" >> "$BASH_PROFILE"
  echo "  exec sway" >> "$BASH_PROFILE"
  echo "fi" >> "$BASH_PROFILE"
  echo "✅ Ajout de sway au .bash_profile"
else
  echo "ℹ️ Sway est déjà configuré pour démarrer automatiquement"
fi

echo "== ✅ Setup terminé =="
echo "➡️ Redémarre ton Raspberry Pi pour lancer Sway automatiquement"
