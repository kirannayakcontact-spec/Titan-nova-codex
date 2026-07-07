#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_DIR="${TITAN_APP_DIR:-$HOME/titan-app}"
BRANCH="${TITAN_BRANCH:-main}"
LOG_DIR="$APP_DIR/logs"
BACKEND_LOG="$LOG_DIR/backend.log"
GATEWAY_LOG="$LOG_DIR/gateway.log"

info(){ printf '\033[1;34m[TITAN]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[TITAN WARNING]\033[0m %s\n' "$*"; }
fail(){ printf '\033[1;31m[TITAN ERROR]\033[0m %s\n' "$*"; exit 1; }

stop_pid_file(){
  local pid_file="$1"
  if [ -s "$pid_file" ]; then
    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file"
  fi
}

stop_port(){
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" >/dev/null 2>&1 || true
  fi
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      kill $pids 2>/dev/null || true
      sleep 1
      kill -9 $pids 2>/dev/null || true
    fi
  fi
}

port_is_free(){
  python - "$1" <<'PYPORT'
import socket, sys
port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        raise SystemExit(1)
PYPORT
}

choose_free_port(){
  local start="$1"
  python - "$start" <<'PYPORT'
import socket, sys
start = int(sys.argv[1])
for port in range(start, start + 11):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            continue
        print(port)
        raise SystemExit(0)
raise SystemExit(1)
PYPORT
}

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
PORT_WAS_SET="${PORT+x}"
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
stop_pid_file "$LOG_DIR/backend.pid"
stop_pid_file "$LOG_DIR/gateway.pid"
pkill -f "python.*-m backend[.]app" 2>/dev/null || true
pkill -f "python.*flask_app[.]py" 2>/dev/null || true
pkill -f "node.*andres-berlin/bot/index[.]js" 2>/dev/null || true
stop_port "$PORT"
sleep 1

if ! port_is_free "$PORT"; then
  if [ -z "$PORT_WAS_SET" ]; then
    NEXT_PORT="$(choose_free_port "$PORT" || true)"
    if [ -n "$NEXT_PORT" ]; then
      warn "Port $PORT is busy, using free port $NEXT_PORT instead."
      export PORT="$NEXT_PORT"
    else
      fail "Port $PORT is busy and no free fallback port was found. Stop the old app or set PORT=5001."
    fi
  else
    fail "Port $PORT is busy. Stop the old app first, or rerun with a free port: PORT=5001 bash titan_one_command.sh"
  fi
fi

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
