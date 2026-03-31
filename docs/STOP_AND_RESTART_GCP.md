# Tuto : arrêter les coûts GCP et relancer vite

Ce guide explique comment mettre l'hébergement en pause pour payer le moins possible, puis relancer rapidement.

## Ce qui coûte dans votre setup actuel

- Cluster GKE Autopilot
- Service Kubernetes de type `LoadBalancer` (IP publique)
- Trafic réseau sortant (si utilisé)
- Artifact Registry (stockage des images)

## Objectif "payer 0"

Sur GCP, "0 exact" n'est pas garanti à 100% tant que le projet existe (ex: quelques centimes de stockage/arrondis possibles).  
Pour viser un coût quasi nul, il faut arrêter au moins:

1. le Service `LoadBalancer`
2. les workloads de l'app
3. idéalement le cluster

## Option A (recommandée) : pause quasi totale, relance rapide

Conserve les fichiers du dépôt, supprime les ressources runtime.

### Arrêter (pause)

```bash
# 1) Se connecter au cluster
gcloud container clusters get-credentials weather-planner --region=europe-west9

# 2) Supprimer l'IP publique payante
kubectl delete svc weather-planner-svc

# 3) Supprimer l'app (pods)
kubectl delete deployment weather-planner
```

Si tu veux aller plus loin côté coût:

```bash
# 4) Supprimer le cluster (arrêt presque complet des coûts runtime GKE)
gcloud container clusters delete weather-planner --region=europe-west9 --quiet
```

### Relancer

```bash
# 1) (Re)créer le cluster si supprimé
gcloud container clusters create-auto weather-planner --region=europe-west9

# 2) Récupérer les credentials kubectl
gcloud container clusters get-credentials weather-planner --region=europe-west9

# 3) Redéployer
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# 4) Attendre l'IP publique
kubectl get svc weather-planner-svc -w
```

URL d'accès:

```text
http://EXTERNAL-IP
```

## Option B : pause légère (coût réduit mais non nul)

Tu gardes le cluster, mais tu coupes l'app et l'IP publique:

```bash
gcloud container clusters get-credentials weather-planner --region=europe-west9
kubectl scale deployment/weather-planner --replicas=0
kubectl delete svc weather-planner-svc
```

Relance:

```bash
kubectl scale deployment/weather-planner --replicas=1
kubectl apply -f k8s/service.yaml
kubectl get svc weather-planner-svc -w
```

## Vérifications rapides

### Vérifier que c'est bien stoppé

```bash
kubectl get pods
kubectl get svc weather-planner-svc
gcloud container clusters list --region=europe-west9
```

### Vérifier que c'est bien relancé

```bash
kubectl get deployment weather-planner
kubectl get pods -l app=weather-planner
kubectl get svc weather-planner-svc
```

## Note CI/CD GitHub Actions

Si le cluster est supprimé, un push GitHub Actions échouera tant que le cluster n'est pas recréé.  
Après recréation, le workflow de déploiement fonctionne de nouveau sans changement de code.
