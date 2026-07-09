# Titan Nova Termux Deploy

Use this file when you want one copy-paste command from GitHub to Termux.

## Folder name

Use the folder where your repo is cloned. Most common:

```bash
cd ~/Titan-nova-codex
```

If your folder is `~/titan-app`, use that instead.

## One command: update + restart both Flask and Gateway

Copy-paste this full command in Termux:

```bash
bash -lc 'APP_DIR="$HOME/Titan-nova-codex"; [ -d "$APP_DIR" ] || APP_DIR="$HOME/titan-app"; cd "$APP_DIR" || exit 1; git pull origin main; python -m pip install -r requirements.txt; npm install; pkill -f "python .*flask_app.py" 2>/dev/null || true; pkill -f "node .*Gateway.js" 2>/dev/null || true; nohup python flask_app.py > flask.log 2>&1 & nohup node Gateway.js > gateway.log 2>&1 & sleep 3; echo "✅ Titan Nova started"; echo "📌 Dashboard: http://127.0.0.1:5000"; echo "📌 Gateway: http://127.0.0.1:3000"; echo "--- Flask log ---"; tail -n 15 flask.log; echo "--- Gateway log ---"; tail -n 15 gateway.log'
```

This command does all of this:

1. Opens `~/Titan-nova-codex`; if not found, opens `~/titan-app`.
2. Pulls latest code from GitHub.
3. Installs Python requirements.
4. Installs Node packages.
5. Stops old Flask/Gateway processes.
6. Starts both in background.
7. Shows last logs.

## Check if both are running

```bash
ps -ef | grep -E "flask_app.py|Gateway.js" | grep -v grep
```

## View logs

```bash
tail -f flask.log
```

```bash
tail -f gateway.log
```

## Stop both

```bash
pkill -f "python .*flask_app.py" 2>/dev/null || true; pkill -f "node .*Gateway.js" 2>/dev/null || true
```

## Manual two-terminal run

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

## If command says folder not found

Clone first:

```bash
cd ~
git clone https://github.com/kirannayakcontact-spec/Titan-nova-codex.git
cd ~/Titan-nova-codex
```

Then run the one-command deploy again.
