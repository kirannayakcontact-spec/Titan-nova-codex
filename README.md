# Titan Nova Codex

Production Termux runtime for the Titan Nova dashboard and five-session WhatsApp gateway.

## Install once

```bash
cd ~/github
python -m pip install -r requirements.txt
npm install
```

## Normal run

Open two Termux sessions.

### Session 1 — Flask dashboard

```bash
cd ~/github
HOST=0.0.0.0 PORT=5000 GATEWAY_URL=http://127.0.0.1:3000 python flask_app.py
```

### Session 2 — WhatsApp gateway

```bash
cd ~/github
GATEWAY_PORT=3000 node whatsapp_multi_session.js
```

Dashboard: http://127.0.0.1:5000

## Access mode

The local runtime is configured for **direct-open mode**. No `TITAN_ADMIN_TOKEN` or `TITAN_GATEWAY_TOKEN` is required. Keep Flask and gateway bound to `127.0.0.1` unless the private network is trusted; direct-open mode must not be exposed to the public internet without an external authentication layer.

## Update and restart

```bash
cd ~/github && bash deploy.sh update
```

## Production check

```bash
cd ~/github && python scripts/single_source_audit.py --result-source-only && python runtime_syntax_check.py && npm run check
```

## Runtime ownership

- `flask_app.py` — Flask launcher and production integrations.
- `titan_core.py` — dashboard, API and business logic core.
- `whatsapp_multi_session.js` — WhatsApp sessions, schedules and result automation.
- `deploy.sh` — update, dependency repair, checks and background restart.
- `termux.env.example` — direct-open local environment template and Firebase/WhatsApp settings.
- Result website is locked to `https://dpbosss.net.in/`.

Runtime data, WhatsApp auth, logs and generated cache files are intentionally not stored in Git.
