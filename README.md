# Titan Nova Codex

Titan Nova legacy two-file runtime for Flask dashboard/API + WhatsApp Gateway.

## Active production runtime

The official production runtime currently uses the root legacy two-file style:

```bash
python flask_app.py
node Gateway.js
```

Keep this as the production runtime until a documented migration explicitly promotes a new modular runtime. The full previous runtime code is preserved under `legacy-backup/` and loaded by the root launchers:

```text
legacy-backup/flask_app.py.bak
legacy-backup/Gateway.js.bak
```

The clean `andres-berlin/` folder is a future modular rebuild target, not the active production runtime yet. See `docs/RUNTIME_DECISION.md` before changing runtime ownership.

By default, `flask_app.py` opens the classic legacy dashboard from `legacy-backup/flask_app.py.bak` so the old app UI stays active. If you need the newer mobile admin overlay for testing, start Flask with `TITAN_CLASSIC_APP=0 python flask_app.py`.

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

## Full health check

Before changing frontend, backend, Gateway, Firebase, or money-flow code, follow:

```text
docs/HEALTH_CHECK.md
```

This checklist verifies the dashboard, Flask API, Gateway, Firebase readiness, and deploy flow before professional cleanup work starts.

## Easiest Termux deploy

First time or after new GitHub update, run only this small command:

```bash
cd ~/Titan-nova-codex && git pull origin main && bash deploy.sh
```

If your folder name is `titan-app`, use this:

```bash
cd ~/titan-app && git pull origin main && bash deploy.sh
```

After this, future deploy is even shorter:

```bash
bash deploy.sh
```

`deploy.sh` does all work automatically:

1. Pulls latest GitHub code.
2. Installs Python requirements.
3. Installs Node packages.
4. Stops old Flask/Gateway.
5. Starts both Flask and Gateway in background.
6. Shows logs.

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

Then run:

```bash
bash deploy.sh
```

## Extra guide

Full Termux guide is also available in:

```text
TERMUX_DEPLOY.md
```
