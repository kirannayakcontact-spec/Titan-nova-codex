# Titan Nova Update Rules

## Rule 1
Do not mix new features with stability or refactor patches.

## Rule 2
Change only one area per patch:

- Setup
- Ledger
- Gateway health
- Schedule
- Firebase
- Wallet
- Payments
- UI

## Rule 3
Keep these commands working during every phase:

```bash
python flask_app.py
node Gateway.js
```

## Rule 4
Run checks before deploy:

```bash
python -m py_compile flask_app.py
node --check Gateway.js
```

When available:

```bash
python3 scripts/titan_smoke_test.py
```

## Rule 5
Do not rename Firebase paths without a clear migration.

## Rule 6
During folder split, copy helpers first, import them second, and remove old duplicate code only after checks pass.
