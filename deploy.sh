#!/usr/bin/env bash
# Titan Nova Termux deploy helper
# Usage: bash deploy.sh

set -u

say() { printf '\n\033[1;32m%s\033[0m\n' "$1"; }
warn() { printf '\n\033[1;33m%s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31m%s\033[0m\n' "$1"; exit 1; }

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR" || fail "App folder open nahi hua: $APP_DIR"

say "📦 Titan Nova deploy start"
echo "Folder: $APP_DIR"

if command -v git >/dev/null 2>&1; then
  say "⬇️ GitHub se latest update le raha hoon"
  git pull origin main || warn "⚠️ git pull fail hua. Local files se start continue kar raha hoon."
else
  warn "⚠️ git install nahi hai. Skip git pull."
fi

if command -v python >/dev/null 2>&1; then
  if [ -f requirements.txt ]; then
    say "🐍 Python requirements check/install"
    python -m pip install -r requirements.txt || warn "⚠️ pip install fail hua. App start try kar raha hoon."
  fi
else
  fail "Python missing hai. Termux me: pkg install python"
fi

if command -v npm >/dev/null 2>&1; then
  if [ -f package.json ]; then
    say "🟢 Node packages check/install"
    npm install || warn "⚠️ npm install fail hua. Gateway start try kar raha hoon."
  fi
else
  fail "Node/npm missing hai. Termux me: pkg install nodejs"
fi

say "🛑 Old Flask/Gateway stop"
pkill -f "python .*flask_app.py" 2>/dev/null || true
pkill -f "node .*Gateway.js" 2>/dev/null || true
sleep 1

say "🚀 Flask start: http://127.0.0.1:5000"
nohup python flask_app.py > flask.log 2>&1 &
FLASK_PID=$!

say "🚀 Gateway start: http://127.0.0.1:3000"
nohup node Gateway.js > gateway.log 2>&1 &
GATEWAY_PID=$!

sleep 4

echo ""
echo "✅ Titan Nova started"
echo "Flask PID:   $FLASK_PID"
echo "Gateway PID: $GATEWAY_PID"
echo "Dashboard:  http://127.0.0.1:5000"
echo "Gateway:    http://127.0.0.1:3000"
echo ""
echo "--- Flask log ---"
tail -n 20 flask.log 2>/dev/null || true
echo ""
echo "--- Gateway log ---"
tail -n 20 gateway.log 2>/dev/null || true
echo ""
echo "Logs dekhne ke liye:"
echo "  tail -f flask.log"
echo "  tail -f gateway.log"
