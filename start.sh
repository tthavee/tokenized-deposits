#!/usr/bin/env bash
# start.sh — starts all three project services in one command
#
# Usage:
#   ./start.sh           # start everything
#   ./start.sh --no-deploy  # start hardhat node + backend + frontend, skip contract deployment

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BLOCKCHAIN="$ROOT/blockchain"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

DEPLOY=true
for arg in "$@"; do
  [[ "$arg" == "--no-deploy" ]] && DEPLOY=false
done

# ── colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[start]${NC} $*"; }
warn() { echo -e "${YELLOW}[start]${NC} $*"; }
die()  { echo -e "${RED}[start] ERROR:${NC} $*" >&2; exit 1; }

# ── cleanup on exit ───────────────────────────────────────────────────────────
PIDS=()
cleanup() {
  log "Shutting down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ── 1. Hardhat node ───────────────────────────────────────────────────────────
log "Starting Hardhat local node..."
# Kill anything already holding port 8545 (e.g. a leftover from a previous run)
fuser -k 8545/tcp > /dev/null 2>&1 || true
cd "$BLOCKCHAIN"
npm run node > "$ROOT/logs/hardhat.log" 2>&1 &
HARDHAT_PID=$!
PIDS+=("$HARDHAT_PID")

# Wait for the node to be ready (it prints "Started HTTP and WebSocket JSON-RPC server")
log "Waiting for Hardhat node to be ready..."
for i in $(seq 1 30); do
  if grep -q "Started HTTP" "$ROOT/logs/hardhat.log" 2>/dev/null; then
    log "Hardhat node is up."
    break
  fi
  if grep -q "EADDRINUSE\|Error:" "$ROOT/logs/hardhat.log" 2>/dev/null; then
    die "Hardhat node failed to start. Check logs/hardhat.log"
  fi
  sleep 1
  if [[ $i -eq 30 ]]; then
    die "Hardhat node did not start in time. Check logs/hardhat.log"
  fi
done

# ── 2. Deploy contracts ───────────────────────────────────────────────────────
if $DEPLOY; then
  log "Deploying contracts to local network..."
  npm run deploy:local >> "$ROOT/logs/hardhat.log" 2>&1 \
    || die "Contract deployment failed. Check logs/hardhat.log"
  log "Contracts deployed."
fi

# ── 3. FastAPI backend ────────────────────────────────────────────────────────
log "Starting FastAPI backend..."
cd "$BACKEND"

if [[ ! -d venv ]]; then
  warn "No venv found — creating one and installing dependencies..."
  python3 -m venv venv
  venv/bin/pip install -q -r requirements.txt
fi

venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000 \
  > "$ROOT/logs/backend.log" 2>&1 &
BACKEND_PID=$!
PIDS+=("$BACKEND_PID")

# Wait for backend to bind
for i in $(seq 1 20); do
  if grep -q "Application startup complete" "$ROOT/logs/backend.log" 2>/dev/null; then
    log "Backend is up at http://localhost:8000"
    break
  fi
  sleep 1
  if [[ $i -eq 20 ]]; then
    warn "Backend may not be ready yet — check logs/backend.log"
    break
  fi
done

# ── 4. Flutter frontend ───────────────────────────────────────────────────────
FLUTTER_PORT=8080
log "Building Flutter web app..."
cd "$FRONTEND"
# flutter requires a TTY even for builds; use `script` to provide one
script -q -c 'flutter build web --no-wasm-dry-run' /dev/null \
  > "$ROOT/logs/frontend.log" 2>&1 \
  || die "Flutter build failed. Check logs/frontend.log"
log "Serving Flutter web app on port $FLUTTER_PORT..."
python3 -m http.server "$FLUTTER_PORT" --directory build/web \
  > /dev/null 2>&1 &
FRONTEND_PID=$!
PIDS+=("$FRONTEND_PID")

# ── done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}All services started.${NC}"
echo "  Hardhat node  → http://localhost:8545       (logs/hardhat.log)"
echo "  Backend API   → http://localhost:8000/docs  (logs/backend.log)"
echo "  Frontend      → http://localhost:$FLUTTER_PORT  (logs/frontend.log)"
echo ""
echo "Press Ctrl+C to stop everything."

# Keep the script alive so the trap fires on Ctrl+C
wait "${PIDS[@]}"
