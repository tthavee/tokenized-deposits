# Balance Loading Error Fix

## Problem

The dashboard was showing this error when loading balances:

```
Could not load balances: ClientException. Failed to fetch, uri=https://tokenized-deposits-backend-ndyhwdrkda-uc.a.run.app/clients/db2ec5c0-8aad-4593-b8d4-1992986a2323/balances
```

Then after initial fix, it showed:

```
Could not load balances: ApiException(404): Not Found
```

## Root Cause

The frontend was making direct HTTP requests to the Cloud Run backend URL instead of using the Firebase Hosting proxy. Firebase Hosting is configured to proxy `/api/**` requests to the backend (see `firebase.json`), but:

1. The frontend was bypassing this proxy and trying to reach the backend directly
2. The backend routes were not mounted under `/api` prefix, so even when proxied, the paths didn't match

## Solution

Updated both frontend and backend to use `/api` prefix consistently:

### Changes Made

1. **`frontend/lib/config/app_config.dart`**
   - Changed `baseApiUrl` from a compile-time constant to a runtime getter
   - Now returns `/api` for web builds (proxied by Firebase Hosting)
   - Returns `http://localhost:8000/api` for local development

2. **`backend/main.py`**
   - Added `/api` prefix when mounting all routers (clients, admin, transfer)
   - Added `/api/health` endpoint alongside existing `/health`

3. **`backend/tests/*.py`**
   - Updated all test URLs to include `/api` prefix
   - Changed `/clients/...` to `/api/clients/...`
   - Changed `/admin/...` to `/api/admin/...`
   - Changed `/transfer` to `/api/transfer`

4. **`scripts/deploy-frontend.sh`**
   - Updated to use `/api` instead of fetching the full Cloud Run URL
   - Removed the `gcloud run services describe` call

5. **`scripts/deploy.sh`**
   - Updated to use `/api` instead of fetching the full Cloud Run URL

## How to Deploy the Fix

### Deploy Backend

```bash
# Deploy the updated backend to Cloud Run
./scripts/deploy.sh --backend-only
```

### Deploy Frontend

```bash
# Build and deploy the updated frontend
./scripts/deploy-frontend.sh
```

### Or Deploy Everything

```bash
./scripts/deploy.sh
```

## How It Works

1. Frontend makes request to `/api/clients/{id}/balances`
2. Firebase Hosting receives the request
3. Firebase Hosting's rewrite rule (in `firebase.json`) proxies it to the Cloud Run backend
4. Backend receives the request at `/api/clients/{id}/balances` and processes it
5. Backend returns the response
6. Firebase Hosting forwards the response back to the frontend

This approach:
- Avoids CORS issues (same-origin requests)
- Simplifies configuration (no need to hardcode backend URLs)
- Works seamlessly with Firebase Hosting's built-in proxy feature
- Maintains consistency between local development and production

## Local Development

For local development, the backend now serves all routes under `/api`:
- Backend: `http://localhost:8000/api/...`
- Frontend: `http://localhost:8080`

The frontend automatically uses `http://localhost:8000/api` when running locally (non-web builds).

## Testing

After deployment, the dashboard should load balances without errors. The Token Balances section will show:
- Asset type, network, and balance for each token
- Error messages for any networks that are unreachable (e.g., "Hardhat node isn't running")

You can also test the backend directly:
```bash
# Production
curl https://tokenized-deposits.web.app/api/health

# Local
curl http://localhost:8000/api/health
```
