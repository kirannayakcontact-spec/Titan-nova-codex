# Titan Nova Modular Architecture

## Current runtime

Titan Nova currently runs from two large compatibility entry files:

- `flask_app.py` — Flask admin dashboard and backend API
- `Gateway.js` — WhatsApp Gateway, scheduler, scraper, and sender runtime

These files must keep working while the app is split into modules.

## Target runtime

The final structure should keep small entry files and move logic into focused modules:

```text
titan-nova/
├── flask_app.py                  # compatibility entry
├── Gateway.js                    # compatibility entry
├── backend/
│   ├── app.py                    # Flask app factory / route registration
│   ├── config.py                 # env, tokens, URLs, timezone
│   ├── firebase_client.py         # Firebase get/put/patch/delete/cache
│   ├── security.py               # admin/gateway auth helpers
│   ├── health.py                 # health/config diagnostics
│   ├── routes/                   # Flask route groups
│   ├── services/                 # business logic
│   ├── ui/                       # embedded UI fragments and JS chunks
│   └── utils/                    # shared Python helpers
├── bot/
│   ├── index.js                  # Gateway module entry
│   ├── config.js                 # env and runtime config
│   ├── firebase.js               # Firebase access
│   ├── health.js                 # Gateway health response
│   ├── whatsapp/                 # WhatsApp connection, targets, sender, guard
│   ├── scheduler/                # schedule runners and idempotency
│   ├── results/                  # scraper/parser/result sender
│   └── utils/                    # shared JS helpers
├── scripts/                      # safe migration and smoke scripts
├── tests/                        # import/parser/schedule/path tests
└── docs/                         # deployment and update rules
```

## Migration principles

1. **No one-shot rewrite.** Move one stability area at a time.
2. **Keep compatibility entries.** `flask_app.py` and `Gateway.js` must remain runnable until final cutover.
3. **No behavior change during scaffold phases.** Folder creation and docs must not alter runtime behavior.
4. **Firebase paths are source-of-truth.** Do not rename paths without explicit migration.
5. **One module, one responsibility.** Ledger changes belong in ledger modules, Gateway health in health modules, result parsing in result modules.
6. **Smoke test after every phase.** Do not deploy if syntax or smoke checks fail.

## Recommended split order

### Phase 0 — scaffold only

Create folder structure and documentation. Do not change runtime behavior.

### Phase 1 — config and health extraction

Move environment parsing, token handling, gateway URL, Firebase URL, timezone, and health diagnostics into modules.

### Phase 2 — Firebase client extraction

Move Firebase load/save/cache/child-write helpers into a single backend Firebase client. This reduces save/revert bugs.

### Phase 3 — backend routes extraction

Split Flask route groups one by one: setup, ledger, wallet, payments, results, market, backup, WhatsApp.

### Phase 4 — UI extraction

Move embedded UI/JS sections into separate backend UI modules. Start with Setup and Health because they are stability screens.

### Phase 5 — Gateway extraction

Split Gateway config, Firebase, health, WhatsApp client, sender, guard, scheduler, and scraper modules.

### Phase 6 — tests

Add import tests, Firebase path tests, schedule rule tests, and result parser tests.

## Compatibility commands

These commands must keep working during all phases:

```bash
python flask_app.py
node Gateway.js
```

When smoke tooling exists, run before deploy:

```bash
python3 scripts/titan_smoke_test.py
node --check Gateway.js
python -m py_compile flask_app.py
```
