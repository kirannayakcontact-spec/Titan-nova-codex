# Titan Nova WhatsApp-Style UI

This adds a WhatsApp-style visual theme to the dashboard without changing ledger, Firebase, Gateway, wallet, market, or route behavior.

## Enable

The one-command deploy enables it by default:

```bash
titan
```

or:

```bash
cd ~/titan-app && ./titan_one_command.sh
```

## Disable

```bash
TITAN_WHATSAPP_UI=0 titan
```

## Manual apply

```bash
cd ~/titan-app
python titan_whatsapp_ui_patch.py --apply
python -m py_compile flask_app.py
python flask_app.py
```

## What changes visually

- Dark chat-style background
- WhatsApp-like green header accents
- Rounded chat-card style panels
- Green pill buttons
- Dark bottom navigation
- Message-bubble style notifications

## Safety

The patcher creates `flask_app.py.wa-ui.bak` before modifying the local runtime file. The repository copy remains clean after `git reset --hard origin/main`; the one-command deploy reapplies the theme automatically.
