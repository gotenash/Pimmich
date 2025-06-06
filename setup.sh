#!/bin/bash

set -e

echo "=== Mise à jour du système ==="
sudo apt update && sudo apt upgrade -y

echo "=== Installation des dépendances système ==="
sudo apt install -y python3 python3-pip python3-venv python3-pygame python3-pil python3-tk git

echo "=== Clonage ou mise à jour du projet Pimmich ==="
cd /home/pi
if [ ! -d "pimmich" ]; then
  git clone https://github.com/tonrepo/pimmich.git
else
  cd pimmich
  git pull
  cd ..
fi

echo "=== Création de l'environnement virtuel Python ==="
cd /home/pi/pimmich
python3 -m venv venv

echo "=== Activation et installation des paquets Python dans le venv ==="
source venv/bin/activate
pip install --upgrade pip
pip install flask pillow pygame requests psutil
deactivate

echo "=== Création du script de démarrage ==="
cat > /home/pi/pimmich/start_pimmich.sh << 'EOF'
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
EOF

chmod +x /home/pi/pimmich/start_pimmich.sh

echo "=== Création du fichier autostart ==="
mkdir -p /home/pi/.config/autostart

cat > /home/pi/.config/autostart/pimmich.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=Pimmich Diaporama
Exec=/home/pi/pimmich/start_pimmich.sh
X-GNOME-Autostart-enabled=true
EOF

echo "=== Installation terminée. Redémarre le Raspberry Pi pour tester. ==="
