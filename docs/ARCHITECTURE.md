# Titan Nova Architecture

Titan Nova is organized around two runtime entrypoints:

- `flask_app.py` starts the Flask admin/API dashboard.
- `Gateway.js` starts the Node.js WhatsApp Gateway.

The package directories provide stable homes for incremental modularization:

- `backend/` for Flask configuration, security, Firebase access, routes, services, UI helpers, and utilities.
- `bot/` for WhatsApp Gateway modules. Multi-session bot features are split by responsibility: `session_config.js` owns roles/event routes, `message_utils.js` owns message/JID parsing, `role_access.js` owns restricted-role sender checks, `session_routes.js` owns bot API routes, and `session_manager.js` owns socket lifecycle orchestration.
- `scripts/` for operational scripts.
- `tests/` for automated checks.
- `docs/` for project documentation.
