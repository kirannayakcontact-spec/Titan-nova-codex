# Titan Nova Codex

Titan Nova legacy two-file runtime for Flask dashboard/API + WhatsApp Gateway.

## Active production runtime

The official production runtime currently uses the root legacy two-file style:

```bash
python flask_app.py
node whatsapp_multi_session.js
```

Keep this as the production runtime until a documented migration explicitly promotes a new modular runtime. The full previous runtime code is preserved under `legacy-backup/` and loaded by the root launchers:

```text
legacy-backup/flask_app.py.bak
legacy-backup/Gateway.js.bak
```

`flask_app.py` always serves the working classic dashboard from
`legacy-backup/flask_app.py.bak`. The incomplete modular scaffold and its unused
admin UI were removed so they cannot be started accidentally or add maintenance
and deployment weight.

## Install

```bash
python -m pip install -r requirements.txt
npm install
```

## Check

```bash
python -m py_compile flask_app.py
node --check whatsapp_multi_session.js
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
node whatsapp_multi_session.js
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

## Fast PWA and offline reads

The active classic dashboard installs `titan_pwa_fast_patch.py` automatically.
Successful `/api/state` and `/api/market_registry` reads are kept in IndexedDB
for up to 24 hours and are used when the network is unavailable or slow. Static
PWA assets are cached by the service worker.

For data safety, POST/PUT/PATCH/DELETE requests are never cached, queued, or
replayed in the browser. A financial or settings change is only successful after
the Flask/Firebase request responds successfully.

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
pkill -f "python .*flask_app.py" 2>/dev/null || true; pkill -f "node .*whatsapp_multi_session.js" 2>/dev/null || true
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
