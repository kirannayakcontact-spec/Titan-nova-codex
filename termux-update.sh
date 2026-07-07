#!/data/data/com.termux/files/usr/bin/bash
set -e

cd "$(dirname "$0")"
echo "🔄 Pulling latest update..."
git pull

echo "🐍 Installing Python requirements..."
pip install -r requirements.txt

echo "📦 Installing Node packages..."
npm install

echo "✅ Update complete."
echo "Run backend: bash termux-flask.sh"
echo "Run gateway: npm start"
