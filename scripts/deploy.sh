#!/usr/bin/env bash
# Deploy backend to Cloud Run (with env var sync) and frontend to Firebase Hosting.
#
# Usage:
#   ./scripts/deploy.sh                  # deploy everything
#   ./scripts/deploy.sh --backend-only   # backend + env vars only
#   ./scripts/deploy.sh --frontend-only  # frontend only
#   ./scripts/deploy.sh --env-only       # sync env vars only (no rebuild)

set -euo pipefail

PROJECT="tokenized-deposits"
REGION="us-central1"
SERVICE="tokenized-deposits-backend"
ROOT="$(dirname "$0")/.."
ENV_FILE="$ROOT/backend/.env"

# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------
RUN_BACKEND=true
RUN_FRONTEND=true
ENV_ONLY=false

for arg in "$@"; do
  case $arg in
    --backend-only)  RUN_FRONTEND=false ;;
    --frontend-only) RUN_BACKEND=false ;;
    --env-only)      ENV_ONLY=true; RUN_FRONTEND=false ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
build_env_vars() {
  local vars=""
  local skip="HARDHAT_RPC_URL GOOGLE_APPLICATION_CREDENTIALS"

  while IFS= read -r line; do
    [[ -z "$line" || "$line" == \#* ]] && continue
    local key="${line%%=*}"
    local value="${line#*=}"
    local skip_key=false
    for s in $skip; do [[ "$key" == "$s" ]] && skip_key=true && break; done
    $skip_key && continue
    value="${value//,/\\,}"
    vars="${vars:+$vars,}${key}=${value}"
  done < "$ENV_FILE"

  echo "$vars"
}

service_url() {
  gcloud run services describe "$SERVICE" \
    --project "$PROJECT" \
    --region "$REGION" \
    --format 'value(status.url)'
}

# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------
if $RUN_BACKEND; then
  if ! $ENV_ONLY; then
    echo "==> [backend] Deploying to Cloud Run..."
    gcloud run deploy "$SERVICE" \
      --source "$ROOT/backend" \
      --project "$PROJECT" \
      --region "$REGION" \
      --allow-unauthenticated \
      --platform managed \
      --quiet
    echo "==> [backend] Deploy complete."
  fi

  echo "==> [backend] Syncing env vars from $ENV_FILE..."
  ENV_VARS="$(build_env_vars)"
  gcloud run services update "$SERVICE" \
    --project "$PROJECT" \
    --region "$REGION" \
    --set-env-vars "$ENV_VARS"
  echo "==> [backend] Env vars synced."
fi

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
if $RUN_FRONTEND; then
  echo "==> [frontend] Building Flutter web with BASE_API_URL=/api (proxied by Firebase Hosting)"
  (cd "$ROOT/frontend" && flutter build web \
    --dart-define="BASE_API_URL=/api")
  echo "==> [frontend] Build complete."

  echo "==> [frontend] Deploying to Firebase Hosting..."
  firebase deploy --only hosting --project "$PROJECT"
  echo "==> [frontend] Deploy complete."
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "====================================="
if $RUN_BACKEND || $ENV_ONLY; then
  echo "Backend:  $(service_url)"
fi
if $RUN_FRONTEND; then
  echo "Frontend: https://${PROJECT}.web.app"
fi
echo "====================================="
