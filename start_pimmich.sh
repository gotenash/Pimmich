#!/bin/bash

echo "Lancement du superviseur Pimmich..."

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
  echo "[start_pimmich.sh] Warning : aucun socket sway ipc trouvé. Sway est-il lancé ?"
else
  export SWAYSOCK="$SOCK"
  echo "[start_pimmich.sh] Socket sway détecté et exporté : $SOCK"
fi

# --- Pause de stabilisation ---
# Au redémarrage (reboot), les services peuvent se lancer en parallèle.
# Une petite pause ici permet de s'assurer que tout est stable (notamment le réseau) avant de lancer l'application.
echo "[start_pimmich.sh] Pause de 5 secondes pour la stabilisation du système..."
sleep 10

# Aller dans le dossier du projet
cd "$(dirname "$0")" || exit 1

# Activer l'environnement virtuel Python
source venv/bin/activate

while true; do
    echo "[start_pimmich.sh] Lancement de l'application Pimmich (app.py)..."
    # Lancer en avant-plan. Si le script python s'arrête, la boucle le relancera.
    python3 app.py >> logs/log_app.txt 2>&1
    echo "[start_pimmich.sh] L'application s'est arrêtée. Redémarrage dans 5 secondes..."
    sleep 5
done
