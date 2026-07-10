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

say "1/9 Termux repositories update"
pkg update -y
pkg upgrade -y

say "2/9 Core tools install"
pkg install -y git python curl wget openssh nano jq iproute2 procps termux-tools

say "3/9 Node.js install"
if ! pkg install -y nodejs-lts; then
  warn "nodejs-lts available nahi; normal nodejs install kar raha hoon."
  pkg install -y nodejs
fi

say "4/9 Python/Pillow/OCR native libraries install"
pkg install -y clang make cmake pkg-config rust binutils libffi openssl \
  libjpeg-turbo libpng freetype littlecms libwebp tesseract

for optional_pkg in libtiff openjpeg; do
  if pkg install -y "$optional_pkg"; then
    echo "✅ Optional package installed: $optional_pkg"
  else
    warn "Optional package unavailable, skip: $optional_pkg"
  fi
done

say "5/9 Required project files verify"
for f in flask_app.py Gateway.js requirements.txt package.json deploy.sh; do
  [ -f "$f" ] || fail "Missing file: $f"
done
[ -f "legacy-backup/flask_app.py.bak" ] || fail "Missing legacy-backup/flask_app.py.bak"
[ -f "legacy-backup/Gateway.js.bak" ] || fail "Missing legacy-backup/Gateway.js.bak"

say "6/9 Python dependencies install"
python -m pip install --no-cache-dir setuptools wheel
python -m pip install --no-cache-dir -r requirements.txt

say "7/9 Baileys/Node dependencies install"
npm config set fund false >/dev/null 2>&1 || true
npm config set audit false >/dev/null 2>&1 || true
npm install
npm run check

say "8/9 Runtime syntax checks"
python -m py_compile flask_app.py legacy-backup/flask_app.py.bak
node --check Gateway.js
# Node 24 rejects unknown .bak extensions in --check mode. Runtime itself maps
# .bak to JavaScript in Gateway.js, so validate through a temporary .js copy.
LEGACY_GATEWAY_CHECK="${TMPDIR:-$PREFIX/tmp}/titan_legacy_gateway_check.js"
cp legacy-backup/Gateway.js.bak "$LEGACY_GATEWAY_CHECK"
node --check "$LEGACY_GATEWAY_CHECK"
rm -f "$LEGACY_GATEWAY_CHECK"

say "9/9 Permissions, shortcuts and first deploy"
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

sleep 2
if curl -fsS --max-time 8 http://127.0.0.1:5000/api/runtime_boot/status >/tmp/titan_runtime_status.json 2>/dev/null; then
  echo "✅ Flask runtime status:"
  cat /tmp/titan_runtime_status.json
  echo
else
  warn "Flask status check fail. Diagnose output:"
  bash termux_diagnose.sh || true
  fail "Dashboard start nahi hua. Upar Flask log dekho."
fi

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
