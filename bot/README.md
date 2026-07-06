# Bot Modules

This folder is the future home of the WhatsApp Gateway modules.

Current runtime remains `Gateway.js`.

Planned modules:

- `index.js` — module entrypoint
- `config.js` — environment and runtime config
- `firebase.js` — Firebase access
- `health.js` — Gateway health response
- `auth.js` — token helpers
- `whatsapp/` — connection, targets, sender, guard
- `scheduler/` — schedule runners and idempotency
- `results/` — parser and sender modules
- `utils/` — shared JS helpers

Do not move runtime logic here until a focused migration phase is opened.
