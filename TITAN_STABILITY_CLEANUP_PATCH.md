# Titan Nova Stability Cleanup Patch

## Purpose

This patch freezes new feature work and adds a deployment safety layer around the existing two-file runtime:

- `flask_app.py` — Flask admin/API dashboard
- `Gateway.js` — WhatsApp Gateway/runtime bot

The goal is simple:

> Jo save ho, wahi reload ke baad rahe. Jo schedule ho, wahi daily chale. Jo Setup me dikhe, wahi Gateway use kare.

## What this patch adds

### 1. Smoke test script

Run before every deploy:

```bash
python3 scripts/titan_smoke_test.py
```

Or through npm:

```bash
npm run smoke
```

It checks:

- `flask_app.py` Python syntax
- `Gateway.js` Node syntax
- required Python and Node dependencies
- Firebase guard markers
- realtime sync markers
- Setup tab render marker
- Gateway timezone, token, schedule, result-scrape markers
- duplicate Flask route warnings
- dangerous default config warnings

### 2. Gateway syntax command

```bash
npm run check:gateway
```

### 3. `.env.example`

A safe environment template was added so Termux/server deploys do not silently use wrong Firebase or localhost defaults.

### 4. GitHub Actions workflow

Every push/PR now runs:

- Python dependency install
- Titan smoke test
- Gateway syntax check

## Important: what this patch does not do

This patch does **not** add any new product feature. It does not rewrite ledger, result, wallet, or WhatsApp logic. That is intentional.

First stabilize deploy safety. Then fix app behavior in smaller patches.

## Required Termux command before deploy

From repo folder:

```bash
python3 scripts/titan_smoke_test.py
```

If it shows `FAIL`, do not deploy.

If it shows `WARN`, deploy can still run, but read the warning. Common warnings:

- `gateway:default_firebase_url` means `FIREBASE_URL` must be set explicitly.
- `gateway:localhost_host` means split-phone deploy needs `HOST=0.0.0.0` and correct `GATEWAY_URL`.
- `firebase:root_save_modes` means full-root saves still exist historically; new patches must use child-path writes where possible.

## Recommended next patch order

1. Setup blank/render guard patch
2. Ledger child-write-only patch
3. Gateway health URL patch
4. Schedule daily repeat persistence patch
5. Result scraper fresh Open/Close guard patch

## Codex instruction for next patch

Use this exact rule:

```text
Do not add new features. Do not rewrite the whole app. Fix only one stability area. Preserve the 2-file runtime. Before finishing, run: python3 scripts/titan_smoke_test.py and node --check Gateway.js. If smoke test fails, fix it before PR.
```
