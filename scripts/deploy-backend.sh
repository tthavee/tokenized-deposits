#!/usr/bin/env bash
# Deploy the FastAPI backend to Cloud Run and sync environment variables from .env.
#
# Usage:
#   ./scripts/deploy-backend.sh              # deploy + sync env vars
#   ./scripts/deploy-backend.sh --env-only   # update env vars without redeploying
#   ./scripts/deploy-backend.sh --deploy-only # deploy without updating env vars

set -euo pipefail

PROJECT="tokenized-deposits"
REGION="us-central1"
SERVICE="tokenized-deposits-backend"
ENV_FILE="$(dirname "$0")/../backend/.env"

# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------
DEPLOY=true
UPDATE_ENV=true

for arg in "$@"; do
  case $arg in
    --env-only)    DEPLOY=false ;;
    --deploy-only) UPDATE_ENV=false ;;
  esac
done

# ---------------------------------------------------------------------------
# Build env-vars string from .env (skip comments, blanks, and local-only keys)
# ---------------------------------------------------------------------------
build_env_vars() {
  local vars=""
  # Keys that only make sense locally — skip them in Cloud Run
  local skip="HARDHAT_RPC_URL GOOGLE_APPLICATION_CREDENTIALS"

  while IFS= read -r line; do
    # Skip blank lines and comments
    [[ -z "$line" || "$line" == \#* ]] && continue

    key="${line%%=*}"
    value="${line#*=}"

    # Skip local-only keys
    local skip_key=false
    for s in $skip; do
      [[ "$key" == "$s" ]] && skip_key=true && break
    done
    $skip_key && continue

    # Escape commas in values (gcloud uses comma as separator)
    value="${value//,/\\,}"
    vars="${vars:+$vars,}${key}=${value}"
  done < "$ENV_FILE"

  echo "$vars"
}

# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------
if $DEPLOY; then
  echo "==> Deploying $SERVICE to Cloud Run..."
  gcloud run deploy "$SERVICE" \
    --source "$(dirname "$0")/../backend" \
    --project "$PROJECT" \
    --region "$REGION" \
    --allow-unauthenticated \
    --platform managed \
    --quiet
  echo "==> Deploy complete."
fi

# ---------------------------------------------------------------------------
# Sync env vars
# ---------------------------------------------------------------------------
if $UPDATE_ENV; then
  echo "==> Reading env vars from $ENV_FILE..."
  ENV_VARS="$(build_env_vars)"

  if [[ -z "$ENV_VARS" ]]; then
    echo "    No env vars found — skipping."
  else
    echo "==> Updating Cloud Run env vars..."
    gcloud run services update "$SERVICE" \
      --project "$PROJECT" \
      --region "$REGION" \
      --set-env-vars "$ENV_VARS"
    echo "==> Env vars updated."
  fi
fi

echo ""
echo "Service URL: https://$(gcloud run services describe "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --format 'value(status.url)' | sed 's|https://||')"
