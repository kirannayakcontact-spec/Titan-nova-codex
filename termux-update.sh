#!/data/data/com.termux/files/usr/bin/bash
set -e

echo "🔄 Titan Nova: pulling latest GitHub update..."
cd "$(dirname "$0")"
git pull

echo "🐍 Installing Python requirements..."
pip install -r requirements.txt

echo "📦 Installing Node packages..."
npm install

echo "✅ Update complete."
echo "Run Flask:   bash termux-flask.sh"
echo "Run Gateway: bash termux-gateway.sh"
