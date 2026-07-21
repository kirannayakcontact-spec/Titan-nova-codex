#!/data/data/com.termux/files/usr/bin/bash
set -e

cd "$(dirname "$0")"
echo "🛠️ Restoring Titan Nova runtime files if missing..."
python titan_runtime_files.py --ensure

# Keep the dashboard proxy wired to the canonical multi-session gateway,
# including when operators override the gateway port.
export GATEWAY_PORT="${GATEWAY_PORT:-3000}"
export GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:${GATEWAY_PORT}}"

echo "🚀 Starting Titan Nova Flask dashboard..."
echo "Open: http://127.0.0.1:5000"
python flask_app.py
