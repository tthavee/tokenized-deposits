#!/usr/bin/env bash
# Build the Flutter web app and deploy it to Firebase Hosting.
#
# Usage:
#   ./scripts/deploy-frontend.sh                        # build + deploy (uses /api proxy)
#   ./scripts/deploy-frontend.sh --api-url <url>        # override the backend URL
#   ./scripts/deploy-frontend.sh --build-only           # build without deploying
#   ./scripts/deploy-frontend.sh --deploy-only          # deploy without rebuilding

set -euo pipefail

PROJECT="tokenized-deposits"
REGION="us-central1"
SERVICE="tokenized-deposits-backend"
FRONTEND_DIR="$(dirname "$0")/../frontend"

# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------
BUILD=true
DEPLOY=true
API_URL=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --api-url)     API_URL="$2"; shift 2 ;;
    --build-only)  DEPLOY=false; shift ;;
    --deploy-only) BUILD=false; shift ;;
    *) shift ;;
  esac
done

# ---------------------------------------------------------------------------
# Build with /api as the base URL (proxied by Firebase Hosting)
# ---------------------------------------------------------------------------
if $BUILD; then
  if [[ -z "$API_URL" ]]; then
    # Use /api which is proxied to the backend by Firebase Hosting
    API_URL="/api"
    echo "==> Using /api (proxied by Firebase Hosting to Cloud Run backend)"
  fi

  echo "==> Building Flutter web with BASE_API_URL=$API_URL"
  (cd "$FRONTEND_DIR" && flutter build web \
    --dart-define="BASE_API_URL=${API_URL}")
  echo "==> Build complete."
fi

# ---------------------------------------------------------------------------
# Deploy to Firebase Hosting
# ---------------------------------------------------------------------------
if $DEPLOY; then
  echo "==> Deploying to Firebase Hosting..."
  firebase deploy --only hosting --project "$PROJECT"
  echo "==> Deploy complete."
  echo ""
  echo "Hosting URL: https://${PROJECT}.web.app"
fi
