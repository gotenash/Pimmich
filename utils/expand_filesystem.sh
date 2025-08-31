#!/bin/bash

# Ce script est conçu pour être exécuté par l'application web Pimmich.
# Il utilise l'outil raspi-config pour étendre la partition racine afin
# qu'elle utilise tout l'espace disponible sur la carte SD.

set -e # Arrête le script si une commande échoue

echo "STEP:START:--- Lancement de l'extension du système de fichiers ---"
echo "STEP:INFO:Utilisation de raspi-config pour étendre la partition racine..."
sudo raspi-config --expand-rootfs
echo "STEP:DONE:La modification a été programmée. L'extension sera finalisée au prochain redémarrage du système. Veuillez redémarrer le Raspberry Pi depuis l'interface pour appliquer les changements."