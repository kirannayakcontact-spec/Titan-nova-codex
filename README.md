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
`legacy-backup/flask_app.py.bak`.

## One-Time Shortcut Install

For Termux folder `~/github`, install the short command once:

```bash
cd ~/github && git checkout -- titanctl.sh 2>/dev/null || true; git pull origin main && bash titanctl.sh install
```

After that, use only these short commands:

```bash
github update
github restart
github stop
github status
```

`github update` backs up/restores `titanctl.sh` before pulling, then runs the fast deploy path.

## Fast Termux Commands Without Shortcut

Use these after the first install. They skip heavy `pip install`, `npm install`, `pytest`, and `jest`, so phone deploy is much faster.

Update + restart:

```bash
cd ~/github && git pull origin main && bash deploy.sh update
```

Restart only:

```bash
cd ~/github && bash deploy.sh restart
```

Stop:

```bash
cd ~/github && bash deploy.sh stop
```

Status:

```bash
cd ~/github && bash deploy.sh status
```

## First Time Folder `github`

If the folder does not exist, create it once:

```bash
cd ~ && git clone https://github.com/kirannayakcontact-spec/Titan-nova-codex.git github && cd ~/github && bash deploy.sh install && bash titanctl.sh install
```

After that, use only the short commands above.

## Heavy Install

Heavy install is only needed first time or when dependencies change:

```bash
bash deploy.sh install
```

Full heavy check:

```bash
bash deploy.sh full
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

## Run in Termux manually

Terminal 1:

```bash
cd ~/github
python flask_app.py
```

Terminal 2:

```bash
cd ~/github
node whatsapp_multi_session.js
```

## Check if both are running

```bash
ps -ef | grep -E "flask_app.py|whatsapp_multi_session.js|Gateway.js" | grep -v grep
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
github stop
```

## Extra guide

Full Termux guide is also available in:

```text
TERMUX_DEPLOY.md
```