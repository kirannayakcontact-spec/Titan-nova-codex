#!/data/data/com.termux/files/usr/bin/bash
set -e

cd "$(dirname "$0")"
echo "🛠️ Restoring Titan Nova runtime files if missing..."
python titan_runtime_files.py --ensure

echo "🚀 Starting Titan Nova Flask dashboard..."
echo "Open: http://127.0.0.1:5000"
python flask_app.py
