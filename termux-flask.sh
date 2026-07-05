#!/data/data/com.termux/files/usr/bin/bash
set -e

cd "$(dirname "$0")"
echo "🚀 Starting Titan Nova Flask dashboard..."
echo "Open: http://127.0.0.1:5000"
python flask_app.py
