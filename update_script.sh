#!/bin/bash
# Ce script est exécuté par l'application web pour se mettre à jour.
# Il ne doit pas redémarrer de service lui-même, car l'application web
# se chargera de se terminer pour être relancée par son superviseur (systemd, etc.).

set -e # Arrête le script si une commande échoue

# Se placer dans le répertoire racine de Pimmich
cd "$(dirname "$0")"

echo "STEP:PULL:--- Étape 1/2: Téléchargement des mises à jour (git pull) ---"
git pull

echo "STEP:PIP:--- Étape 2/2: Mise à jour des dépendances Python ---"
source venv/bin/activate
pip install -r requirements.txt

echo "STEP:RESTART:Mise à jour des fichiers terminée. L'application va redémarrer."