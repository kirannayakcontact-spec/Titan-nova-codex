# Screenshot Error Fix

## Root causes

The Deposit OCR and Withdrawal runtime patches were attempting to assign wrapper functions to `baileys.default`. In the installed Baileys release, the imported module namespace is immutable, so startup logged `Cannot assign to property 'default' of [object Module]` and the hooks did not load.

The Gateway also reported `EADDRINUSE` when another Gateway process was already listening on port 3000. The deploy script had process cleanup, but its port cleanup was not portable across Termux environments without `fuser` or `lsof`. The deploy readiness probe additionally used `/api/health` while the Gateway exposed `/health`.

## Fixes

The hooks now register callbacks on `global.__TITAN_DEPOSIT_OCR_HANDLER__` and `global.__TITAN_WITHDRAWAL_HANDLER__`; the canonical owner socket dispatcher invokes them without mutating the Baileys module namespace. Deposit hook handling now returns a handled flag so the canonical dispatcher does not process the same payment twice.

The deploy script now includes portable PID-based process and port cleanup fallbacks. The Gateway has a process lock, exposes both `/health` and `/api/health`, and returns clean startup status when launched on a free port.

## Verification

The following checks passed after the fix:

- `npm run check`
- `npm test`
- `python3 -m unittest discover -s tests -v` — 13 tests passed
- `python3 -m compileall -q .`
- `bash -n deploy.sh termux_diagnose.sh`
- `git diff --check`
- Fresh Gateway smoke test: no hook/module-assignment errors, no `EADDRINUSE`, expected OCR and withdrawal startup markers present, and `/api/health` returned successfully.

## Termux update commands

```bash
cd ~/Titan-nova-codex
git pull origin main
bash deploy.sh restart
```

If an old process still owns port 3000, run this once and then restart:

```bash
cd ~/Titan-nova-codex
bash deploy.sh stop
bash deploy.sh restart
```

Keep the Gateway on localhost/private LAN unless an explicit network security boundary is configured.
