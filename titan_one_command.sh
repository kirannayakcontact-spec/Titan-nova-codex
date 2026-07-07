#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_DIR="${TITAN_APP_DIR:-$HOME/titan-app}"
BRANCH="${TITAN_BRANCH:-main}"
LOG_DIR="$APP_DIR/logs"
FLASK_LOG="$LOG_DIR/flask.log"
GATEWAY_LOG="$LOG_DIR/gateway.log"

info(){ printf '\033[1;34m[TITAN]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[TITAN WARNING]\033[0m %s\n' "$*"; }
fail(){ printf '\033[1;31m[TITAN ERROR]\033[0m %s\n' "$*"; exit 1; }

info "Titan Nova one-command deploy starting"

if [ ! -d "$APP_DIR/.git" ]; then
  fail "Repo folder not found: $APP_DIR. Clone repo first, then run this script."
fi

cd "$APP_DIR"
mkdir -p "$LOG_DIR"

info "Ensuring Titan runtime files"
python titan_runtime_files.py --ensure

# Load saved Termux env if present.
if [ -f "$HOME/.bashrc" ]; then
  # shellcheck disable=SC1090
  set +u
  source "$HOME/.bashrc" || true
  set -u
fi

if [ -z "${FIREBASE_URL:-}" ] && [ -z "${FIREBASE_DB_URL:-}" ]; then
  fail "FIREBASE_URL missing. Add it to ~/.bashrc first: export FIREBASE_URL=\"https://YOUR-PROJECT-default-rtdb.firebaseio.com/titan_master_data.json\""
fi

export APP_TZ="${APP_TZ:-Asia/Kolkata}"
export TITAN_BUSINESS_DAY_CUTOFF_HOUR="${TITAN_BUSINESS_DAY_CUTOFF_HOUR:-6}"
export GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:3000}"
export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-3000}"
export TITAN_WHATSAPP_UI="${TITAN_WHATSAPP_UI:-1}"

info "Updating repo from origin/$BRANCH"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

info "Installing Python dependencies"
pip install -r requirements.txt

info "Installing Node dependencies"
npm install

if [ "${TITAN_WHATSAPP_UI:-1}" = "1" ]; then
  info "Applying WhatsApp-style UI theme"
  python titan_whatsapp_ui_patch.py --apply
fi

info "Applying WhatsApp QR refresh fix"
python titan_wa_qr_fix_patch.py --apply

info "Applying Market Control Pro"
python titan_mcp_patch.py --apply

info "Applying VIP profile persistence fix"
python titan_profile_delete_guard_patch.py --apply
python titan_vip_profile_fix_patch.py --apply

info "Running preflight checks"
python -m py_compile flask_app.py
node --check Gateway.js
python titan_smoke_test.py
python titan_dead_code_audit.py || warn "Dead-code audit reported cleanup targets. Continuing because this is not a runtime failure."

if [ "${TITAN_APPLY_PHASE4_CLEANUP:-0}" = "1" ]; then
  info "Applying optional Phase 4 banner cleanup"
  python titan_phase4_banner_cleanup.py --apply
  python -m py_compile flask_app.py
  node --check Gateway.js
  python titan_smoke_test.py
fi

info "Stopping old Titan processes if running"
pkill -f "python flask_app.py" 2>/dev/null || true
pkill -f "node Gateway.js" 2>/dev/null || true
sleep 1

info "Starting Flask dashboard in background"
nohup python flask_app.py > "$FLASK_LOG" 2>&1 &
FLASK_PID=$!

info "Starting WhatsApp Gateway in background"
nohup node Gateway.js > "$GATEWAY_LOG" 2>&1 &
GATEWAY_PID=$!

sleep 2
if ! kill -0 "$FLASK_PID" 2>/dev/null; then
  tail -n 80 "$FLASK_LOG" || true
  fail "Flask failed to start. Check $FLASK_LOG"
fi
if ! kill -0 "$GATEWAY_PID" 2>/dev/null; then
  tail -n 80 "$GATEWAY_LOG" || true
  fail "Gateway failed to start. Check $GATEWAY_LOG"
fi

info "Deploy complete"
printf '\nDashboard: http://127.0.0.1:5000\n'
printf 'Market Control Pro: http://127.0.0.1:5000/market_control_pro\n'
printf 'Flask log:   %s\n' "$FLASK_LOG"
printf 'Gateway log: %s\n' "$GATEWAY_LOG"
printf '\nUseful commands:\n'
printf '  tail -f %s\n' "$FLASK_LOG"
printf '  tail -f %s\n' "$GATEWAY_LOG"
printf '  pkill -f "python flask_app.py"; pkill -f "node Gateway.js"\n'
