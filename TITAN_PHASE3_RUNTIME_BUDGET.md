# Titan Nova Phase 3 Runtime Budget

Phase 3 goal: stop the two runtime files from growing without control and prepare a safe slimming path.

## Current constraint

The live runtime is still only:

- `flask_app.py`
- `Gateway.js`

Because the dashboard UI, APIs, Firebase logic, wallet, ledger, market, WhatsApp control, scraper, safety, and diagnostics are packed into two files, direct deletion is high risk.

## Phase 3 budget rule

Until the project is split into modules, every cleanup PR should follow these rules:

1. Do not add a new feature while cleaning code.
2. Do not add a second implementation of the same tab behavior.
3. Do not add new patch banners unless they replace old banners.
4. Do not add local JSON fallback unless Firebase cannot safely handle that state.
5. Do not add new inline dashboard JavaScript unless an old duplicate block is removed.
6. Keep public route names and saved Firebase keys stable.

## Safe slimming order

### Step 1: comments and banners

Remove repeated historical banners and keep only one small runtime manifest comment near the top of each runtime file.

### Step 2: version constants

Replace many standalone version constants with a single dictionary/object manifest. This reduces noise without changing behavior.

### Step 3: embedded UI organization

Keep the HTML inside `flask_app.py` for the two-file rule, but group JavaScript by tab and remove duplicate helper functions.

### Step 4: fallback review

Review old fallback values and convert them into clear startup warnings instead of silent defaults.

### Step 5: active logic cleanup

Only delete active-looking code when a search proves it is unused and syntax/smoke checks pass.

## Required checks after every Phase 3 patch

```bash
python -m py_compile flask_app.py
node --check Gateway.js
python titan_smoke_test.py
python titan_dead_code_audit.py
```

## Not done in this phase

This phase does not blindly rewrite `flask_app.py` or `Gateway.js`. The next patch should target a small block, such as version constants only, and test immediately.
