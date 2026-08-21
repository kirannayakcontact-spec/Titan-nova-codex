# WhatsApp-Only Payment System Upgrade

## Scope

The payment runtime is designed so that end users interact only through the linked WhatsApp bot. The admin uses the dashboard to review incoming payment activity, approve or reject deposits, approve withdrawals, complete external payouts, and mark withdrawals paid.

## Storage correction

Before this upgrade, the WhatsApp gateway’s payment handlers were still named and implemented around direct Firebase access while the dashboard had been changed to local SQLite. This created a split-brain risk: the dashboard could read one state source while WhatsApp deposits, withdrawal holds, payment outbox messages, and idempotency records were written to another source.

The gateway now defaults to `TITAN_STORAGE_MODE=sqlite` and reads/writes the same SQLite-backed Flask state through localhost-only `/api/internal/state` and `/api/internal/state/child` bridges. Child PUT, PATCH, DELETE, and durable-lock operations use the same database. Firebase remains an explicit opt-in mode only.

## User flow

A user sends `deposit 500` or `deposit` to the bot, receives the configured UPI/QR instructions, and sends a screenshot or UTR. The bot extracts proof data, checks duplicate message/UTR/transaction/screenshot identifiers, evaluates receiver mismatch and OCR risk flags, stores the payment in SQLite, replies to the user, and places an admin notification in the payment outbox.

A user sends `withdraw 500 upi user@upi`, `withdraw 500 qr` with a QR image, or a bank-detail command. The bot verifies the linked profile, amount limits, available balance, one-active-request policy, and sender identity. It creates a withdrawal request and applies a wallet hold before notifying the admin. The admin dashboard supports Approve, Reject, and Mark Paid. Mark Paid releases the hold, deducts the balance exactly once, stores the external transaction ID, writes an audit record, and queues the WhatsApp completion message.

## Admin activity

A unified `/api/payment_activity` endpoint now exposes deposit proofs, withdrawal requests, approvals, rejections, wallet holds, paid events, pending counters, and audit entries. The existing `/api/payments` response also includes the activity feed, so the Finance dashboard can consume the same view without requiring a separate client site.

## Safety controls

The payment path keeps role-aware WhatsApp routing, per-message durable deduplication, duplicate UTR/transaction/screenshot checks, receiver mismatch flags, amount limits, profile approval rules, wallet holds, idempotent approval/rejection/paid actions, and WhatsApp delivery outbox processing. The SQLite gateway bridge accepts requests only from localhost. Keep Flask and the gateway bound to `127.0.0.1` because the app is in direct-open mode.

## Verification

Passed checks include 19 Python regression tests, Node regression tests, JavaScript syntax checks, Python compilation, shell syntax checks, `git diff --check`, SQLite root/child persistence smoke tests, isolated Flask `/api/state` and `/api/payment_activity` tests, and a no-QR Gateway smoke test with `TITAN_SKIP_WHATSAPP_START=1`. The Gateway smoke test confirmed SQLite mode, successful `/api/health`, successful bridge reads/writes, and no Firebase-missing warning or payment-hook startup errors.

## Termux update commands

```bash
cd ~/Titan-nova-codex
git pull origin main
export TITAN_STORAGE_MODE="sqlite"
export TITAN_SQLITE_PATH="$HOME/Titan-nova-codex/titan_nova.sqlite3"
bash deploy.sh stop
bash deploy.sh restart
```

Do not delete `titan_nova.sqlite3`; it contains the local payment, wallet, profile, audit, and outbox state.
