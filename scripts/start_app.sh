#!/usr/bin/env bash
set -euo pipefail

# Start app on GKE and print public HTTP URL.
# If cluster does not exist, it is created automatically.

PROJECT_ID="${PROJECT_ID:-weather-interface}"
REGION="${REGION:-europe-west9}"
CLUSTER_NAME="${CLUSTER_NAME:-weather-planner}"
NAMESPACE="${NAMESPACE:-default}"
SERVICE_NAME="${SERVICE_NAME:-weather-planner-svc}"
DEPLOYMENT_MANIFEST="${DEPLOYMENT_MANIFEST:-k8s/deployment.yaml}"
SERVICE_MANIFEST="${SERVICE_MANIFEST:-k8s/service.yaml}"

echo "Using project=$PROJECT_ID region=$REGION cluster=$CLUSTER_NAME namespace=$NAMESPACE"
gcloud config set project "$PROJECT_ID" >/dev/null

if ! gcloud container clusters describe "$CLUSTER_NAME" --region "$REGION" >/dev/null 2>&1; then
  echo "Cluster not found. Creating $CLUSTER_NAME..."
  gcloud container clusters create-auto "$CLUSTER_NAME" --region "$REGION"
fi

echo "Getting kubectl credentials..."
gcloud container clusters get-credentials "$CLUSTER_NAME" --region "$REGION" >/dev/null

echo "Applying Kubernetes manifests..."
kubectl apply -f "$DEPLOYMENT_MANIFEST"
kubectl apply -f "$SERVICE_MANIFEST"

echo "Waiting for external IP on service $SERVICE_NAME..."
EXTERNAL_IP=""
for _ in $(seq 1 90); do
  EXTERNAL_IP="$(kubectl -n "$NAMESPACE" get svc "$SERVICE_NAME" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
  if [[ -n "$EXTERNAL_IP" ]]; then
    break
  fi
  sleep 5
done

if [[ -z "$EXTERNAL_IP" ]]; then
  echo "External IP not ready yet."
  echo "Run: kubectl -n $NAMESPACE get svc $SERVICE_NAME -w"
  exit 1
fi

echo "App is available at:"
echo "http://$EXTERNAL_IP"
