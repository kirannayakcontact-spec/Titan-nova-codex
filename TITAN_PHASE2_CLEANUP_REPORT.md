# Titan Nova Phase 2 Cleanup Report

Phase 2 goal: identify the real reasons the codebase is oversized and prepare safe slimming without changing live behavior.

## Current diagnosis

The runtime is intentionally limited to two active files:

- `flask_app.py`
- `Gateway.js`

Because of that rule, UI, API routes, Firebase storage, admin security, wallet logic, ledger logic, market logic, deposit flow, backups, audit logs, WhatsApp proxy calls, gateway scheduling, scraping, spam guard, and observability are all packed into two files.

## Safe cleanup targets found

### 1. Too many patch/version markers

Both runtime files include many historical patch constants and labels. They help trace changes but add noise. Next safe cleanup can consolidate them into one manifest object per file.

### 2. Embedded dashboard HTML/JS inside Python

`flask_app.py` contains dashboard HTML and browser JavaScript directly inside a Python string. That is the biggest reason the Python file is large. Keeping two runtime files means this cannot be fully removed yet, but it can be compressed and organized.

### 3. Runtime local cache references

`Gateway.js` still references local runtime cache/log files for WhatsApp targets, schedule sent logs, spam guard state, result scrape confirmations, reliability logs, and processed messages. Some are still active fallback/state files and should not be deleted blindly.

### 4. Legacy default/source hints

The audit now flags old default/source hints. These should be reviewed before deletion because some are fallback values used when environment variables are missing.

## Phase 2 action completed

- Expanded `titan_dead_code_audit.py` to report cleanup targets, not just obsolete references.
- Kept runtime behavior unchanged.
- No risky deletion from `flask_app.py` or `Gateway.js` yet.

## Next safe phase

Phase 3 should do actual small runtime cleanup in this order:

1. Consolidate version constants into a single manifest object.
2. Remove duplicate comments and obsolete patch banners.
3. Replace legacy source defaults with explicit env-required warnings.
4. Keep all routes and public function names unchanged.
5. Run:

```bash
python -m py_compile flask_app.py
node --check Gateway.js
python titan_smoke_test.py
python titan_dead_code_audit.py
```

## Strict rule

Do not delete Ledger, Wallet, Market, VIP, Setup, WhatsApp, Firebase, or schedule code unless there is a test or direct proof that it is unused.
