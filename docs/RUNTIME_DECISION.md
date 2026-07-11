# Runtime Decision

## Official production runtime

Titan Nova production currently uses the root legacy two-file runtime:

```bash
python flask_app.py
node Gateway.js
```

This is the only runtime that should be used for production deploys until a
separate migration checklist explicitly promotes a new modular runtime.

## Why this runtime is official

The root runtime is wired into the current deploy and check flow:

1. `flask_app.py` starts the Flask dashboard and API.
2. `Gateway.js` starts the WhatsApp Gateway.
3. `deploy.sh` installs dependencies, checks runtime references, starts both
   processes, and prints health/log output.
4. `package.json` Node scripts point to the root `Gateway.js` launcher.

## Current runtime flow

```text
Browser/Admin/VIP UI
  -> python flask_app.py
  -> legacy-backup/flask_app.py.bak
  -> Flask dashboard/API
  -> Firebase shared state

WhatsApp/automation
  -> node Gateway.js
  -> gateway safety/compatibility patches
  -> legacy-backup/Gateway.js.bak
  -> WhatsApp Gateway + schedules + notifications
  -> Firebase shared state
```

## Clean modular rebuild target

The `andres-berlin/` folder is a clean modular starter/rebuild target. It is not
the production runtime yet.

Use it as the professional migration direction after the current production flow
is documented, checked, and migrated safely.

## Rule before migration

Do not switch production from the root runtime to `andres-berlin/` until all of
these are complete:

1. Frontend dashboard loads successfully.
2. Flask API health and state endpoints are verified.
3. Gateway health and WhatsApp login endpoints are verified.
4. Payment, wallet, withdrawal, entry, result, and schedule flows are mapped.
5. Deploy scripts and README point to the same promoted runtime.
6. A rollback path to the root runtime exists.

## Safe next steps

1. Keep root runtime as official production.
2. Follow `docs/HEALTH_CHECK.md` before changing frontend, backend, Gateway, Firebase, or money-flow code.
3. Document active API contracts.
4. Clean configuration and security without changing business behavior.
5. Gradually move legacy code into normal modules only after each flow is tested.
