#!/bin/bash

# Ce script est le point d'entrée principal de Pimmich, géré par Sway.
# Il assure qu'une seule instance de l'application est en cours et gère les redémarrages.

# Code de sortie spécial pour demander un redémarrage
RESTART_CODE=42

# Se placer dans le répertoire du script pour que les chemins relatifs fonctionnent
cd "$(dirname "$0")" || exit 1

# S'assurer que le dossier de logs existe
mkdir -p logs

cleanup() {
    echo "[start_pimmich] Nettoyage des processus Pimmich existants..." >> logs/pimmich.log
    # Tuer le processus de contrôle vocal s'il est en cours
    if [ -f /tmp/pimmich_voice_control.pid ]; then
        pkill -F /tmp/pimmich_voice_control.pid 2>/dev/null || true
        rm -f /tmp/pimmich_voice_control.pid
    fi
    # Tuer le processus du diaporama s'il est en cours
    if [ -f /tmp/pimmich_slideshow.pid ]; then
        pkill -F /tmp/pimmich_slideshow.pid 2>/dev/null || true
        rm -f /tmp/pimmich_slideshow.pid
    fi
    # Tuer toute instance précédente de l'application Flask (app.py)
    # Utilisation de pkill -f pour plus de robustesse
    pkill -f "python3 -u app.py" 2>/dev/null || true
    pkill -f "python3 app.py" 2>/dev/null || true
    sleep 1 # Laisser le temps aux processus de se terminer
}

while true; do
    # Nettoyer avant chaque lancement
    cleanup

    echo "----------------------------------------------------------------" >> logs/pimmich.log
    echo "[start_pimmich] Lancement de l'application Pimmich à $(date)..." >> logs/pimmich.log
    
    # Vérifier et activer l'environnement virtuel
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    else
        echo "[start_pimmich] ERREUR CRITIQUE: Environnement virtuel 'venv' introuvable !" >> logs/pimmich.log
        sleep 10
        continue
    fi

    # Lancer l'application 
    python3 -u app.py #>> logs/pimmich.log 2>&1

    exit_code=$?
    echo "[start_pimmich] L'application s'est terminée avec le code de sortie : $exit_code" >> logs/pimmich.log

    if [ $exit_code -eq 0 ]; then
        echo "[start_pimmich] Arrêt normal demandé (Code 0). Fin du script." >> logs/pimmich.log
        break
    fi

    if [ $exit_code -ne $RESTART_CODE ]; then
        echo "[start_pimmich] Code de sortie inattendu ($exit_code). Redémarrage de sécurité dans 5s..." >> logs/pimmich.log
        sleep 5 # Pause de sécurité pour éviter une boucle rapide en cas de crash
        continue
    fi

    echo "[start_pimmich] Redémarrage demandé. Relance de l'application dans 2 secondes..." >> logs/pimmich.log
    sleep 2
done
