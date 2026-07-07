# Andres Berlin

Clean modular starter repo for the next Titan Nova rebuild.

This folder is intentionally small and independent from the legacy monolith. Use
it as the fresh starting point for a new repository named **Andres Berlin**.

## Layout

```text
backend/
  app.py
  config.py
  security.py
  routes/
    admin.py
    wallet.py
    ledger.py
    payments.py
    withdrawals.py
    whatsapp.py
    markets.py
  services/
    firebase.py
    wallet_service.py
    ledger_service.py
    whatsapp_gateway.py
  ui/
    templates.py
bot/
  index.js
  gateway.js
  config.js
  firebase.js
  whatsapp.js
  scheduler.js
  result_scraper.js
  safety.js
  routes.js
```

## Run locally

Python API:

```bash
python -m backend.app
```

Node gateway:

```bash
node bot/index.js
```

## New repo setup

From this folder, start a separate Git repository when ready:

```bash
cd andres-berlin
git init
git add .
git commit -m "Start Andres Berlin clean modular repo"
```
