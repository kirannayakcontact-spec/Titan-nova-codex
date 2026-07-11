# Titan Nova Health Check

Use this checklist before changing runtime, frontend, backend, Gateway, Firebase,
or money-flow code. The goal is to prove that the current production runtime is
working before any professional cleanup starts.

## Official runtime under test

```bash
python flask_app.py
node Gateway.js
```

This matches the official production decision in `docs/RUNTIME_DECISION.md`.

## A-to-Z flow being checked

```text
Frontend browser
  -> Flask dashboard/API on port 5000
  -> Firebase state/config
  -> Gateway proxy APIs
  -> Node WhatsApp Gateway on port 3000
  -> WhatsApp login, targets, schedules, notifications
```

## 1. Clean local status

Run this first so you know whether local files were already changed:

```bash
git status --short
```

Expected good result: no unexpected modified files.

## 2. Static runtime checks

Run these before starting servers:

```bash
python -m py_compile flask_app.py backend/app.py
node --check Gateway.js
npm run check
python runtime_syntax_check.py
```

Expected good result:

- Python files compile.
- Gateway JavaScript syntax passes.
- `npm run check` passes.
- `runtime_syntax_check.py` prints `Titan Nova active runtime syntax/reference check passed`.

## 3. Start Flask backend and frontend server

Terminal 1:

```bash
HOST=0.0.0.0 PORT=5000 python flask_app.py
```

Expected good result:

- Flask starts without traceback.
- Browser can open `http://127.0.0.1:5000`.
- Dashboard HTML loads.

## 4. Start WhatsApp Gateway

Terminal 2:

```bash
GATEWAY_PORT=3000 node Gateway.js
```

Expected good result:

- Gateway starts without syntax/runtime boot crash.
- QR/login status endpoints respond.
- If WhatsApp is not logged in, QR/login status should still respond with a clear state.

## 5. Flask health endpoints

With Flask running, check:

```bash
curl -fsS http://127.0.0.1:5000/api/plain_health
curl -fsS http://127.0.0.1:5000/api/runtime_boot/status
curl -fsS http://127.0.0.1:5000/titan-test
```

Expected good result:

- `/api/plain_health` returns JSON success.
- `/api/runtime_boot/status` returns boot status and patch report.
- `/titan-test` returns a simple working HTML page.

## 6. Dashboard/frontend check

Open this URL in a browser:

```text
http://127.0.0.1:5000
```

Expected good result:

- Dashboard opens.
- No startup error page appears.
- Main admin UI renders.
- Browser console should not show a fatal boot/render error.

If admin security token is configured, login first with the configured token.

## 7. Gateway health endpoints

With Gateway running, check:

```bash
curl -fsS http://127.0.0.1:3000/health
curl -fsS http://127.0.0.1:3000/status
curl -fsS http://127.0.0.1:3000/wa_login_status
```

Expected good result:

- `/health` responds.
- `/status` responds with Gateway state.
- `/wa_login_status` responds with WhatsApp login/QR state instead of crashing.

## 8. Flask-to-Gateway proxy check

With both Flask and Gateway running, check:

```bash
curl -fsS http://127.0.0.1:5000/api/gateway_status
curl -fsS http://127.0.0.1:5000/api/wa_login_status
```

Expected good result:

- Flask can reach Gateway.
- Responses are JSON and not connection-refused errors.

## 9. Firebase/config readiness check

Check runtime boot status:

```bash
curl -fsS http://127.0.0.1:5000/api/runtime_boot/status
```

Expected good result:

- `legacyLoaded` is true.
- `firebaseUrlConfigured` is true.
- Critical patches are either loaded or intentionally skipped for safe UI boot.

## 10. Money-flow smoke checklist

Do not change wallet, payment, withdrawal, entry, result, or settlement code until
these flows are manually mapped and verified in a safe test environment:

1. Admin dashboard loads current state.
2. Wallet list loads.
3. Payment/deposit list loads.
4. Withdrawal list loads.
5. Entry/result tabs load.
6. Gateway status appears in dashboard.
7. WhatsApp QR/login status appears.
8. No Firebase data-loss warning appears during normal load.

## 11. One-command deploy check

For Termux or production-like startup, run:

```bash
bash deploy.sh
```

Expected good result:

- Dependencies install or are already present.
- Runtime syntax/reference check passes.
- Old Flask/Gateway processes stop.
- Flask starts on port 5000.
- Gateway starts on port 3000.
- Runtime boot status is printed.
- Logs do not show fatal startup tracebacks.

## Common failures and meaning

| Symptom | Likely cause | First action |
| --- | --- | --- |
| `Runtime syntax/reference check fail` | Broken import/syntax/reference | Stop and fix before deploy |
| Port 5000 busy | Old Flask still running | Stop old process or run `bash deploy.sh` |
| Port 3000 busy | Old Gateway still running | Stop old process or run `bash deploy.sh` |
| `/api/runtime_boot/status` says `legacyLoaded=false` | Legacy Flask failed to load | Read Flask traceback in response/log |
| Gateway connection refused from Flask | Gateway not running or wrong port | Start `node Gateway.js` and verify port 3000 |
| WhatsApp not logged in | Session missing/expired | Open QR/login status and scan QR |
| Firebase warning | Config/network/data issue | Do not save money-flow data until checked |

## Rule for future changes

Before each new step:

1. Run static checks.
2. Confirm dashboard/API/Gateway health if the change can affect runtime behavior.
3. Make the smallest safe change.
4. Run checks again.
5. Commit only after checks pass or an environment limitation is clearly recorded.
