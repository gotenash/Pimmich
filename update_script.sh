#!/bin/bash
# Ce script est exécuté par l'application web pour se mettre à jour.
# Il ne doit pas redémarrer de service lui-même, car l'application web
# se chargera de se terminer pour être relancée par son superviseur (systemd, etc.).

set -e # Arrête le script si une commande échoue

# Se placer dans le répertoire racine de Pimmich
cd "$(dirname "$0")"

echo "STEP:PULL:--- Étape 1/2: Téléchargement des mises à jour (git) ---"
# Utilise une méthode robuste qui évite les blocages dus aux conflits locaux.
git fetch --all
git reset --hard origin/main

echo "STEP:PIP:--- Étape 2/2: Mise à jour des dépendances Python ---"
source venv/bin/activate

# Rediriger la sortie de pip vers un fichier de log pour le débogage
# et vérifier le code de retour manuellement pour ne pas bloquer le redémarrage.
if ! pip install -r requirements.txt > logs/update_pip.log 2>&1; then
    echo "STEP:WARNING:--- AVERTISSEMENT: La mise à jour des dépendances a échoué. ---"
    echo "STEP:WARNING:L'application va quand même redémarrer, mais pourrait être instable."
    echo "STEP:WARNING:Consultez le fichier 'logs/update_pip.log' depuis l'onglet Système pour les détails."
fi

echo "STEP:RESTART:Mise à jour des fichiers terminée. L'application va redémarrer."