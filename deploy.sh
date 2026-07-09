#!/usr/bin/env bash
# Titan Nova Termux deploy helper
# Usage: bash deploy.sh

set -u

say() { printf '\n\033[1;32m%s\033[0m\n' "$1"; }
warn() { printf '\n\033[1;33m%s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31m%s\033[0m\n' "$1"; exit 1; }

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR" || fail "App folder open nahi hua: $APP_DIR"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-5000}"
GATEWAY_PORT="${GATEWAY_PORT:-3000}"

say "📦 Titan Nova deploy start"
echo "Folder: $APP_DIR"
echo "Host:   $HOST"
echo "Port:   $PORT"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "$2"
}

http_ok() {
  local url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 3 "$url" >/dev/null 2>&1
    return $?
  fi
  python - "$url" <<'PY' >/dev/null 2>&1
import sys, urllib.request
try:
    urllib.request.urlopen(sys.argv[1], timeout=3).read(1)
    raise SystemExit(0)
except Exception:
    raise SystemExit(1)
PY
}

wait_http() {
  local name="$1" url="$2" tries="${3:-25}"
  local i
  for i in $(seq 1 "$tries"); do
    if http_ok "$url"; then
      echo "✅ $name response OK: $url"
      return 0
    fi
    sleep 1
  done
  return 1
}

stop_old() {
  say "🛑 Old Flask/Gateway stop"
  pkill -TERM -f "python.*flask_app.py" 2>/dev/null || true
  pkill -TERM -f "python3.*flask_app.py" 2>/dev/null || true
  pkill -TERM -f "node.*Gateway.js" 2>/dev/null || true
  sleep 2
  pkill -KILL -f "python.*flask_app.py" 2>/dev/null || true
  pkill -KILL -f "python3.*flask_app.py" 2>/dev/null || true
  pkill -KILL -f "node.*Gateway.js" 2>/dev/null || true

  # Best effort port cleanup if Termux has fuser/lsof installed.
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" 2>/dev/null || true
    fuser -k "${GATEWAY_PORT}/tcp" 2>/dev/null || true
  elif command -v lsof >/dev/null 2>&1; then
    lsof -ti tcp:"$PORT" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
    lsof -ti tcp:"$GATEWAY_PORT" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
  fi
}

show_ports() {
  echo ""
  echo "--- Port check ---"
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | grep -E ":(${PORT}|${GATEWAY_PORT})\b" || true
  elif command -v netstat >/dev/null 2>&1; then
    netstat -ltnp 2>/dev/null | grep -E ":(${PORT}|${GATEWAY_PORT})\b" || true
  else
    echo "ss/netstat missing. Termux me: pkg install iproute2"
  fi
}

show_phone_ip() {
  local ip=""
  if command -v ip >/dev/null 2>&1; then
    ip="$(ip -4 addr show wlan0 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1 | head -n1)"
  fi
  echo ""
  echo "Dashboard same phone: http://127.0.0.1:${PORT}"
  if [ -n "$ip" ]; then
    echo "Dashboard other phone/PC same WiFi: http://${ip}:${PORT}"
  else
    echo "Other phone/PC ke liye IP: ip addr show wlan0 | grep 'inet '"
  fi
}

need_cmd python "Python missing hai. Termux me: pkg install python"
need_cmd npm "Node/npm missing hai. Termux me: pkg install nodejs"

if command -v git >/dev/null 2>&1; then
  say "⬇️ GitHub se latest update le raha hoon"
  git pull origin main || warn "⚠️ git pull fail hua. Local files se start continue kar raha hoon."
else
  warn "⚠️ git install nahi hai. Skip git pull. Termux me: pkg install git"
fi

if [ -f requirements.txt ]; then
  say "🐍 Python requirements check/install"
  python -m pip install -r requirements.txt || warn "⚠️ pip install fail hua. App start try kar raha hoon."
fi

if [ -f package.json ]; then
  say "🟢 Node packages check/install"
  npm install || warn "⚠️ npm install fail hua. Gateway start try kar raha hoon."
fi

stop_old

: > flask.log
: > gateway.log

say "🚀 Flask start: http://127.0.0.1:${PORT}"
PYTHONUNBUFFERED=1 HOST="$HOST" PORT="$PORT" nohup python flask_app.py > flask.log 2>&1 &
FLASK_PID=$!

say "🚀 Gateway start: http://127.0.0.1:${GATEWAY_PORT}"
GATEWAY_PORT="$GATEWAY_PORT" nohup node Gateway.js > gateway.log 2>&1 &
GATEWAY_PID=$!

if wait_http "Dashboard" "http://127.0.0.1:${PORT}" 25; then
  DASHBOARD_OK=1
else
  DASHBOARD_OK=0
fi

sleep 2

echo ""
echo "✅ Titan Nova start command complete"
echo "Flask PID:   $FLASK_PID"
echo "Gateway PID: $GATEWAY_PID"
show_phone_ip
show_ports

echo ""
echo "--- Flask log ---"
tail -n 40 flask.log 2>/dev/null || true

echo ""
echo "--- Gateway log ---"
tail -n 25 gateway.log 2>/dev/null || true

echo ""
echo "Logs dekhne ke liye:"
echo "  tail -f flask.log"
echo "  tail -f gateway.log"

if [ "$DASHBOARD_OK" != "1" ]; then
  echo ""
  fail "Dashboard port ${PORT} response nahi de raha. Upar Flask log ka last error bhejo."
fi
