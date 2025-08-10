#!/bin/bash

# === [1/12] Mise à jour des paquets ===
# ⚠️ Étape facultative. Si nécessaire, faire manuellement :
# sudo apt update && sudo apt upgrade -y
# echo "Mise à jour sautée pour une installation plus rapide."


echo "=== [2/12] Installation des dépendances ==="
sudo apt install -y sway xterm python3 python3-venv python3-pip libjpeg-dev libopenjp2-7-dev libtiff-dev libatlas-base-dev ffmpeg git cifs-utils smbclient network-manager jq mpv gettext

echo "=== [3/12] Désactivation de l'économie d'énergie Wi-Fi ==="
# Installation conditionnelle de RPi.GPIO (pour le ventilateur)
if [ -f "/etc/os-release" ]; then
    source /etc/os-release
    if [[ "$ID" == "raspbian" || "$ID" == "debian" ]]; then
        echo "Détection de Raspberry Pi OS (ou Debian). Installation de RPi.GPIO..."
        sudo apt-get install -y python3-rpi.gpio
    fi
fi

CONF_FILE="/etc/NetworkManager/conf.d/99-disable-wifi-powersave.conf"
if [ ! -f "$CONF_FILE" ]; then
    echo "Création du fichier de configuration pour désactiver l'économie d'énergie Wi-Fi..."
    sudo tee "$CONF_FILE" > /dev/null <<'EOL'
[connection]
wifi.powersave = 2
EOL
    echo "✅ Économie d'énergie Wi-Fi désactivée. Redémarrage de NetworkManager..."
    sudo systemctl restart NetworkManager
    sleep 2 # Petite pause pour laisser le service redémarrer
else
    echo "✅ L'économie d'énergie Wi-Fi est déjà désactivée."
fi

echo "=== [4/12] Configuration automatique du fuseau horaire ==="
DETECTED_TIMEZONE="UTC" # Valeur par défaut
TIMEZONE_SOURCE="fallback" # Source par défaut

echo "Tentative de détection du fuseau horaire via l'adresse IP publique..."
# Utilise l'API ip-api.com et l'outil jq pour extraire le fuseau horaire
TIMEZONE_FROM_API=$(curl -s http://ip-api.com/json | jq -r '.timezone')

# Vérifie si la détection a réussi
if [ -n "$TIMEZONE_FROM_API" ] && [ "$TIMEZONE_FROM_API" != "null" ]; then
    echo "Fuseau horaire détecté : $TIMEZONE_FROM_API"
    sudo timedatectl set-timezone "$TIMEZONE_FROM_API"
    DETECTED_TIMEZONE="$TIMEZONE_FROM_API"
    TIMEZONE_SOURCE="auto"
    echo "✅ Fuseau horaire configuré automatiquement. Heure actuelle : $(date)"
else
    echo "⚠️ La détection automatique a échoué. Le fuseau horaire sera réglé sur UTC par défaut."
    sudo timedatectl set-timezone UTC
    echo "Vous pourrez le changer manuellement plus tard avec : sudo timedatectl set-timezone Votre/Ville"
fi

echo "=== [5/12] Installation et configuration de NGINX pour redirection sans :5000 ==="

# Vérifier si nginx est installé
if ! command -v nginx &> /dev/null; then
    echo "📦 NGINX non détecté, tentative d'installation..."

    # Vérifie que la liste des paquets est à jour
    echo "🔄 Mise à jour de la liste des paquets..."
    sudo apt-get update --fix-missing

    # Installer NGINX
    if ! sudo apt-get install -y nginx; then
        echo "❌ Échec de l'installation de NGINX. Vérifie ta connexion Internet ou tes dépôts apt."
        exit 1
    fi
else
    echo "✅ NGINX est déjà installé"
fi

# Vérifie l'existence du dossier /etc/nginx
if [ ! -d /etc/nginx ]; then
    echo "❌ Le dossier /etc/nginx est introuvable. L'installation de NGINX semble incomplète."
    exit 1
fi

# Supprimer la config par défaut si elle existe
if [ -f /etc/nginx/sites-enabled/default ]; then
    sudo rm /etc/nginx/sites-enabled/default
    echo "⛔ Fichier de config par défaut supprimé"
fi

# Créer une nouvelle config pour Pimmich
sudo mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
sudo tee /etc/nginx/sites-available/pimmich > /dev/null <<'EOL'
server {
    listen 80;
    server_name _;

    client_max_body_size 200M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
    }
}
EOL

# Activer la nouvelle config
if [ ! -f /etc/nginx/sites-enabled/pimmich ]; then
    sudo ln -s /etc/nginx/sites-available/pimmich /etc/nginx/sites-enabled/
    echo "✅ Configuration Pimmich activée dans NGINX"
fi

# Redémarrer NGINX
if sudo systemctl restart nginx; then
    echo "✅ NGINX redémarré et prêt"
else
    echo "❌ Impossible de redémarrer NGINX. Vérifie la configuration avec : sudo nginx -t"
    exit 1
fi

echo "=== [6/12] Création de l’environnement Python ==="
cd "$(dirname "$0")"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
echo "Installation de la bibliothèque pour les QR codes..."
pip install "qrcode[pil]"
echo "Mise à jour de la bibliothèque pour le bot Telegram..."
pip install --upgrade python-telegram-bot

echo "=== [7/12] Création de l'arborescence des dossiers nécessaires ==="
mkdir -p logs
mkdir -p cache
mkdir -p static/photos
mkdir -p static/prepared
mkdir -p static/pending_uploads
echo "✅ Arborescence des dossiers créée."

# Corriger les permissions même si script lancé avec sudo
REAL_USER=$(logname)
sudo chown -R "$REAL_USER:$REAL_USER" static logs cache
chmod -R u+rwX static logs cache

echo "=== [8/12] Création du fichier d'identification sécurisé ==="
CREDENTIALS_FILE="/boot/firmware/credentials.json"

if [ ! -f "$CREDENTIALS_FILE" ]; then
    echo "Génération d'un mot de passe aléatoire et création du fichier d'identification..."
    # On utilise sudo pour exécuter le script python qui a besoin des droits pour écrire dans /boot/firmware
    # Le script python est exécuté via l'interpréteur de l'environnement virtuel pour avoir accès à werkzeug.
    # Le script affichera lui-même le mot de passe généré.
    sudo venv/bin/python3 utils/create_initial_user.py --output "$CREDENTIALS_FILE"
else
    echo "✅ Le fichier d'identification $CREDENTIALS_FILE existe déjà. Aucune modification."
fi

echo "=== [9/12] Configuration du démarrage en mode console (CLI) ==="
sudo raspi-config nonint do_boot_behaviour B2
echo "✅ Système configuré pour démarrer en mode console avec auto-login."


echo "=== [10/12] Configuration du lancement automatique de Sway ==="
BASH_PROFILE="/home/pi/.bash_profile"
if ! grep -q 'exec sway' "$BASH_PROFILE"; then
    echo 'if [[ -z $DISPLAY ]] && [[ $(tty) = /dev/tty1 ]]; then' >> "$BASH_PROFILE"
    echo '  exec sway' >> "$BASH_PROFILE"
    echo 'fi' >> "$BASH_PROFILE"
    echo "Ajout du démarrage automatique de Sway dans $BASH_PROFILE"
else
    echo "✅ Sway déjà configuré pour se lancer automatiquement"
fi

echo "=== [11/12] Configuration du lancement automatique de Pimmich dans Sway ==="
SWAY_CONFIG_DIR="/home/pi/.config/sway"
SWAY_CONFIG_FILE="$SWAY_CONFIG_DIR/config"
mkdir -p "$SWAY_CONFIG_DIR"

# Rendre exécutable
chmod +x /home/pi/pimmich/start_pimmich.sh

# Ajout de l'exec_always si absent
if ! grep -q 'start_pimmich.sh' "$SWAY_CONFIG_FILE" 2>/dev/null; then
    echo 'exec_always --no-startup-id /home/pi/pimmich/start_pimmich.sh' >> "$SWAY_CONFIG_FILE"
    echo "Ajout de start_pimmich.sh dans la config sway"
else
    echo "✅ start_pimmich.sh déjà présent dans la config sway"
fi

echo "=== [12/12] Installation terminée ==="
echo "✅ Installation terminée. Redémarrez pour lancer automatiquement Sway + Pimmich."
