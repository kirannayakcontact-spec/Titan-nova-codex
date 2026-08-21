# Bookie-only mode

## Product scope

Titan Nova now defaults to a bookie-only product mode. Users interact through WhatsApp; the admin uses the dashboard for payment operations, result publishing, bot status and user approvals.

| Active | Behavior |
|---|---|
| WhatsApp game-format replies | `/help`, `/format`, `/status`, profile, wallet, payment status and withdrawal status replies remain available. |
| Deposit | WhatsApp payment instructions, screenshot/UTR intake, duplicate-proof checks and admin notification remain available. |
| Withdrawal | WhatsApp request intake, wallet hold, admin approve/reject/pay actions and user status replies remain available. |
| Results | Admin manually declares open/close results; configured WhatsApp targets receive the result. |
| Admin activity | Finance, Results, Activity, Bots and Users dashboard areas remain available. |

## Disabled scope

Ledger, ledger cards, schedules, guessing/entries, digits, load-forwarder and website result scraping are disabled by default. Their legacy data is not deleted. Flask routes for these modules return HTTP `410` with a `bookie_only_mode` response, and the Gateway does not start their polling/background jobs.

## Runtime configuration

`TITAN_BOOKIE_ONLY_MODE=1` is the default in the Node Gateway, Flask app configuration, preflight patch and Termux environment template. Automatic website result scraping is also disabled with `RESULT_SCRAPE_ENABLED=0`. Manual result declarations continue to use the existing strict open/close validation and WhatsApp delivery pipeline.

## Verification

The implementation was checked with JavaScript syntax checks, Python compilation, Node regression tests, Python regression tests, source architecture checks and an isolated Flask HTTP smoke test. The smoke test confirmed that disabled routes return `410`, while security status, payment activity and results routes remain accessible. No WhatsApp QR login or real-money transaction was performed in the sandbox.

## Termux update

```bash
cd ~/Titan-nova-codex
git pull origin main
export TITAN_STORAGE_MODE="sqlite"
export TITAN_BOOKIE_ONLY_MODE="1"
export RESULT_SCRAPE_ENABLED="0"
export TITAN_SQLITE_PATH="$HOME/Titan-nova-codex/titan_nova.sqlite3"
bash deploy.sh stop
bash deploy.sh restart
```

Keep Flask and the Gateway on localhost/private LAN only because the project is configured for direct-open access without an HTTP token layer.
