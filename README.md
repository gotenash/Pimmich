# 🖼️ Pimmich – Cadre photo connecté intelligent

Pimmich est une application Python conçue pour transformer un Raspberry Pi en cadre photo numérique intelligent, capable d'afficher des albums hébergés sur un serveur Immich ou sur une clé USB.

![Pimmich Logo](static/pimmich_logo.png)

---

## ✨ Fonctionnalités

- 🔒 Interface sécurisée avec login
- 🖼️ Slideshow dynamique avec effet Pan & Zoom (en développement)
- 🌐 Intégration avec l’API Immich (récupération automatique d’albums)
- 📂 Support de la clé USB comme source alternative d’images (en développement)
- 🕒 Horaires configurables pour l’affichage automatique
- 💡 Interface web locale pour la configuration (http://IP-du-Pi:5000)
- ⚙️ Multi-albums sélectionnables
- 🔌 Boutons de redémarrage et extinction du système

---

## 🧰 Technologies utilisées

- Python 
- Flask
- Requests
- Pygame
- Pillow
- Tkinter (interface du slideshow)
- Immich API

---

## 📦 Installation

### ✅ Pré-requis

- Raspberry Pi avec Raspberry Pi OS Lite ou Desktop (32-bit ou 64-bit)
- Connexion Internet
- Python 
- Clavier + écran pour la première configuration, ou SSH

Vous avez dit :
oui


ChatGPT a dit :
Parfait ! Voici une version complète et claire pour la section Installation & Configuration initiale du README, intégrant tout ce que tu souhaites :

Pimmich - Cadre Photo Connecté
Installation
Téléchargez le projet sur votre Raspberry Pi ou ordinateur avec la commande :

bash
Copier
Modifier
git clone https://github.com/gotenash/pimmich.git
cd pimmich
Exécutez le script d'installation pour installer les dépendances et configurer le système :

bash
Copier
Modifier
sudo ./setup.sh
Ce script installe toutes les dépendances nécessaires (Python, Pygame, Flask, Pillow, Requests, etc.) et configure le démarrage automatique.

Préparez la carte SD avec l'image Raspberry Pi OS (version Desktop recommandée pour plus de simplicité).
Vous pouvez écrire l’image à l’aide de Raspberry Pi Imager ou un outil similaire.

Configuration initiale
Après l’écriture de l’image sur la carte SD et l’installation du projet, vous devez créer un fichier credentials.json pour sécuriser l’accès à l’interface web de configuration.

Montez la partition /boot de la carte SD (accessible directement sous Windows ou Linux) ou accédez-y via le Raspberry Pi.

Créez un fichier nommé credentials.json à la racine de cette partition (/boot/ ou /boot/firmware/) contenant vos identifiants au format JSON :

json
Copier
Modifier
{
  "username": "admin",
  "password": "votre_mot_de_passe"
}
Sauvegardez et démontez la carte SD.

Insérez la carte SD dans le Raspberry Pi et démarrez-le.

Utilisation
Le diaporama se lance automatiquement au démarrage.

Pour accéder à la page de configuration, ouvrez un navigateur et rendez-vous à l’adresse IP du Raspberry Pi sur le port 5000 (exemple : http://192.168.1.x:5000).

Connectez-vous avec les identifiants définis dans credentials.json.

Vous pourrez alors modifier les paramètres de l’album photo, les horaires d’activité, etc.
