#!/data/data/com.termux/files/usr/bin/bash
set -e

cd "$(dirname "$0")"
echo "🛠️ Restoring Titan Nova runtime files if missing..."
python titan_runtime_files.py --ensure

echo "🚀 Starting Titan Nova WhatsApp Gateway..."
node Gateway.js
