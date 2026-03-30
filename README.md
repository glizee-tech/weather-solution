# Running Planner V2 (interface web FastAPI)

Application web pour planifier des sorties course à pied sur 7 jours à partir d’une adresse en France (ou d’un point choisi sur la carte).

## Fonctionnalités

- **Adresse** : géocodage direct (BAN / Géoplateforme) ou **clic sur la carte** (géocodage inverse) pour remplir le lieu.
- **Carte** : Leaflet + fond OpenStreetMap, marqueur sur le lieu retenu.
- **Filtres** : pluie max (mm/h), vent max (km/h, prise en compte des rafales), durée de sortie, plages horaires semaine / week-end, nombre de sorties souhaitées par semaine.
- **Heatmap 7×24** : score heure par heure ; les créneaux dans tes plages « disponibles » sont mis en évidence ; libellés des jours en français (ex. *lundi 3 mars 2026*).
- **Sélection manuelle** des créneaux ; pour chaque créneau choisi, **flèche de vent** (direction d’où vient le vent, convention météo).
- **Plan de sortie suggéré** : jusqu’à une sortie par jour (max 7) ; priorité aux **meilleures conditions** (pluie, vent, respect des seuils), puis espacement des jours ; pour 2 ou 3 sorties, au moins un jour d’écart entre deux dates quand c’est possible.

## Prérequis

- Python 3.11+
- Windows / PowerShell (ou environnement compatible)

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

## Lancement

À la racine du projet :

```powershell
.\.venv\Scripts\uvicorn app:app --reload
```

Ouvrir [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Utilisation

1. Saisir une adresse et cliquer sur **Localiser**, ou **cliquer sur la carte** pour remplir l’adresse automatiquement.
2. Ajuster les paramètres (pluie, vent, durée, disponibilités, sorties / semaine).
3. Cliquer sur **Calculer le plan**.
4. Consulter la heatmap, le **plan de sortie suggéré** et cliquer les cases pour constituer ta propre sélection de créneaux.

## APIs externes

| Service | Rôle |
|--------|------|
| **BAN** — `https://data.geopf.fr/geocodage/search` | Adresse → coordonnées |
| **BAN** — `https://data.geopf.fr/geocodage/reverse` | Clic carte → adresse |
| **Open-Meteo** — `https://api.open-meteo.com/v1/forecast` | Prévisions horaires sur la semaine (base) |
| **Open-Meteo** — `https://api.open-meteo.com/v1/meteofrance` | Modèles Météo-France (AROME / ARPEGE) pour les premiers jours, **fusionnés** avec le forecast quand l’appel réussit ; sinon seul le forecast est utilisé |

Aucune clé API n’est nécessaire pour ces services dans cette version. Aucun fichier `.env` n’est requis.

## Endpoints HTTP (local)

| Méthode | Chemin | Description |
|---------|--------|-------------|
| `GET` | `/` | Interface web |
| `POST` | `/api/geocode` | Corps JSON `{ "address": "…" }` |
| `POST` | `/api/reverse` | Corps JSON `{ "latitude": …, "longitude": … }` |
| `POST` | `/api/plan` | Paramètres du formulaire ; `address` peut être vide si `latitude` et `longitude` sont fournis |

## Structure du projet

- `app.py` — FastAPI, routes et validation des requêtes
- `templates/index.html` — page unique
- `static/app.js` — carte, heatmap, appels API
- `static/styles.css` — mise en forme
- `weather_client.py` — géocodage, Open-Meteo, scoring, payload JSON (plan, recommandations)

## Notes

- Les scores et suggestions sont **heuristiques** : aide à la décision, pas conseil médical ni sportif professionnel.
