# Procédure de Mise à Jour des Traductions pour Pimmich

Ce document décrit la procédure complète pour mettre à jour les fichiers de traduction de l'application Pimmich, en utilisant un script personnalisé et la bibliothèque `deep-translator`.

---

## 1. Prérequis

Avant de commencer, assurez-vous que les outils suivants sont installés dans votre environnement virtuel.

### a. Activer l'environnement virtuel

Toutes les commandes doivent être lancées depuis le dossier racine du projet (`/home/pi/pimmich`) avec l'environnement virtuel activé :
```bash
source venv/bin/activate
```

### b. Installer les outils nécessaires

Si ce n'est pas déjà fait, installez les bibliothèques nécessaires (qui devraient être incluses dans `requirements.txt`) :
```bash
pip install deep-translator polib
```

### c. Fichier de configuration `babel.cfg`

Assurez-vous que le fichier `babel.cfg` existe à la racine du projet avec le contenu suivant. Ce fichier indique à l'outil où trouver les textes à traduire.

```ini
[python: **.py]
[jinja2: **/templates/**.html]
extensions=jinja2.ext.i18n
```

---

## 2. Procédure de Mise à Jour

Le processus se déroule en 4 étapes principales.

### Étape 1 : Extraction des textes à traduire

Cette commande scanne tous les fichiers `.py` et `.html` du projet, recherche les textes marqués pour la traduction (par exemple, `_('Mon texte')`), et crée/met à jour un fichier modèle `messages.pot`.

```bash
pybabel extract -F babel.cfg -o translations/messages.pot .
```
**Note :** N'oubliez pas le `.` à la fin de la commande, qui signifie "analyser le dossier courant".

### Étape 2 : Mise à jour des fichiers de langue

Cette commande compare le fichier modèle (`messages.pot`) avec les fichiers de traduction de chaque langue (`.po`) et y ajoute les nouveaux textes à traduire.

```bash
pybabel update -i translations/messages.pot -d translations
```

### Étape 3 : Traduction automatique

C'est ici que notre script personnalisé `utils/translate_po.py` intervient. Il utilise une bibliothèque fiable pour traduire les textes manquants. Lancez les commandes suivantes pour chaque langue.

```bash
# Traduire le fichier anglais
python utils/translate_po.py translations/en/LC_MESSAGES/messages.po en

# Traduire le fichier espagnol
python utils/translate_po.py translations/es/LC_MESSAGES/messages.po es
```
**Conseil :** Après cette étape, il est recommandé d'ouvrir les fichiers `.po` avec un éditeur comme Poedit pour relire rapidement les traductions automatiques et corriger d'éventuels contresens.

### Étape 4 : Compilation des traductions

Cette dernière commande transforme les fichiers texte `.po` (lisibles par l'homme) en fichiers binaires optimisés `.mo` que l'application utilise pour afficher les traductions.

```bash
pybabel compile -d translations
```

---

Une fois ces étapes terminées, redémarrez l'application Pimmich pour que les nouvelles traductions soient prises en compte.

---

## 3. Comment convertir ce document en PDF

*   **Avec VS Code :** Installez une extension comme "Markdown PDF" et faites un clic droit sur le fichier `.md` pour l'exporter.
*   **En ligne :** Utilisez un site web comme md2pdf.netlify.app en y copiant-collant ce texte.
*   **En ligne de commande :** Si vous avez `pandoc` d'installé, utilisez la commande : `pandoc procedure_traduction.md -o procedure.pdf`.
