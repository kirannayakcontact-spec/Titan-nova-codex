#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_DIR="${TITAN_APP_DIR:-$HOME/titan-app}"
BRANCH="${TITAN_BRANCH:-main}"
LOG_DIR="$APP_DIR/logs"
BACKEND_LOG="$LOG_DIR/backend.log"
GATEWAY_LOG="$LOG_DIR/gateway.log"

info(){ printf '\033[1;34m[TITAN]\033[0m %s\n' "$*"; }
fail(){ printf '\033[1;31m[TITAN ERROR]\033[0m %s\n' "$*"; exit 1; }

info "Starting clean Andres Berlin deploy"

if [ ! -d "$APP_DIR/.git" ]; then
  fail "Repo folder not found: $APP_DIR. Clone repo first, then run this script."
fi

cd "$APP_DIR"
mkdir -p "$LOG_DIR"

if [ -f "$HOME/.bashrc" ]; then
  set +u
  # shellcheck disable=SC1090
  source "$HOME/.bashrc" || true
  set -u
fi

export APP_TZ="${APP_TZ:-Asia/Kolkata}"
export GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:3000}"
export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-5000}"

info "Updating repo from origin/$BRANCH"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

info "Installing dependencies"
pip install -r requirements.txt
npm install

info "Running checks"
python -m compileall backend andres-berlin/backend
npm run check

info "Stopping old processes if running"
pkill -f "python -m backend.app" 2>/dev/null || true
pkill -f "node andres-berlin/bot/index.js" 2>/dev/null || true
sleep 1

info "Starting Flask backend"
(
  cd andres-berlin
  nohup python -m backend.app > "$BACKEND_LOG" 2>&1 &
  echo $! > "$LOG_DIR/backend.pid"
)

info "Starting WhatsApp gateway"
nohup npm start > "$GATEWAY_LOG" 2>&1 &
echo $! > "$LOG_DIR/gateway.pid"

sleep 2
BACKEND_PID="$(cat "$LOG_DIR/backend.pid")"
GATEWAY_PID="$(cat "$LOG_DIR/gateway.pid")"

if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
  tail -n 80 "$BACKEND_LOG" || true
  fail "Backend failed to start. Check $BACKEND_LOG"
fi
if ! kill -0 "$GATEWAY_PID" 2>/dev/null; then
  tail -n 80 "$GATEWAY_LOG" || true
  fail "Gateway failed to start. Check $GATEWAY_LOG"
fi

info "Deploy complete"
printf '\nBackend: http://127.0.0.1:%s\n' "$PORT"
printf 'Backend log: %s\n' "$BACKEND_LOG"
printf 'Gateway log: %s\n' "$GATEWAY_LOG"
printf '\nStop commands:\n'
printf '  kill $(cat %s/backend.pid) $(cat %s/gateway.pid)\n' "$LOG_DIR" "$LOG_DIR"
