# 🖼️ Pimmich – Cadre photo connecté intelligent

Pimmich est une application Python conçue pour transformer un Raspberry Pi en cadre photo numérique intelligent, capable d'afficher des albums hébergés sur un serveur Immich ou sur une clé USB. Toutes suggestions  d'évolution du système seront prises en compte.

<img src="static/pimmich_logo.png" alt="Pimmich Logo" width="300">

---

## ✨ Fonctionnalités

- 🔒 Interface sécurisée avec login
- 🖼️ Slideshow dynamique avec effet Pan & Zoom (en développement)
- 🌐 Intégration avec l’API Immich (récupération automatique d’albums)
- 📂 Support de la clé USB comme source alternative d’images (en développement)
- 🕒 Horaires configurables pour l’affichage automatique
- 💡 Interface web locale pour la configuration (http://IP-du-Pi:5000)
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

A terme il y aura deux possibilités d'installer Pimmich une img prêt à l'emploi (pas encore disponible) et le clonage du dépôt qui est fonctionnel hormis la gestion de la clef USB.

### ✅ Pré-requis

- Raspberry Pi avec Raspberry Pi OS Desktop (64-bit)
- Connexion Internet
- Python 
- Clavier + écran pour la première configuration, ou SSH

### Création du fichier credentials.json

À la racine de la carte SD, crée un fichier credentials.json contenant les identifiants pour accéder à la page de configuration :

```json
{
  "username": "votre_nom_utilisateur",
  "password": "votre_mot_de_passe"
}
```


### Installation à partir du dépôt

#### Installation de GIT

```bash
sudo apt-get install git
```

#### Clonage du dépôt

```bash
git clone https://github.com/gotenash/pimmich.git
cd pimmich
````

#### Lancement du Setup.sh

Ces commandes permettre de rendre le fgichier setup.sh exécutable et lance le setup
```bash
chmod +x setup.sh
sudo ./setup.sh
```
Ce script installe les dépendances système et Python, configure l’environnement, et prépare le démarrage automatique du diaporama.

### Récupérer la Clef API (Token Immich)

🧭 1. Se connecter à l'interface web d’Immich

⚙️ 2. Accéder à la page "Paramètres du compte"
Une fois connecté :

Clique sur l’icône de profil (en haut à droite) ou ton nom d'utilisateur.

![Paramètre du compte](https://drive.google.com/uc?id=1_c12UZ7g8IwsL99xP55eB4qqacGAY8Kc)


Sélectionne “Account settings” ou “Paramètres du compte”.

![Menu Clef API](https://drive.google.com/uc?id=1rofAi6HNhvJbBh2D_AUsedj3HwSrQHjP)


🧪 3. Générer un nouveau token API
Dans la section "API Key" ou "Clés API" :

![Menu Clef API](https://drive.google.com/uc?id=1HrBVgvR4UXdkhLj-4KDohufr5nt57t2G)

Clique sur “Generate new API Key” ou “Générer une nouvelle clé API”.
![Menu Clef API](https://drive.google.com/uc?id=1dRBQMs0dsdM7vKlEuUzBnMmzzH3RNplc)

### Se connecter à Pimmich


### Page de configuration

Donne un nom à ta clé, par exemple :
PimmichFrame

✅ Une fois générée, une clé s'affiche. C’est le token à copier.

![Menu Clef API](https://drive.google.com/uc?id=1hyt14hFPN3XEBu_0rh9XYIgLdXJau22y)

⚠️ Attention

Tu ne pourras plus voir cette clé après avoir quitté la page. Si tu la perds, il faudra en générer une nouvelle.

Ne partage jamais ce token publiquement. Il donne un accès total à tes albums Immich.

Le mieux est de créer un compte Immich réservé au cadre photo avec accès à un seul album que tu pourras alimenter à partir d'un autre compte.


