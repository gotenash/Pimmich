# Icônes Météo pour Pimmich

Ce dossier est destiné à contenir les icônes météo utilisées par le diaporama.

## Comment obtenir les icônes ?

Pimmich utilise les codes d'icônes de l'API OpenWeatherMap. Vous devez télécharger les images correspondantes et les placer dans ce dossier.

1.  **Rendez-vous sur la page des conditions météorologiques d'OpenWeatherMap :**
    [https://openweathermap.org/weather-conditions](https://openweathermap.org/weather-conditions)

2.  **Téléchargez les icônes.** Pour chaque code d'icône (par exemple, `01d`, `10n`), vous pouvez télécharger l'image correspondante. Le format de l'URL est :
    `https://openweathermap.org/img/wn/CODE@2x.png`

    Remplacez `CODE` par le code de l'icône. Par exemple, pour `10d` (pluie de jour), l'URL est :
    https://openweathermap.org/img/wn/10d@2x.png

3.  **Enregistrez les images dans ce dossier** (`static/weather_icons/`) en les nommant d'après leur code, suivi de `.png`.
    -   `10d@2x.png` doit être renommé en `10d.png`.
    -   `01n@2x.png` doit être renommé en `01n.png`.
    -   etc.

### Liste des icônes courantes à télécharger :

*   `01d.png` (ciel dégagé, jour) & `01n.png` (nuit)
*   `02d.png` (quelques nuages, jour) & `02n.png` (nuit)
*   `03d.png` & `03n.png` (nuages épars)
*   `04d.png` & `04n.png` (nuages fragmentés)
*   `09d.png` & `09n.png` (averse de pluie)
*   `10d.png` (pluie, jour) & `10n.png` (nuit)
*   `11d.png` & `11n.png` (orage)
*   `13d.png` & `13n.png` (neige)
*   `50d.png` & `50n.png` (brouillard)

Téléchargez au minimum celles que vous rencontrez le plus souvent dans votre région. Si une icône est manquante, seul le texte s'affichera.