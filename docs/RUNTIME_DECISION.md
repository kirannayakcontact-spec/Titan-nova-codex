# Runtime Decision

## Official production runtime

Titan Nova production currently uses the root legacy two-file runtime:

```bash
python flask_app.py
node whatsapp_multi_session.js
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
  -> node whatsapp_multi_session.js
  -> gateway safety/compatibility patches
  -> legacy-backup/Gateway.js.bak
  -> WhatsApp Gateway + schedules + notifications
  -> Firebase shared state
```

## Removed experimental runtime

The incomplete modular scaffold and its alternate admin UI were not used by the
production launchers and have been removed. This prevents an unsupported API/UI
from being started accidentally. A future migration must be developed on a
separate branch and must pass the full health checklist before it can replace
the production runtime.

## Safe next steps

1. Keep root runtime as official production.
2. Follow `docs/HEALTH_CHECK.md` before changing frontend, backend, Gateway, Firebase, or money-flow code.
3. Document active API contracts.
4. Clean configuration and security without changing business behavior.
5. Move legacy code only as part of a tested, documented migration.
