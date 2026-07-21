#!/data/data/com.termux/files/usr/bin/bash
# Titan Nova Termux Control
# Usage:
#   bash titanctl.sh update
#   bash titanctl.sh start
#   bash titanctl.sh stop
#   bash titanctl.sh restart
#   bash titanctl.sh status
#   bash titanctl.sh logs
#   bash titanctl.sh install

set -u

APP_DIR="${TITAN_APP_DIR:-$HOME/Titan-nova-codex}"
PID_DIR="$APP_DIR/.pids"
LOG_DIR="$APP_DIR/logs"
FLASK_PID="$PID_DIR/flask.pid"
GATEWAY_PID="$PID_DIR/gateway.pid"
FLASK_LOG="$LOG_DIR/flask.log"
GATEWAY_LOG="$LOG_DIR/gateway.log"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-5000}"
GATEWAY_PORT="${GATEWAY_PORT:-3000}"

ok(){ printf '\033[1;32m%s\033[0m\n' "$*"; }
warn(){ printf '\033[1;33m%s\033[0m\n' "$*"; }
err(){ printf '\033[1;31m%s\033[0m\n' "$*"; }
info(){ printf '\033[1;36m%s\033[0m\n' "$*"; }

ensure_dirs(){
  mkdir -p "$PID_DIR" "$LOG_DIR" "$HOME/bin"
}

cd_app(){
  if [ ! -d "$APP_DIR" ]; then
    err "App folder nahi mila: $APP_DIR"
    echo "Pehle repo clone karo ya TITAN_APP_DIR set karo."
    exit 1
  fi
  cd "$APP_DIR" || exit 1
}

is_running(){
  local pid_file="$1"
  [ -f "$pid_file" ] || return 1
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null
}

stop_one(){
  local name="$1"
  local pid_file="$2"
  if is_running "$pid_file"; then
    local pid
    pid="$(cat "$pid_file")"
    warn "Stopping $name PID $pid ..."
    kill "$pid" 2>/dev/null || true
    sleep 2
    if kill -0 "$pid" 2>/dev/null; then
      warn "$name force stop ..."
      kill -9 "$pid" 2>/dev/null || true
    fi
  fi
  rm -f "$pid_file"
}

install_deps(){
  cd_app
  ensure_dirs
  info "Installing/updating dependencies..."
  if command -v pkg >/dev/null 2>&1; then
    pkg install -y git python nodejs >/dev/null 2>&1 || true
  fi
  python -m pip install --upgrade pip >/dev/null 2>&1 || true
  if [ -f requirements.txt ]; then
    pip install -r requirements.txt
  else
    pip install flask requests
  fi
  if [ -f package.json ]; then
    npm install
  else
    npm install express axios qrcode-terminal pino @whiskeysockets/baileys
  fi
}

update_app(){
  cd_app
  ensure_dirs
  info "Updating Titan Nova from Git..."
  git pull
  install_deps
  info "Syntax check..."
  python -m py_compile flask_app.py deposit_professional_v2.py deposit_finance_native.py deposit_screenshot_routes.py
  if [ -f whatsapp_multi_session.js ]; then node --check whatsapp_multi_session.js; fi
  ok "Update complete."
}

start_app(){
  cd_app
  ensure_dirs
  if is_running "$FLASK_PID"; then
    warn "Flask already running PID $(cat "$FLASK_PID")"
  else
    info "Starting Flask dashboard/API on port $PORT ..."
    : > "$FLASK_LOG"
    nohup env HOST="$HOST" PORT="$PORT" python flask_app.py >> "$FLASK_LOG" 2>&1 &
    echo $! > "$FLASK_PID"
    sleep 1
    if is_running "$FLASK_PID"; then ok "Flask started PID $(cat "$FLASK_PID")"; else err "Flask start failed. Run: bash titanctl.sh logs"; fi
  fi

  if [ -f whatsapp_multi_session.js ]; then
    if is_running "$GATEWAY_PID"; then
      warn "Gateway already running PID $(cat "$GATEWAY_PID")"
    else
      info "Starting WhatsApp Gateway on port $GATEWAY_PORT ..."
      : > "$GATEWAY_LOG"
      nohup env GATEWAY_PORT="$GATEWAY_PORT" node whatsapp_multi_session.js >> "$GATEWAY_LOG" 2>&1 &
      echo $! > "$GATEWAY_PID"
      sleep 1
      if is_running "$GATEWAY_PID"; then ok "Gateway started PID $(cat "$GATEWAY_PID")"; else err "Gateway start failed. Run: bash titanctl.sh logs"; fi
    fi
  else
    warn "whatsapp_multi_session.js nahi mila, sirf Flask start hua."
  fi

  echo
  ok "Open dashboard: http://127.0.0.1:$PORT"
  echo "QR/log dekhne ke liye: titan logs"
}

stop_app(){
  cd_app
  ensure_dirs
  stop_one "Flask" "$FLASK_PID"
  stop_one "Gateway" "$GATEWAY_PID"
  ok "Titan Nova stopped."
}

status_app(){
  cd_app
  ensure_dirs
  echo "Titan Nova status"
  echo "App dir: $APP_DIR"
  if is_running "$FLASK_PID"; then ok "Flask: RUNNING PID $(cat "$FLASK_PID")  http://127.0.0.1:$PORT"; else warn "Flask: STOPPED"; fi
  if is_running "$GATEWAY_PID"; then ok "Gateway: RUNNING PID $(cat "$GATEWAY_PID")"; else warn "Gateway: STOPPED"; fi
}

logs_app(){
  cd_app
  ensure_dirs
  echo "Showing Flask + Gateway logs. Press CTRL+C to exit."
  touch "$FLASK_LOG" "$GATEWAY_LOG"
  tail -n 80 -f "$FLASK_LOG" "$GATEWAY_LOG"
}

install_command(){
  cd_app
  ensure_dirs
  chmod +x "$APP_DIR/titanctl.sh"
  cat > "$HOME/bin/titan" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
cd "$APP_DIR" || exit 1
bash "$APP_DIR/titanctl.sh" "\$@"
EOF
  chmod +x "$HOME/bin/titan"
  if ! echo "$PATH" | grep -q "$HOME/bin"; then
    echo 'export PATH="$HOME/bin:$PATH"' >> "$HOME/.bashrc"
  fi
  ok "Command installed: titan"
  echo "Ab use karo: titan update | titan start | titan stop | titan restart | titan status | titan logs"
}

case "${1:-help}" in
  install) install_command ;;
  update) update_app ;;
  start) start_app ;;
  stop) stop_app ;;
  restart) stop_app; update_app; start_app ;;
  status) status_app ;;
  logs) logs_app ;;
  deploy) update_app; stop_app; start_app ;;
  help|--help|-h|*)
    echo "Titan Nova Termux Control"
    echo "Commands:"
    echo "  bash titanctl.sh install   # installs titan shortcut"
    echo "  titan update               # git pull + deps + checks"
    echo "  titan start                # start Flask + Gateway"
    echo "  titan stop                 # stop both"
    echo "  titan restart              # stop + update + start"
    echo "  titan deploy               # update + stop + start"
    echo "  titan status               # process status"
    echo "  titan logs                 # live logs / QR"
    ;;
esac
