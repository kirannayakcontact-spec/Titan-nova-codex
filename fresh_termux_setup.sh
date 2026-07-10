#!/data/data/com.termux/files/usr/bin/bash
# Titan Nova complete fresh Termux setup
# Usage after clone: bash fresh_termux_setup.sh

set -Eeuo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

say(){ printf '\n\033[1;32m%s\033[0m\n' "$1"; }
warn(){ printf '\n\033[1;33m%s\033[0m\n' "$1"; }
fail(){ printf '\n\033[1;31m%s\033[0m\n' "$1"; exit 1; }

trap 'warn "Setup line $LINENO par fail hua. Upar ka exact error dekho."' ERR

if [ ! -d "/data/data/com.termux/files/usr" ]; then
  fail "Ye installer sirf official Termux environment ke liye hai."
fi

say "1/8 Termux repositories update"
pkg update -y
pkg upgrade -y

say "2/8 Core tools install"
pkg install -y git python curl wget openssh nano jq iproute2 procps termux-tools

say "3/8 Node.js install"
if ! pkg install -y nodejs-lts; then
  warn "nodejs-lts available nahi; normal nodejs install kar raha hoon."
  pkg install -y nodejs
fi

say "4/8 Python/Pillow/OCR native libraries install"
# Required build/runtime packages. These must succeed.
pkg install -y clang make cmake pkg-config rust binutils libffi openssl \
  libjpeg-turbo libpng freetype littlecms libwebp tesseract

# Optional image codecs have different names/availability across Termux mirrors.
# Missing optional codecs must not stop Titan Nova setup.
for optional_pkg in libtiff openjpeg; do
  if pkg install -y "$optional_pkg"; then
    echo "✅ Optional package installed: $optional_pkg"
  else
    warn "Optional package unavailable, skip: $optional_pkg"
  fi
done

say "5/8 Required project files verify"
for f in flask_app.py Gateway.js requirements.txt package.json deploy.sh; do
  [ -f "$f" ] || fail "Missing file: $f"
done
[ -f "legacy-backup/flask_app.py.bak" ] || fail "Missing legacy-backup/flask_app.py.bak"
[ -f "legacy-backup/Gateway.js.bak" ] || fail "Missing legacy-backup/Gateway.js.bak"

say "6/8 Python dependencies install"
python -m pip install --upgrade pip setuptools wheel
python -m pip install --no-cache-dir -r requirements.txt

say "7/8 Baileys/Node dependencies install"
npm config set fund false >/dev/null 2>&1 || true
npm config set audit false >/dev/null 2>&1 || true
npm install
npm run check

say "8/8 Permissions, shortcuts and first deploy"
chmod +x deploy.sh termux_diagnose.sh fresh_termux_setup.sh 2>/dev/null || true

BIN_DIR="$HOME/bin"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/titan" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
cd "$APP_DIR" || exit 1
bash deploy.sh
EOF
cat > "$BIN_DIR/titan-log" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
cd "$APP_DIR" || exit 1
tail -n 120 flask.log 2>/dev/null
echo
echo '--- Gateway ---'
tail -n 100 gateway.log 2>/dev/null
EOF
cat > "$BIN_DIR/titan-fix" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
cd "$APP_DIR" || exit 1
git pull origin main && bash fresh_termux_setup.sh
EOF
chmod +x "$BIN_DIR/titan" "$BIN_DIR/titan-log" "$BIN_DIR/titan-fix"

case ":$PATH:" in
  *":$HOME/bin:"*) ;;
  *)
    echo 'export PATH="$HOME/bin:$PATH"' >> "$HOME/.bashrc"
    export PATH="$HOME/bin:$PATH"
    ;;
esac

git config --global credential.helper store

echo
say "Installed versions"
python --version
node --version
npm --version
git --version
tesseract --version 2>/dev/null | head -n 1 || true

say "Titan Nova first start"
bash deploy.sh

echo
say "✅ Fresh Termux setup complete"
echo "Dashboard: http://127.0.0.1:5000"
echo "Gateway:   http://127.0.0.1:3000"
echo
echo "Next time start:  titan"
echo "Logs:             titan-log"
echo "Update + repair:  titan-fix"
echo
echo "WhatsApp QR gateway.log ya Termux output me dikhega."
