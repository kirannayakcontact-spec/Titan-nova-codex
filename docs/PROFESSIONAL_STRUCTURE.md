# Titan Nova Professional Structure

This is the safe professional structure for the current Titan Nova codebase.

## Current migration mode

The app still has two production runtime files at the repository root:

```text
flask_app.py
Gateway.js
```

Do not delete these until the split runtime is fully tested. The new folders are wrappers and future homes for refactored modules.

## Folder tree

```text
titan-nova/
├── backend/
│   ├── app.py
│   └── requirements.txt
├── gateway/
│   ├── Gateway.js
│   └── package.json
├── scripts/
│   └── README.md
├── deploy/
│   └── README.md
├── docs/
│   └── PROFESSIONAL_STRUCTURE.md
├── tests/
│   └── README.md
├── logs/                  # local only, ignored by git
├── backups/               # local only, ignored by git
├── auth_info_baileys/      # local WhatsApp session, never commit
├── flask_app.py            # current production Flask runtime
├── Gateway.js              # current production WhatsApp runtime
├── requirements.txt
├── package.json
└── titan_one_command.sh
```

## Why old files are not deleted yet

`flask_app.py` and `Gateway.js` are very large runtime files with embedded UI, routes, Firebase logic, and WhatsApp logic. Deleting them before the split is complete will break:

- dashboard
- Firebase save/load
- VIP tabs
- wallet and payments
- WhatsApp Gateway
- QR login
- market/result automation
- Termux one-command deploy

## Safe migration phases

### Phase 1 — Scaffold

Add professional folders and wrapper entrypoints. Keep old root runtime untouched.

### Phase 2 — Extract backend modules

Move small, stable backend pieces into:

```text
backend/routes/
backend/services/
backend/storage/
backend/security/
```

### Phase 3 — Extract gateway modules

Move stable Gateway helpers into:

```text
gateway/services/
gateway/handlers/
gateway/storage/
```

### Phase 4 — Move dashboard UI

Move embedded dashboard HTML/CSS/JS into:

```text
backend/templates/
backend/static/
```

### Phase 5 — Replace root files with wrappers

Only after testing, root files become small wrappers:

```text
flask_app.py -> imports backend.app
Gateway.js -> imports gateway/Gateway.js
```

## Current commands

Normal deploy:

```bash
titan
```

Backend wrapper test:

```bash
python backend/app.py
```

Gateway wrapper syntax check:

```bash
node --check gateway/Gateway.js
```
