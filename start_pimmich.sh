#!/bin/bash

echo "Lancement du diaporama Pimmich..."

# Détecter et exporter automatiquement le socket Sway IPC
USER_ID=$(id -u)
# Attendre que sway soit prêt (max 15 secondes)
for i in {1..15}; do
  SOCK=$(ls /run/user/$USER_ID/sway-ipc.* 2>/dev/null | head -n 1)
  if [ -n "$SOCK" ]; then
    break
  fi
  sleep 1
done

if [ -z "$SOCK" ]; then
  echo "Warning : aucun socket sway ipc trouvé. Sway est-il lancé ?"
else
  export SWAYSOCK="$SOCK"
  echo "Socket sway détecté et exporté : $SOCK"
fi

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
