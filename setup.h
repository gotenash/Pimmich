#!/bin/bash

set -e  # Arrête le script en cas d'erreur

echo "=== Installation de Pimmich (auto-détection Lite/Desktop) ==="

# Met à jour les paquets et installe les dépendances
sudo apt update && sudo apt install -y python3-venv python3-pil python3-tk unzip git

# Crée le dossier du projet
cd /home/pi || exit 1
mkdir -p pimmich
cd pimmich || exit 1

# Clone le dépôt GitHub si vide
if [ -z "$(ls -A .)" ]; then
    echo "Clonage du dépôt GitHub..."
    git clone https://github.com/gotenash/pimmich.git .
fi

# Crée l'environnement virtuel Python
python3 -m venv venv
source venv/bin/activate

# Installe les dépendances Python
pip install flask pillow requests flask_cors

# Crée les dossiers nécessaires
mkdir -p config logs static/photos templates

# Rendez le script de démarrage exécutable
chmod +x /home/pi/pimmich/start_pimmich.sh

# Détection Desktop vs Lite
if [ -d /home/pi/.config/autostart ]; then
    echo "Mode Desktop détecté : création d’un raccourci autostart"

    mkdir -p /home/pi/.config/autostart

    cat > /home/pi/.config/autostart/pimmich.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Pimmich Diaporama
Exec=/home/pi/pimmich/start_pimmich.sh
X-GNOME-Autostart-enabled=true
EOF

else
    echo "Mode Lite détecté : création d’un service systemd"

    sudo tee /etc/systemd/system/pimmich.service > /dev/null <<EOF
[Unit]
Description=Pimmich Photo Frame
After=network.target

[Service]
ExecStart=/home/pi/pimmich/start_pimmich.sh
WorkingDirectory=/home/pi/pimmich
StandardOutput=file:/home/pi/pimmich/logs/pimmich.log
StandardError=file:/home/pi/pimmich/logs/pimmich_error.log
Restart=always
User=pi
Environment="PATH=/home/pi/pimmich/venv/bin"

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reexec
    sudo systemctl daemon-reload
    sudo systemctl enable pimmich.service
fi

echo "=== Installation terminée. Redémarre le Raspberry Pi avec 'sudo reboot' ==="
