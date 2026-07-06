# Titan Nova Architecture

Titan Nova is organized around two runtime entrypoints:

- `flask_app.py` starts the Flask admin/API dashboard.
- `Gateway.js` starts the Node.js WhatsApp Gateway.

The package directories provide stable homes for incremental modularization:

- `backend/` for Flask configuration, security, Firebase access, routes, services, UI helpers, and utilities.
- `bot/` for WhatsApp Gateway configuration, Firebase helpers, scheduler logic, result processing, WhatsApp code, and utilities.
- `scripts/` for operational scripts.
- `tests/` for automated checks.
- `docs/` for project documentation.
