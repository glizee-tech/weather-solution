# Running Planner V2 (interface web FastAPI)

Application web pour planifier des sorties course à pied sur 7 jours à partir d’une adresse en France (ou d’un point choisi sur la carte).

## Statut du projet

Projet de démonstration finalisé.  
Le repository est conservé comme base de référence technique (FastAPI + GKE + CI/CD GitHub Actions).

Pour une reprise rapide en environnement cloud:

```bash
bash start_app.sh
```

Pour arrêter les coûts:

```bash
bash stop_costs.sh
```

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
- `Dockerfile` — image de production (Uvicorn)
- `k8s/` — manifests GKE (Deployment, Service `LoadBalancer`)

## Déploiement GCP — GKE Autopilot, région France (sans domaine)

Région cible : **`europe-west9`** (Paris). Cette version expose l'app en HTTP via une IP publique (pas de nom de domaine requis).

### 1. Prérequis côté GCP

- Projet GCP avec facturation activée
- Outils : `gcloud`, `kubectl`, Docker
- APIs utiles (souvent proposées à la volée) : Container / Kubernetes, Artifact Registry

### 2. Cluster Autopilot

Remplace `PROJECT_ID` par ton projet.

```bash
gcloud config set project PROJECT_ID
gcloud container clusters create-auto weather-planner \
  --region=europe-west9
```

Récupère les identifiants `kubectl` :

```bash
gcloud container clusters get-credentials weather-planner --region=europe-west9
```

### 3. Artifact Registry (image Docker)

```bash
gcloud artifacts repositories create weather-planner \
  --repository-format=docker \
  --location=europe-west9 \
  --description="Running Planner"
gcloud auth configure-docker europe-west9-docker.pkg.dev
```

Build et push (à lancer depuis la racine du dépôt) :

```bash
docker build -t europe-west9-docker.pkg.dev/PROJECT_ID/weather-planner/app:latest .
docker push europe-west9-docker.pkg.dev/PROJECT_ID/weather-planner/app:latest
```

### 4. Kubernetes

1. Dans `k8s/deployment.yaml`, remplace `PROJECT_ID` dans le champ `image` par ton vrai projet (et le tag si besoin).
Applique les manifests :

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

Récupère l’**IP publique** du Service (affiche `EXTERNAL-IP` une fois prêt) :

```bash
kubectl get svc weather-planner-svc -w
```

Quand l'IP est attribuée, ouvre :

```text
http://EXTERNAL-IP
```

### 5. Coûts

Autopilot et le **Service LoadBalancer** sont facturables (cluster, transfert, load balancer, etc.). Consulter la [calculatrice de prix GCP](https://cloud.google.com/products/calculator).

Pour arrêter les coûts puis relancer proprement, voir le guide: `docs/STOP_AND_RESTART_GCP.md`.

Scripts prêts à l'emploi :

- `./stop_costs.sh` : stoppe l'app et supprime le LoadBalancer (option `--delete-cluster` pour minimiser encore plus les coûts)
- `./start_app.sh` : (re)crée le cluster si besoin, redéploie l'app et affiche l'URL HTTP publique

## Notes

- Les scores et suggestions sont **heuristiques** : aide à la décision, pas conseil médical ni sportif professionnel.

## CI/CD GitHub Actions (push sur `master`)

Le workflow `.github/workflows/deploy-master.yml` déploie automatiquement l'API sur GKE à chaque push sur `master` :

1. Authentification à GCP via Workload Identity Federation
2. Build et push de l'image Docker vers Artifact Registry (tag = `GITHUB_SHA`)
3. Update de l'image du `Deployment` Kubernetes + vérification du rollout

### Variables GitHub à créer (Repository variables)

- `GCP_PROJECT_ID` : id du projet GCP (ex: `weather-interface`)
- `GKE_CLUSTER` : nom du cluster (ex: `weather-planner`)
- `GKE_REGION` : région du cluster (ex: `europe-west9`)
- `GAR_LOCATION` : région Artifact Registry (ex: `europe-west9`)
- `GAR_REPOSITORY` : dépôt Artifact Registry (ex: `weather-planner`)
- `K8S_NAMESPACE` : namespace Kubernetes (optionnel, défaut: `default`)
- `K8S_DEPLOYMENT` : nom du Deployment (optionnel, défaut: `weather-planner`)
- `K8S_CONTAINER` : nom du container dans le Deployment (optionnel, défaut: `weather-planner`)

### Secrets GitHub à créer (Repository secrets)

- `GCP_WIF_PROVIDER` : ressource Workload Identity Provider (format complet `projects/.../providers/...`)
- `GCP_SERVICE_ACCOUNT` : email du service account utilisé par GitHub Actions
