#!/bin/bash

echo "=== Installation de Pimmich ==="

# Mises à jour et dépendances système
sudo apt update && sudo apt install -y python3-venv python3-pip python3-pil python3-tk unzip libjpeg-dev libatlas-base-dev libopenjp2-7 libtiff5 tk-dev python3-dev python3-setuptools python3-wheel

# Détection Desktop (X11) ou Lite
if [ -n "$DISPLAY" ] || [ -d /etc/xdg/autostart ]; then
    MODE="desktop"
    echo "Mode : Raspberry Pi OS Desktop détecté"
else
    MODE="lite"
    echo "Mode : Raspberry Pi OS Lite détecté"
fi

# Création du dossier projet
cd /home/pi || exit 1
mkdir -p pimmich/{config,logs,static/photos,templates}
cd pimmich || exit 1

# Création de l'environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installation des paquets Python
pip install --upgrade pip
pip install flask pillow requests pygame

# Création du service systemd (pour Lite)
if [ "$MODE" = "lite" ]; then
    echo "Création du service systemd pour démarrage automatique..."

    cat <<EOF | sudo tee /etc/systemd/system/pimmich.service > /dev/null
[Unit]
Description=Pimmich Slideshow and Flask App
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/pimmich
ExecStart=/home/pi/pimmich/start_pimmich.sh
Restart=always
Environment=DISPLAY=:0
StandardOutput=file:/home/pi/pimmich/logs/systemd_out.log
StandardError=file:/home/pi/pimmich/logs/systemd_err.log

[Install]
WantedBy=multi-user.target
EOF

    sudo chmod 644 /etc/systemd/system/pimmich.service
    sudo systemctl daemon-reexec
    sudo systemctl enable pimmich.service
    echo "Service systemd installé. Il démarrera automatiquement au prochain boot."

# Création de l’autostart (pour Desktop)
else
    echo "Création du fichier autostart pour interface graphique..."
    mkdir -p ~/.config/autostart
    cat <<EOF > ~/.config/autostart/pimmich.desktop
[Desktop Entry]
Type=Application
Name=Pimmich Diaporama
Exec=/home/pi/pimmich/start_pimmich.sh
X-GNOME-Autostart-enabled=true
EOF
fi

# Rendre le script de démarrage exécutable
chmod +x /home/pi/pimmich/start_pimmich.sh

echo "=== Installation terminée. Redémarre le Raspberry Pi pour tester le démarrage automatique ==="
