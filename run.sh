#!/usr/bin/env bash
#
# Pulse — one-command dev setup + run.
#
#   ./run.sh              install deps (first run) and start backend + frontend
#   ./run.sh --setup-only just install deps, don't start
#   ./run.sh --backend    start only the backend
#   ./run.sh --frontend   start only the frontend
#
set -euo pipefail
cd "$(dirname "$0")"

BACKEND_PORT="${PULSE_BACKEND_PORT:-8787}"
FRONTEND_PORT="${PULSE_FRONTEND_PORT:-3030}"

c_blue='\033[34m'; c_green='\033[32m'; c_yellow='\033[33m'; c_dim='\033[2m'; c_reset='\033[0m'
say() { printf "${c_blue}▸${c_reset} %s\n" "$1"; }
ok()  { printf "${c_green}✓${c_reset} %s\n" "$1"; }
warn(){ printf "${c_yellow}!${c_reset} %s\n" "$1"; }

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    warn "missing '$1'. $2"
    exit 1
  fi
}

setup() {
  need uv "Install: https://github.com/astral-sh/uv"
  need node "Install Node 20+ : https://nodejs.org"

  say "Installing backend deps (uv sync)…"
  uv sync >/dev/null
  ok "backend deps ready"

  if [ ! -f .env ]; then
    cp .env.example .env
    warn "created .env — add your OPENADAPTER_API_KEY (or edit config.yaml for another provider)"
  fi

  say "Installing frontend deps (npm install)…"
  ( cd web && npm install --silent )
  ok "frontend deps ready"
}

start_backend() {
  say "Starting backend on :${BACKEND_PORT}  ${c_dim}(uv run pulse)${c_reset}"
  PULSE_PORT="$BACKEND_PORT" uv run pulse &
  BACKEND_PID=$!
}

start_frontend() {
  say "Starting frontend on :${FRONTEND_PORT}  ${c_dim}(next dev)${c_reset}"
  ( cd web && PORT="$FRONTEND_PORT" npm run dev ) &
  FRONTEND_PID=$!
}

cleanup() {
  echo
  say "shutting down…"
  [ -n "${BACKEND_PID:-}" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "${FRONTEND_PID:-}" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}

case "${1:-}" in
  --setup-only)
    setup
    ok "setup complete. run ./run.sh to start."
    exit 0
    ;;
  --backend)
    setup; trap cleanup EXIT INT TERM
    start_backend; wait
    ;;
  --frontend)
    setup; trap cleanup EXIT INT TERM
    start_frontend; wait
    ;;
  *)
    setup
    trap cleanup EXIT INT TERM
    start_backend
    start_frontend
    echo
    ok "Pulse is up:"
    printf "   ${c_dim}backend ${c_reset} http://127.0.0.1:%s\n" "$BACKEND_PORT"
    printf "   ${c_dim}frontend${c_reset} http://localhost:%s\n" "$FRONTEND_PORT"
    printf "   ${c_dim}Ctrl-C to stop both.${c_reset}\n\n"
    wait
    ;;
esac
