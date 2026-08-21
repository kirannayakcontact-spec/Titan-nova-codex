# Titan Nova Codex

Production Termux runtime for the Titan Nova **bookie-only** dashboard and WhatsApp gateway.

## Product scope

Users interact with the system through WhatsApp. The admin dashboard retains Finance, Results, Activity, Bots and Users. The source now physically excludes the legacy ledger, ledger-card, schedule, guessing/entry, digits and load-forwarder modules instead of merely hiding them behind a mode flag.

| Active system | Behavior |
|---|---|
| WhatsApp bookie replies | Help, status, wallet/profile, payment status and result information replies. |
| Payments | Deposit proof/UTR intake and withdrawal request, approval, rejection and paid notifications. |
| Results | Website auto-result polling and admin manual open/close publishing use the same result validation and WhatsApp delivery flow. |
| Admin activity | Finance/payment activity, bot health, user/profile operations and result delivery status remain visible. |

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
RESULT_SCRAPE_ENABLED=1 GATEWAY_PORT=3000 node whatsapp_multi_session.js
```

Dashboard: http://127.0.0.1:5000

## Result system

The Gateway polls the configured result website when `RESULT_SCRAPE_ENABLED=1`. Configure `RESULT_SOURCE_NAME`, `RESULT_SOURCE_URL` and `RESULT_SCRAPE_URLS` with the trusted source pages. Scraped results pass through the existing format, market and freshness checks before they are saved and sent to configured WhatsApp targets.

The admin can also open the Results tab and manually declare an open result in `123-4` format or a close result in `123-45-678` format. Close results are accepted only after a matching fresh open result. Manual declarations and scraped declarations share the same state and duplicate-safe WhatsApp delivery pipeline.

## Access mode

The local runtime is configured for **direct-open mode**. No `TITAN_ADMIN_TOKEN` or `TITAN_GATEWAY_TOKEN` is required. Keep Flask and Gateway bound to `127.0.0.1` unless the private network is trusted; direct-open mode must not be exposed to the public internet without an external authentication layer.

## Update and restart

```bash
cd ~/github && git pull origin main && bash deploy.sh restart
```

## Runtime ownership

- `flask_app.py` — Flask launcher and production integrations.
- `titan_core.py` — slim admin dashboard, payment APIs, result APIs and activity APIs.
- `whatsapp_multi_session.js` — WhatsApp connection, bookie replies, payments, auto-result polling and manual result publishing.
- `deploy.sh` — update, dependency repair, checks and restart.
- `termux.env.example` — SQLite, result-source and WhatsApp settings.

## Storage mode

The runtime defaults to **local SQLite**. The full application state is stored transactionally in `titan_nova.sqlite3` under `TITAN_STATE_DIR`; Firebase is not contacted in SQLite mode, and the dashboard is SQLite-aware. The WhatsApp Gateway reads and writes the same local state through the localhost-only Flask bridge. Set `TITAN_STORAGE_MODE=firebase` and provide `FIREBASE_URL` only if remote Firebase storage is intentionally required.

## WhatsApp-only payment workflow

Users do not need to open the dashboard. They message the linked WhatsApp bot with `deposit 500` or `deposit`, receive configured UPI/QR instructions, and send the payment screenshot or UTR. The bot deduplicates proof, records amount/UTR/OCR risk flags in SQLite, replies to the user and notifies the admin through the payment outbox.

For withdrawals, the user sends `withdraw 500 upi user@upi`, `withdraw 500 qr` with a QR image, or `withdraw 500 bank Name / A-C / IFSC`. The bot checks the profile, wallet and limits, places a wallet hold and creates a pending withdrawal. The admin uses Finance/Withdrawals to approve, pay externally and mark paid with a transaction ID; the bot sends status replies back to the user.

## Removed source modules

The following legacy source modules and their Flask/Gateway entry points were removed: ledger, ledger cards, schedule sending, guessing/entries, digits/trick editing, load-forwarder and ledger settlement/auto-marking. Old SQLite records are preserved but are no longer rendered, accepted or processed. There is no `TITAN_BOOKIE_ONLY_MODE=0` fallback because the product is now permanently bookie-only.

## Performance tuning

SQLite reads use a short-lived 250 ms in-memory cache and serialized write locking for payment and wallet updates. Dashboard polling backs off while the browser is hidden. Keep `TITAN_SQLITE_CACHE_TTL_MS=250` for normal Termux use and set it to `0` only while debugging stale-state behavior.
