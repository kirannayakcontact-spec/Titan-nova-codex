# Titan Nova Codex

Production Termux runtime for the Titan Nova **bookie-only** dashboard and five-session WhatsApp gateway.

## Install once

```bash
cd ~/github
python -m pip install -r requirements.txt
npm install
```

## Normal run

Open two Termux sessions.

### Session 1 — Flask dashboard

```bash
cd ~/github
HOST=0.0.0.0 PORT=5000 GATEWAY_URL=http://127.0.0.1:3000 python flask_app.py
```

### Session 2 — WhatsApp gateway

```bash
cd ~/github
TITAN_BOOKIE_ONLY_MODE=1 RESULT_SCRAPE_ENABLED=0 GATEWAY_PORT=3000 node whatsapp_multi_session.js
```

Dashboard: http://127.0.0.1:5000

## Access mode

The local runtime is configured for **direct-open mode**. No `TITAN_ADMIN_TOKEN` or `TITAN_GATEWAY_TOKEN` is required. Keep Flask and gateway bound to `127.0.0.1` unless the private network is trusted; direct-open mode must not be exposed to the public internet without an external authentication layer.

## Update and restart

```bash
cd ~/github && bash deploy.sh update
```

## Production check

```bash
cd ~/github && python scripts/single_source_audit.py --result-source-only && python runtime_syntax_check.py && npm run check
```

## Runtime ownership

- `flask_app.py` — Flask launcher and production integrations.
- `titan_core.py` — dashboard, API and business logic core.
- `whatsapp_multi_session.js` — WhatsApp sessions, bookie game-format replies, payments and manual result publishing.
- `deploy.sh` — update, dependency repair, checks and background restart.
- `termux.env.example` — direct-open local environment template, SQLite storage, and WhatsApp settings.
- Automatic result scraping, schedule sending, ledger cards, ledger, guessing/entries and digits are disabled in Bookie-only mode. Results are published manually from the admin Results tab and sent to configured WhatsApp targets.

Runtime data, WhatsApp auth, logs, generated cache files, and the local SQLite database are intentionally not stored in Git.

## Storage mode

The runtime now defaults to **local SQLite**. The full application state is stored transactionally in `titan_nova.sqlite3` under `TITAN_STATE_DIR`; Firebase is not contacted in SQLite mode, and the dashboard no longer reports Firebase/Auth Sync warnings. The WhatsApp gateway reads and writes the same local state through the localhost-only Flask bridge. Set `TITAN_STORAGE_MODE=firebase` and provide `FIREBASE_URL` only if remote Firebase storage is intentionally required. To use an existing local database at a custom location, set `TITAN_SQLITE_PATH` to its absolute path before starting Flask.

## WhatsApp-only payment workflow

Users do not need to open the dashboard. They message the linked WhatsApp bot with `deposit 500` or `deposit`, receive the configured UPI/QR instructions, and send the payment screenshot or a message containing the UTR. The bot deduplicates the proof, records the amount/UTR/OCR risk flags in SQLite, replies to the user, and sends an admin notification through the payment outbox.

For withdrawals, the user sends `withdraw 500 upi user@upi`, `withdraw 500 qr` with a QR image, or `withdraw 500 bank Name / A-C / IFSC`. The bot checks the user profile, available wallet, active-request limit, and amount limits, then places a wallet hold and creates a pending withdrawal. The admin uses the dashboard Finance/Withdrawals area to **Approve**, pay externally, and then **Mark Paid** with the transaction ID; the bot sends approval and completion replies back to the user. Reject actions include the reason in the WhatsApp reply.

The admin dashboard can read the unified activity feed at `/api/payment_activity`, which includes WhatsApp proofs, withdrawals, approvals, rejections, wallet holds, payments, and outbox status. Keep Flask and the gateway bound to `127.0.0.1` because the direct-open dashboard has no HTTP token layer.

## Bookie-only mode

The product keeps only the bookie workflow: users interact through WhatsApp, the bot replies to game-format/status requests, handles deposit and withdrawal messages, and sends manually declared results. The admin uses Finance for payments/wallets/withdrawals, Results for manual open/close declarations, Activity for operational records, Bots for WhatsApp status, and Users for profile approvals.

The following modules are intentionally disabled and their API routes return `410`: ledger, ledger cards, schedule, guessing/entries, digits, load-forwarder and website scraping. Existing SQLite data is preserved; disabling these features does not delete old records. To re-enable the legacy surface temporarily, set `TITAN_BOOKIE_ONLY_MODE=0` before starting both Flask and the gateway.

## Performance tuning

SQLite reads use a short-lived 250 ms in-memory cache and a serialized read-modify-write lock for payment and wallet child updates. The dashboard polls quickly while visible and backs off to a 10-second minimum interval when the browser is hidden. To change the server cache window, set `TITAN_SQLITE_CACHE_TTL_MS`; keep the default for normal Termux use and set it to `0` only while debugging stale-state behaviour.
