#!/bin/bash

# Ce script est le point d'entrée principal de Pimmich, géré par Sway.
# Il assure qu'une seule instance de l'application est en cours et gère les redémarrages.

# Code de sortie spécial pour demander un redémarrage
RESTART_CODE=42

# Se placer dans le répertoire du script pour que les chemins relatifs fonctionnent
cd "$(dirname "$0")" || exit 1

cleanup() {
    echo "[start_pimmich] Nettoyage des processus Pimmich existants..."
    # Tuer le processus de contrôle vocal s'il est en cours
    if [ -f /tmp/pimmich_voice_control.pid ]; then
        pkill -F /tmp/pimmich_voice_control.pid || true
        rm -f /tmp/pimmich_voice_control.pid
    fi
    # Tuer le processus du diaporama s'il est en cours
    if [ -f /tmp/pimmich_slideshow.pid ]; then
        pkill -F /tmp/pimmich_slideshow.pid || true
        rm -f /tmp/pimmich_slideshow.pid
    fi
    # Tuer toute instance précédente de l'application Flask (app.py)
    # Utilise pgrep pour trouver le PID et le tuer, plus sûr que pkill -f
    PID_TO_KILL=$(pgrep -f "python3 app.py")
    if [ -n "$PID_TO_KILL" ]; then
        echo "[start_pimmich] Ancien processus app.py trouvé (PID: $PID_TO_KILL). Arrêt..."
        kill "$PID_TO_KILL"
    fi
    sleep 1 # Laisser le temps aux processus de se terminer
}

while true; do
    # Nettoyer avant chaque lancement
    cleanup

    echo "[start_pimmich] Lancement de l'application Pimmich..."
    # Activer l'environnement virtuel et lancer l'application
    # Rediriger la sortie vers le fichier de log, en l'écrasant à chaque nouveau démarrage
    # pour éviter qu'il ne grossisse indéfiniment.
    source venv/bin/activate
    python3 -u app.py > logs/log_app.txt 2>&1

    exit_code=$?
    echo "[start_pimmich] L'application s'est terminée avec le code de sortie : $exit_code" >> logs/log_app.txt

    if [ $exit_code -ne $RESTART_CODE ]; then
        echo "[start_pimmich] Code de sortie non-redémarrage. Arrêt du script." >> logs/log_app.txt
        break # Sortir de la boucle si ce n'est pas un redémarrage demandé
    fi

    echo "[start_pimmich] Redémarrage demandé. Relance de l'application dans 2 secondes..." >> logs/log_app.txt
    sleep 2
done
