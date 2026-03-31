#!/usr/bin/env bash
set -euo pipefail

# Stop app costs on GCP/GKE.
# Default behavior keeps the cluster (faster restart).
# Use --delete-cluster to remove the cluster too (lowest runtime cost).

PROJECT_ID="${PROJECT_ID:-weather-interface}"
REGION="${REGION:-europe-west9}"
CLUSTER_NAME="${CLUSTER_NAME:-weather-planner}"
NAMESPACE="${NAMESPACE:-default}"
DELETE_CLUSTER="false"

for arg in "$@"; do
  case "$arg" in
    --delete-cluster)
      DELETE_CLUSTER="true"
      ;;
    *)
      echo "Unknown argument: $arg"
      echo "Usage: ./stop_costs.sh [--delete-cluster]"
      exit 1
      ;;
  esac
done

echo "Using project=$PROJECT_ID region=$REGION cluster=$CLUSTER_NAME namespace=$NAMESPACE"
gcloud config set project "$PROJECT_ID" >/dev/null

if gcloud container clusters describe "$CLUSTER_NAME" --region "$REGION" >/dev/null 2>&1; then
  gcloud container clusters get-credentials "$CLUSTER_NAME" --region "$REGION" >/dev/null

  echo "Deleting public LoadBalancer service (if present)..."
  kubectl -n "$NAMESPACE" delete svc weather-planner-svc --ignore-not-found

  echo "Deleting app deployment (if present)..."
  kubectl -n "$NAMESPACE" delete deployment weather-planner --ignore-not-found

  if [[ "$DELETE_CLUSTER" == "true" ]]; then
    echo "Deleting cluster $CLUSTER_NAME..."
    gcloud container clusters delete "$CLUSTER_NAME" --region "$REGION" --quiet
  else
    echo "Cluster kept for quick restart."
  fi
else
  echo "Cluster $CLUSTER_NAME not found. Nothing to stop."
fi

echo "Done."
