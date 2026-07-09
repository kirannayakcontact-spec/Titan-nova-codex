#!/usr/bin/env bash
# Titan Nova Termux diagnose helper
# Usage: bash termux_diagnose.sh

set -u

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR" || exit 1

PORT="${PORT:-5000}"
GATEWAY_PORT="${GATEWAY_PORT:-3000}"

echo "=============================="
echo "Titan Nova Termux Diagnose"
echo "=============================="
echo "Date:   $(date 2>/dev/null || true)"
echo "Folder: $APP_DIR"
echo "User:   $(whoami 2>/dev/null || true)"
echo "Shell:  ${SHELL:-unknown}"
echo ""

echo "--- Versions ---"
python --version 2>&1 || true
node --version 2>&1 || true
npm --version 2>&1 || true
git --version 2>&1 || true

echo ""
echo "--- Git latest ---"
git log --oneline -5 2>/dev/null || true

echo ""
echo "--- Files ---"
ls -la flask_app.py Gateway.js deploy.sh requirements.txt package.json 2>/dev/null || true
ls -la flask.log gateway.log 2>/dev/null || true

echo ""
echo "--- Running processes ---"
ps -ef 2>/dev/null | grep -E "flask_app.py|Gateway.js" | grep -v grep || true

echo ""
echo "--- Listening ports ---"
if command -v ss >/dev/null 2>&1; then
  ss -ltnp 2>/dev/null | grep -E ":(${PORT}|${GATEWAY_PORT})\b" || true
elif command -v netstat >/dev/null 2>&1; then
  netstat -ltnp 2>/dev/null | grep -E ":(${PORT}|${GATEWAY_PORT})\b" || true
else
  echo "ss/netstat missing. Termux me: pkg install iproute2"
fi

echo ""
echo "--- HTTP check ---"
if command -v curl >/dev/null 2>&1; then
  echo "Dashboard headers:"
  curl -I --max-time 8 "http://127.0.0.1:${PORT}" 2>&1 || true
  echo ""
  echo "Gateway headers:"
  curl -I --max-time 8 "http://127.0.0.1:${GATEWAY_PORT}" 2>&1 || true
else
  python - <<PY 2>&1 || true
import urllib.request
for name, url in [('Dashboard', 'http://127.0.0.1:${PORT}'), ('Gateway', 'http://127.0.0.1:${GATEWAY_PORT}')]:
    try:
        r = urllib.request.urlopen(url, timeout=8)
        print(name, 'OK', r.status)
    except Exception as e:
        print(name, 'ERROR', e)
PY
fi

echo ""
echo "--- Phone IP ---"
if command -v ip >/dev/null 2>&1; then
  ip -4 addr show wlan0 2>/dev/null | grep "inet " || true
else
  echo "ip command missing. Termux me: pkg install iproute2"
fi

echo ""
echo "--- Flask log last 120 ---"
tail -n 120 flask.log 2>/dev/null || echo "flask.log missing"

echo ""
echo "--- Gateway log last 80 ---"
tail -n 80 gateway.log 2>/dev/null || echo "gateway.log missing"

echo ""
echo "Done. Is full output ko ChatGPT me bhejo."
