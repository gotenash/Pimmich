# ❓ Foire Aux Questions (FAQ) - Pimmich

Voici une liste de questions fréquemment posées pour vous aider à utiliser et dépanner Pimmich.

---

### Questions Générales

**Q : Qu'est-ce que Pimmich ?**

**R :** Pimmich est un logiciel qui transforme un Raspberry Pi en un cadre photo numérique intelligent. Il peut afficher des photos depuis un serveur [Immich](https://immich.app/), une clé USB, un partage réseau (Samba/Windows), un smartphone ou même via l'application de messagerie Telegram.

**Q : De quoi ai-je besoin pour utiliser Pimmich ?**

**R :** Il vous faut :
- Un Raspberry Pi (modèle 3, 4 ou 5 recommandé) avec son alimentation.
- Une carte SD avec Raspberry Pi OS (64-bit) installé.
- Un écran.
- Une connexion Internet (Wi-Fi ou Ethernet).

---

### Installation et Configuration

**Q : Comment installer Pimmich ?**

**R :** L'installation est conçue pour être simple :
1. Clonez le dépôt GitHub : `git clone https://github.com/gotenash/pimmich.git`
2. Allez dans le dossier : `cd pimmich`
3. Rendez le script d'installation exécutable : `chmod +x setup.sh`
4. Lancez le script avec les droits d'administrateur : `sudo ./setup.sh`
Le script s'occupe d'installer toutes les dépendances et de configurer le système pour un démarrage automatique.

**Q : Comment accéder à l'interface de configuration ?**

**R :** Une fois le Raspberry Pi démarré, ouvrez un navigateur web sur un autre appareil (ordinateur, smartphone) connecté au même réseau et tapez simplement l'adresse IP de votre Raspberry Pi. Par exemple : `http://192.168.1.25`. Si vous ne connaissez pas l'IP, elle est souvent affichée sur l'écran du cadre au premier démarrage ou si aucune photo n'est trouvée.

**Q : J'ai oublié mon mot de passe pour l'interface web. Comment le réinitialiser ?**

**R :** Le mot de passe initial est stocké dans le fichier `/boot/firmware/credentials.json`. Vous pouvez vous connecter en SSH à votre Raspberry Pi pour lire ce fichier. Si vous l'avez changé via l'interface et oublié, vous devrez supprimer ce fichier et redémarrer le Pi pour qu'il en génère un nouveau (attention, cela réinitialisera l'utilisateur).

**Q : Comment obtenir un Token API Immich ?**

**R :**
1. Connectez-vous à votre interface web Immich.
2. Allez dans "Paramètres du compte" (via votre icône de profil).
3. Dans la section "Clés API", cliquez sur "Générer une nouvelle clé API".
4. Donnez-lui un nom (ex: "Pimmich") et copiez la clé générée.

*Conseil :* Pour plus de sécurité, créez un utilisateur Immich dédié pour le cadre avec un accès limité à un seul album partagé.

---

### Fonctionnalités

**Q : Comment fonctionne la fonction Telegram ?**

**R :** Elle vous permet, ainsi qu'à des invités, d'envoyer des photos directement sur le cadre.
1.  **Créez un bot** sur Telegram en parlant à `@BotFather`. Il vous donnera un **Token**.
2.  **Obtenez votre ID utilisateur** Telegram en parlant à un bot comme `@userinfobot`.
3.  Entrez ces deux informations dans l'onglet "Telegram" de Pimmich.
4.  Vous pouvez ensuite créer des liens d'invitation sécurisés et temporaires pour vos proches.

**Q : À quoi sert l'onglet "Favoris" ?**

**R :** En marquant une photo comme favorite (via l'icône étoile <i class="fas fa-star"></i> dans l'onglet "Aperçu"), vous augmentez sa fréquence d'apparition dans le diaporama. Vous pouvez régler le "facteur de boost" dans l'onglet "Affichage" pour qu'elles apparaissent plus ou moins souvent.

**Q : Qu'est-ce que l'effet "Carte Postale" ?**

**R :** C'est un filtre qui ajoute un cadre blanc et un espace pour une légende (si vous en ajoutez une via l'interface) à vos photos, leur donnant un aspect de carte postale. Les photos envoyées via Telegram utilisent cet effet par défaut pour un rendu plus personnel et chaleureux.

---

### Dépannage (Troubleshooting)

**Q : J'ai un problème, où puis-je trouver de l'aide ?**

**R :** L'onglet **Système** est le meilleur endroit pour commencer. Il contient une section **Logs**.
- `app.py` contient les logs du serveur web (interface de configuration).
- `local_slideshow_stdout` et `local_slideshow_stderr` contiennent les logs du diaporama lui-même. Les erreurs s'afficheront le plus souvent dans `stderr`.

**Q : Les vidéos ne sont pas fluides ou ne s'affichent pas. Que faire ?**

**R :** Dans l'onglet **Affichage**, essayez d'activer l'option "**Activer le décodage vidéo matériel**". C'est beaucoup plus performant, surtout sur Raspberry Pi. Si cela cause des problèmes (écran noir/bleu après une vidéo), désactivez-la.

**Q : Le Wi-Fi ne se connecte pas, mais l'Ethernet (câble) fonctionne. Pourquoi ?**

**R :** Parfois, si un câble Ethernet est branché, le système lui donne la priorité. Dans l'onglet **Système**, vous pouvez essayer de désactiver temporairement l'interface "**Interface Filaire (eth0)**" pour forcer le système à utiliser exclusivement le Wi-Fi.

**Q : Comment mettre à jour Pimmich ?**

**R :** Allez dans l'onglet **Système** et cliquez sur le bouton "**Vérifier les mises à jour**". Pimmich se chargera de télécharger la dernière version depuis GitHub et de redémarrer automatiquement.

**Q : J'ai modifié une configuration mais rien ne change sur le diaporama.**

**R :** Certaines modifications, notamment celles liées à l'affichage (police, météo, etc.), nécessitent un redémarrage du diaporama pour être prises en compte. Vous pouvez le faire depuis l'onglet **Actions** en cliquant sur "Arrêter" puis "Démarrer le diaporama". Pour les changements plus profonds, un redémarrage de l'application web ou du système (depuis l'onglet **Système**) peut être nécessaire.