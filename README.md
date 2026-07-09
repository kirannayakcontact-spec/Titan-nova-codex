# Titan Nova Codex

Titan Nova legacy two-file runtime for Flask dashboard/API + WhatsApp Gateway.

## Active runtime

The active runtime uses the old two-file style:

```bash
python flask_app.py
node Gateway.js
```

The full previous runtime code is preserved under `legacy-backup/` and loaded by the root launchers:

```text
legacy-backup/flask_app.py.bak
legacy-backup/Gateway.js.bak
```

## Install

```bash
python -m pip install -r requirements.txt
npm install
```

## Check

```bash
python -m py_compile flask_app.py
node --check Gateway.js
npm run check
```

## Run in Termux manually

Terminal 1:

```bash
cd ~/Titan-nova-codex
python flask_app.py
```

Terminal 2:

```bash
cd ~/Titan-nova-codex
node Gateway.js
```

## Termux one-command update + deploy

Use this command when you want GitHub latest update + dependency install + both Flask and Gateway restart in one copy-paste.

```bash
bash -lc 'APP_DIR="$HOME/Titan-nova-codex"; [ -d "$APP_DIR" ] || APP_DIR="$HOME/titan-app"; cd "$APP_DIR" || exit 1; git pull origin main; python -m pip install -r requirements.txt; npm install; pkill -f "python .*flask_app.py" 2>/dev/null || true; pkill -f "node .*Gateway.js" 2>/dev/null || true; nohup python flask_app.py > flask.log 2>&1 & nohup node Gateway.js > gateway.log 2>&1 & sleep 3; echo "✅ Titan Nova started"; echo "📌 Dashboard: http://127.0.0.1:5000"; echo "📌 Gateway: http://127.0.0.1:3000"; echo "--- Flask log ---"; tail -n 15 flask.log; echo "--- Gateway log ---"; tail -n 15 gateway.log'
```

What this command does:

1. Opens `~/Titan-nova-codex`; if that folder is missing, opens `~/titan-app`.
2. Pulls latest code from GitHub `main`.
3. Installs Python packages from `requirements.txt`.
4. Installs Node packages from `package.json`.
5. Stops old Flask/Gateway processes.
6. Starts both in background.
7. Shows the last Flask and Gateway logs.

## Check if both are running

```bash
ps -ef | grep -E "flask_app.py|Gateway.js" | grep -v grep
```

## Open app

Flask dashboard/API:

```text
http://127.0.0.1:5000
```

Gateway health/server:

```text
http://127.0.0.1:3000
```

## View logs

Flask:

```bash
tail -f flask.log
```

Gateway:

```bash
tail -f gateway.log
```

## Stop both

```bash
pkill -f "python .*flask_app.py" 2>/dev/null || true; pkill -f "node .*Gateway.js" 2>/dev/null || true
```

## If folder not found

Clone first:

```bash
cd ~
git clone https://github.com/kirannayakcontact-spec/Titan-nova-codex.git
cd ~/Titan-nova-codex
```

Then run the one-command deploy again.

## Extra guide

Full Termux guide is also available in:

```text
TERMUX_DEPLOY.md
```
