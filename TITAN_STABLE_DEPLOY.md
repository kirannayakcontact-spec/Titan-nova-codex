# Titan Nova Stable Deploy

Use this when tabs are blank, stale, or not saving correctly.

## 1. Pull latest clean repo

```bash
cd ~/titan-app
git fetch origin main
git reset --hard origin/main
```

## 2. Install dependencies

```bash
pip install -r requirements.txt
npm install
```

## 3. Set required environment

Copy `termux.env.example` values into `~/.bashrc` and fill your real Firebase URL.

```bash
nano ~/.bashrc
source ~/.bashrc
```

Minimum required values:

```bash
export FIREBASE_URL="https://YOUR-PROJECT-default-rtdb.firebaseio.com/titan_master_data.json"
export APP_TZ="Asia/Kolkata"
export TITAN_BUSINESS_DAY_CUTOFF_HOUR="6"
export GATEWAY_URL="http://127.0.0.1:3000"
```

## 4. Run preflight checks

```bash
python -m py_compile flask_app.py
node --check Gateway.js
python titan_smoke_test.py
python titan_dead_code_audit.py
```

Do not run checks against removed files such as `sitecustomize.py` or `usercustomize.py`.

## 5. Optional Phase 4 banner cleanup

Dry-run first:

```bash
python titan_phase4_banner_cleanup.py
```

Apply only after preflight checks pass:

```bash
python titan_phase4_banner_cleanup.py --apply
python -m py_compile flask_app.py
node --check Gateway.js
python titan_smoke_test.py
python titan_dead_code_audit.py
```

The cleanup script writes `.phase4.bak` backups before changing runtime files.

## 6. Start runtime

Terminal 1:

```bash
cd ~/titan-app
python flask_app.py
```

Terminal 2:

```bash
cd ~/titan-app
node Gateway.js
```

## Why this fixes many-tab failure

Most tab-wide failures come from one shared layer, not from every tab separately:

- wrong or missing `FIREBASE_URL`
- old workflow/deploy command checking removed files
- Python or Gateway syntax/runtime startup error
- Flask and Gateway using different environment values
- stale local process still running old code

Run the checks above before testing Ledger, VIPs, Wallet, Withdrawal, Entries, Pay, Results, Market, Forward, Guard, Backup, Health, AI, Audit, and Setup.

## Phase 1 dead-code cleanup rule

Do not delete active Ledger/Wallet/Market/Gateway logic until the preflight checks pass. Phase 1 only removes repository noise and blocks old removed-file references from coming back.
