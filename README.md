# Weather Running Planner (BAN + Open-Meteo)

Outil CLI Python pour planifier des sorties course a pied sur 7 jours, a partir d'une adresse.

Le programme combine :
- **Geocodage BAN / Geoplateforme** pour convertir une adresse en coordonnees.
- **Open-Meteo** pour recuperer la meteo horaire (pluie, vent, rafales, direction).

Il affiche :
- une **heatmap heure par heure** (rouge -> a eviter, vert -> favorable),
- des **creneaux recommandes** selon tes criteres,
- et te laisse **selectionner manuellement** les creneaux a garder.

---

## 1) Prerequis

- Python 3.11+ (3.13 teste ici)
- Windows / PowerShell (ou autre shell compatible Python)

---

## 2) Installation

Depuis la racine du projet :

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

---

## 3) Lancer l'application

```powershell
.\.venv\Scripts\python chatbot.py
```

Le bot demande ensuite :
1. **Adresse** (d'abord)
2. **Reglages principaux** (persistants dans la session) :
   - horaires dispo semaine
   - horaires dispo week-end
3. **Nombre de sorties souhaitees sur la semaine**
4. **Filtres meteo** :
   - pluie moyenne max (mm/h)
   - vent maximum max (km/h, vent ou rafales)
   - duree de course

---

## 4) Lecture de la heatmap

- Affichage sur **toute la journee** (00h -> 23h), pour chaque jour de la semaine.
- Couleur :
  - **vert** = meilleur creneau potentiel
  - **rouge** = creneau a eviter
- Le score depend surtout de :
  - pluie (au-dessus du seuil choisi)
  - vent max (vent/rafales au-dessus du seuil choisi)

Si ton terminal ne gere pas bien les couleurs ANSI, la heatmap peut apparaître degradee.

---

## 5) Selection manuelle des creneaux

Apres la heatmap, tu peux choisir les creneaux a conserver :

- Ajouter une heure :
  - `add 2026-04-01 18`
- Ajouter une plage :
  - `add 2026-04-01 17-20`
- Supprimer :
  - `del 2026-04-01 18`
  - `del 2026-04-01 17-20`
- Lister la selection :
  - `list`
- Terminer :
  - `done`

Format attendu des creneaux :
- `YYYY-MM-DD HH`
- ou plage `YYYY-MM-DD HH-HH`

---

## 6) APIs utilisees

- BAN / Geoplateforme geocodage :
  - `https://data.geopf.fr/geocodage/search`
- Open-Meteo forecast :
  - `https://api.open-meteo.com/v1/forecast`
- Open-Meteo meteofrance (si dispo) :
  - `https://api.open-meteo.com/v1/meteofrance`

Notes :
- Le code utilise un fallback si l'endpoint `meteofrance` est indisponible.
- Pas de cle API obligatoire pour cette version.

---

## 7) Fichiers principaux

- `chatbot.py` : interface CLI interactive
- `weather_client.py` : appels API, scoring, heatmap, recommandations
- `requirements.txt` : dependances Python

---

## 8) Limitations actuelles

- App CLI (pas d'interface web).
- Score heuristique (pratique, mais pas un modele sportif/medical).
- Selon la qualite du terminal, le rendu couleur peut varier.

