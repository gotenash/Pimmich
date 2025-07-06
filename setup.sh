#!/bin/bash

# === [1/10] Mise à jour des paquets ===
# ⚠️ Étape facultative. Si nécessaire, faire manuellement :
# sudo apt update && sudo apt upgrade -y
# echo "Mise à jour sautée pour une installation plus rapide."

echo "=== [2/10] Installation des dépendances ==="
sudo apt install -y sway xterm python3 python3-venv python3-pip libjpeg-dev libopenjp2-7-dev libtiff-dev libatlas-base-dev ffmpeg git cifs-utils smbclient

echo "=== [3/10] Installation et configuration de NGINX pour redirection sans :5000 ==="
# Installer NGINX si ce n'est pas déjà fait
if ! command -v nginx &> /dev/null; then
    echo "Installation de NGINX..."
    sudo apt install -y nginx
else
    echo "✅ NGINX est déjà installé"
fi

# Supprimer la config par défaut si elle existe
if [ -f /etc/nginx/sites-enabled/default ]; then
    sudo rm /etc/nginx/sites-enabled/default
    echo "⛔ Fichier de config par défaut supprimé"
fi

# Créer une nouvelle config pour Pimmich
sudo tee /etc/nginx/sites-available/pimmich > /dev/null <<'EOL'
server {
    listen 80;
    server_name _;

    client_max_body_size 200M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOL

# Activer la nouvelle config
if [ ! -f /etc/nginx/sites-enabled/pimmich ]; then
    sudo ln -s /etc/nginx/sites-available/pimmich /etc/nginx/sites-enabled/
    echo "✅ Configuration Pimmich activée dans NGINX"
fi

# Redémarrer NGINX
sudo systemctl restart nginx
echo "✅ NGINX redémarré et prêt"

echo "=== [4/10] Création de l’environnement Python ==="
cd "$(dirname "$0")"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "=== [5/10] Création de l'arborescence des dossiers nécessaires ==="
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

echo "=== [6/10] Création du fichier de configuration par défaut ==="
CONFIG_DIR="config"
CONFIG_FILE="$CONFIG_DIR/config.json"
mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Création du fichier de configuration initial : $CONFIG_FILE"
    cat > "$CONFIG_FILE" << EOL
{
  "photo_source": "immich",
  "display_duration": 10,
  "active_start": "07:00",
  "active_end": "22:00",
  "screen_height_percent": "100",
  "immich_url": "",
  "immich_token": "",
  "album_name": "",
  "immich_auto_update": false,
  "immich_update_interval_hours": 24,
  "smb_host": "",
  "smb_share": "",
  "smb_user": "",
  "smb_password": "",
  "smb_path": "/",
  "smb_auto_update": false,
  "smb_update_interval_hours": 24,
  "show_clock": true,
  "clock_format": "%H:%M",
  "clock_color": "#FFFFFF",
  "clock_outline_color": "#000000",
  "clock_font_size": 72,
  "clock_font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
  "clock_offset_x": 0,
  "clock_offset_y": 0
}
EOL
else
    echo "✅ Le fichier de configuration existe déjà."
fi

echo "=== [7/10] Création du fichier d'identification par défaut ==="
CREDENTIALS_FILE="/boot/firmware/credentials.json"

if [ ! -f "$CREDENTIALS_FILE" ]; then
    echo "Création du fichier d'identification par défaut : $CREDENTIALS_FILE"
    echo "Utilisateur : admin / Mot de passe : pimmich"
    # Utilisation de sudo avec bash -c pour gérer la redirection de droits
    sudo bash -c "cat > '$CREDENTIALS_FILE'" << EOL
{
  "username": "admin",
  "password": "pimmich"
}
EOL
    echo "✅ Fichier credentials.json créé. Pensez à le modifier pour plus de sécurité."
else
    echo "✅ Le fichier d'identification $CREDENTIALS_FILE existe déjà. Aucune modification."
fi


echo "=== [8/10] Configuration du lancement automatique de Sway ==="
BASH_PROFILE="/home/pi/.bash_profile"
if ! grep -q 'exec sway' "$BASH_PROFILE"; then
    echo 'if [[ -z $DISPLAY ]] && [[ $(tty) = /dev/tty1 ]]; then' >> "$BASH_PROFILE"
    echo '  exec sway' >> "$BASH_PROFILE"
    echo 'fi' >> "$BASH_PROFILE"
    echo "Ajout du démarrage automatique de Sway dans $BASH_PROFILE"
else
    echo "✅ Sway déjà configuré pour se lancer automatiquement"
fi

echo "=== [9/10] Configuration du lancement automatique de Pimmich dans Sway ==="
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

echo "=== [10/10] Installation terminée ==="
echo "✅ Installation terminée. Redémarrez pour lancer automatiquement Sway + Pimmich."
