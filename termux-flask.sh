#!/data/data/com.termux/files/usr/bin/bash
set -e

cd "$(dirname "$0")/andres-berlin"
echo "🚀 Starting Andres Berlin Flask backend..."
echo "Open: http://127.0.0.1:${PORT:-5000}"
python -m backend.app
