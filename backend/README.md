# Backend Modules

This folder is the future home of the Flask backend modules.

Current runtime remains `flask_app.py`.

Planned modules:

- `app.py` — Flask app factory and route registration
- `config.py` — environment and runtime config
- `firebase_client.py` — Firebase access and cache helpers
- `security.py` — admin/gateway auth helpers
- `health.py` — health and diagnostics
- `routes/` — route groups
- `services/` — business logic
- `ui/` — UI fragments and embedded JS chunks
- `utils/` — shared helpers

Do not move runtime logic here until a focused migration phase is opened.
