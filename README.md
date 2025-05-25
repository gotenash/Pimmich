# 🖼️ Pimmich – Cadre photo connecté intelligent

Pimmich est une application Python conçue pour transformer un Raspberry Pi en cadre photo numérique intelligent, capable d'afficher des albums hébergés sur un serveur Immich ou sur une clé USB.

<img src="static/pimmich_logo.png" alt="Pimmich Logo" width="300">

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

### Création du fichier credentials.json

```json
{
  "username": "votre_nom_utilisateur",
  "password": "votre_mot_de_passe"
}
```


### Installation à partir du dépôt

#### Installation de GIT

#### Clonage du dépôt

```bash
git clone https://github.com/gotenash/pimmich.git
cd pimmich
````

#### Lancement du Setup.sh

### Récupérer la Clef API (Token Immich)

🧭 1. Se connecter à l'interface web d’Immich

⚙️ 2. Accéder à la page "Paramètres du compte"
Une fois connecté :

Clique sur l’icône de profil (en haut à droite) ou ton nom d'utilisateur.

![Paramètre du compte](https://drive.google.com/uc?id=1_c12UZ7g8IwsL99xP55eB4qqacGAY8Kc)


Sélectionne “Account settings” ou “Paramètres du compte”.

![Menu Clef API](https://drive.google.com/uc?id=1rofAi6HNhvJbBh2D_AUsedj3HwSrQHjP)
