# Titan Nova One Command Deploy

This is the easiest Termux deploy method.

## First-time setup

Run once:

```bash
cd ~/titan-app
chmod +x titan_one_command.sh
```

Make sure `~/.bashrc` has your real Firebase URL:

```bash
export FIREBASE_URL="https://YOUR-PROJECT-default-rtdb.firebaseio.com/titan_master_data.json"
export APP_TZ="Asia/Kolkata"
export TITAN_BUSINESS_DAY_CUTOFF_HOUR="6"
export GATEWAY_URL="http://127.0.0.1:3000"
```

Reload env:

```bash
source ~/.bashrc
```

## One command deploy

```bash
cd ~/titan-app && ./titan_one_command.sh
```

It will:

1. Pull latest `main` from GitHub.
2. Install Python dependencies.
3. Install Node dependencies.
4. Run syntax and smoke checks.
5. Stop old Flask/Gateway processes.
6. Start Flask and Gateway in the background.
7. Save logs in `logs/flask.log` and `logs/gateway.log`.

## Make it even shorter

Add this alias to `~/.bashrc`:

```bash
alias titan='cd ~/titan-app && ./titan_one_command.sh'
```

Reload:

```bash
source ~/.bashrc
```

After that, deploy/start with one word:

```bash
titan
```

## Check logs

```bash
tail -f ~/titan-app/logs/flask.log
```

```bash
tail -f ~/titan-app/logs/gateway.log
```

## Stop app

```bash
pkill -f "python flask_app.py"; pkill -f "node Gateway.js"
```

## Optional Phase 4 cleanup during deploy

Only use this after normal deploy works:

```bash
TITAN_APPLY_PHASE4_CLEANUP=1 titan
```
