# Bookie-only product

Titan Nova is permanently a WhatsApp-first bookie system. The admin dashboard contains only Finance, Results, Activity, Bots and Users operations.

## Active workflow

Incoming WhatsApp messages are handled by the bot. Payment messages support deposit proof/UTR intake and withdrawal requests. The bot sends acknowledgement and status replies, while the admin reviews activity and approves or rejects financial actions from Finance.

Results have two supported sources. The Gateway polls the configured result website when `RESULT_SCRAPE_ENABLED=1`, applies market and freshness validation, saves accepted results and sends them to configured WhatsApp targets. The admin can also manually declare open and close results from the Results tab. Both paths share the same strict open/close validation, duplicate-safe storage and outbound delivery pipeline.

## Physically removed modules

The source no longer contains the legacy Ledger UI, ledger-card editing, schedule sender, guessing/entry parser, digit/trick editor, load-forwarder or ledger settlement/auto-marking routes and jobs. Old SQLite records are retained for data safety but are not rendered or processed by the active product. Since the product is permanently bookie-only, there is no legacy-mode environment switch.

## Runtime configuration

```bash
export TITAN_STORAGE_MODE="sqlite"
export RESULT_SCRAPE_ENABLED="1"
export RESULT_SOURCE_NAME="Dpbosss Net In"
export RESULT_SOURCE_URL="https://dpbosss.net.in/"
export RESULT_SCRAPE_URLS="https://dpbosss.net.in/"
```

Use a trusted result source and verify its page format before production use. Keep Flask and Gateway on localhost/private LAN because the dashboard is direct-open and does not enforce an HTTP token layer.

## Termux update

```bash
cd ~/Titan-nova-codex
git pull origin main
export TITAN_STORAGE_MODE="sqlite"
export RESULT_SCRAPE_ENABLED="1"
bash deploy.sh stop
bash deploy.sh restart
```
