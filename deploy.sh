#!/usr/bin/env bash
# Titan Nova Termux deploy helper
# Fast usage:
#   bash deploy.sh update    # git pull + fast restart
#   bash deploy.sh restart   # fast restart only
#   bash deploy.sh stop      # stop Flask/Gateway
# Heavy install/check:
#   bash deploy.sh install   # pip/npm install + restart
#   bash deploy.sh full      # install + full tests + restart

set -u

say() { printf '\n\033[1;32m%s\033[0m\n' "$1"; }
warn() { printf '\n\033[1;33m%s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31m%s\033[0m\n' "$1"; exit 1; }

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR" || fail "App folder open nahi hua: $APP_DIR"

MODE="${1:-restart}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-5000}"
GATEWAY_PORT="${GATEWAY_PORT:-3000}"

usage() {
  cat <<EOF
Titan Nova deploy commands:
  bash deploy.sh update    GitHub update + fast restart
  bash deploy.sh restart   Fast restart only
  bash deploy.sh stop      Stop Flask and Gateway
  bash deploy.sh status    Show running ports/processes
  bash deploy.sh install   Install Python/Node deps, then restart
  bash deploy.sh full      Install deps + full tests, then restart
EOF
}

say "📦 Titan Nova deploy: ${MODE}"
echo "Folder: $APP_DIR"
echo "Host:   $HOST"
echo "Port:   $PORT"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "$2"
}

http_ok() {
  local url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 4 "$url" >/dev/null 2>&1
    return $?
  fi
  python - "$url" <<'PY' >/dev/null 2>&1
import sys, urllib.request
try:
    urllib.request.urlopen(sys.argv[1], timeout=4).read(1)
    raise SystemExit(0)
except Exception:
    raise SystemExit(1)
PY
}

wait_http() {
  local name="$1" url="$2" tries="${3:-20}"
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
  pkill -TERM -f "node.*whatsapp_multi_session.js" 2>/dev/null || true
  pkill -TERM -f "node.*Gateway.js" 2>/dev/null || true
  sleep 1
  pkill -KILL -f "python.*flask_app.py" 2>/dev/null || true
  pkill -KILL -f "python3.*flask_app.py" 2>/dev/null || true
  pkill -KILL -f "node.*whatsapp_multi_session.js" 2>/dev/null || true
  pkill -KILL -f "node.*Gateway.js" 2>/dev/null || true

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
  echo "--- Process check ---"
  ps -ef 2>/dev/null | grep -E "flask_app.py|whatsapp_multi_session.js|Gateway.js" | grep -v grep || true
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

show_runtime_status() {
  echo ""
  echo "--- Runtime boot status ---"
  if command -v curl >/dev/null 2>&1; then
    curl -sS --max-time 8 "http://127.0.0.1:${PORT}/api/runtime_boot/status" 2>&1 || true
    echo ""
  else
    python - <<PY 2>&1 || true
import urllib.request
try:
    print(urllib.request.urlopen('http://127.0.0.1:${PORT}/api/runtime_boot/status', timeout=8).read().decode())
except Exception as e:
    print('runtime status error:', e)
PY
  fi
}

pull_latest() {
  if command -v git >/dev/null 2>&1; then
    say "⬇️ GitHub update"
    git pull origin main || fail "GitHub update fail hua. Old local code se start nahi kar raha. Pehle git error fix karo."
  else
    warn "⚠️ git install nahi hai. Termux me: pkg install git"
  fi
}

install_deps() {
  need_cmd python "Python missing hai. Termux me: pkg install python"
  need_cmd npm "Node/npm missing hai. Termux me: pkg install nodejs"
  if [ -f requirements.txt ]; then
    say "🐍 Python requirements install (heavy, sirf install/full mode me)"
    python -m pip install -r requirements.txt || warn "⚠️ pip install fail hua. App start try kar raha hoon."
  fi
  if [ -f package.json ]; then
    say "🟢 Node packages install (heavy, sirf install/full mode me)"
    npm install || warn "⚠️ npm install fail hua. Gateway start try kar raha hoon."
  fi
}

ensure_runtime_deps() {
  need_cmd python "Python missing hai. Termux me: pkg install python"
  need_cmd npm "Node/npm missing hai. Termux me: pkg install nodejs"

  if ! python - <<'PY' >/dev/null 2>&1
import importlib
for name in ('flask', 'requests', 'flask_limiter'):
    importlib.import_module(name)
PY
  then
    say "🐍 Missing Python runtime deps install (opencv skip)"
    python -m pip install 'flask>=3.0.0' 'requests>=2.31.0' 'Flask-Limiter>=3.8.0' 'redis>=5.0.0' 'rq>=2.0.0' || warn "⚠️ Python runtime deps install fail hua."
  fi

  if ! node - <<'NODE' >/dev/null 2>&1
for (const name of ['axios','express','pino','qrcode-terminal','@whiskeysockets/baileys']) require(name);
NODE
  then
    say "🟢 Missing Node runtime deps install"
    npm install axios express pino qrcode-terminal @whiskeysockets/baileys || warn "⚠️ Node runtime deps install fail hua."
  fi
}

fast_check() {
  need_cmd python "Python missing hai. Termux me: pkg install python"
  need_cmd node "Node missing hai. Termux me: pkg install nodejs"
  say "🧪 Complete production preflight"
  python scripts/single_source_audit.py --result-source-only || fail "Old result website reference mila; deploy blocked."
  python runtime_syntax_check.py || fail "Production runtime check fail."
}

full_check() {
  say "🧪 Full production check"
  fast_check
  npm run check || fail "Gateway JavaScript syntax check failed."
}

start_runtime() {
  stop_old
  : > flask.log
  : > gateway.log

  say "🚀 Flask start: http://127.0.0.1:${PORT}"
  PYTHONUNBUFFERED=1 HOST="$HOST" PORT="$PORT" GATEWAY_URL="http://127.0.0.1:${GATEWAY_PORT}" nohup python flask_app.py > flask.log 2>&1 &
  FLASK_PID=$!

  say "🚀 Gateway start: http://127.0.0.1:${GATEWAY_PORT}"
  GATEWAY_PORT="$GATEWAY_PORT" nohup node whatsapp_multi_session.js > gateway.log 2>&1 &
  GATEWAY_PID=$!

  if wait_http "Runtime boot status" "http://127.0.0.1:${PORT}/api/runtime_boot/status" 20; then
    DASHBOARD_OK=1
  elif wait_http "Dashboard" "http://127.0.0.1:${PORT}" 5; then
    DASHBOARD_OK=1
  else
    DASHBOARD_OK=0
  fi

  sleep 1
  if ! wait_http "Gateway health" "http://127.0.0.1:${GATEWAY_PORT}/api/health" 8; then
    warn "⚠️ Gateway /health response unavailable; inspect gateway.log."
  fi

  echo ""
  echo "✅ Titan Nova command complete"
  echo "Flask PID:   $FLASK_PID"
  echo "Gateway PID: $GATEWAY_PID"
  show_phone_ip
  show_ports
  show_runtime_status

  echo ""
  echo "--- Flask log ---"
  tail -n 30 flask.log 2>/dev/null || true

  echo ""
  echo "--- Gateway log ---"
  tail -n 20 gateway.log 2>/dev/null || true

  echo ""
  echo "Logs dekhne ke liye:"
  echo "  tail -f flask.log"
  echo "  tail -f gateway.log"

  if [ "$DASHBOARD_OK" != "1" ]; then
    echo ""
    fail "Flask runtime port ${PORT} response nahi de raha. Upar Flask log ka last error bhejo."
  fi
}

case "$MODE" in
  update|pull)
    pull_latest
    ensure_runtime_deps
    fast_check
    start_runtime
    ;;
  restart|start|run)
    ensure_runtime_deps
    fast_check
    start_runtime
    ;;
  stop)
    stop_old
    echo "✅ Titan Nova stopped"
    ;;
  status)
    show_ports
    show_phone_ip
    show_runtime_status
    ;;
  install)
    pull_latest
    install_deps
    fast_check
    start_runtime
    ;;
  full|deploy)
    pull_latest
    install_deps
    full_check
    start_runtime
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage
    fail "Unknown command: $MODE"
    ;;
esac
