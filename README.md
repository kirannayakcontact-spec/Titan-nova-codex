# Titan Nova Codex

Titan Nova legacy two-file runtime for Flask dashboard/API + WhatsApp Gateway.

## Active runtime

The active runtime uses the old two-file style:

```bash
python flask_app.py
node Gateway.js
```

The full previous runtime code is preserved under `legacy-backup/` and loaded by the root launchers:

```text
legacy-backup/flask_app.py.bak
legacy-backup/Gateway.js.bak
```

## Install

```bash
python -m pip install -r requirements.txt
npm install
```

## Check

```bash
python -m py_compile flask_app.py
node --check Gateway.js
npm run check
```

## Easiest Termux deploy

First time or after new GitHub update, run only this small command:

```bash
cd ~/Titan-nova-codex && git pull origin main && bash deploy.sh
```

If your folder name is `titan-app`, use this:

```bash
cd ~/titan-app && git pull origin main && bash deploy.sh
```

After this, future deploy is even shorter:

```bash
bash deploy.sh
```

`deploy.sh` does all work automatically:

1. Pulls latest GitHub code.
2. Installs Python requirements.
3. Installs Node packages.
4. Stops old Flask/Gateway.
5. Starts both Flask and Gateway in background.
6. Shows logs.

## Run in Termux manually

Terminal 1:

```bash
cd ~/Titan-nova-codex
python flask_app.py
```

Terminal 2:

```bash
cd ~/Titan-nova-codex
node Gateway.js
```

## Check if both are running

```bash
ps -ef | grep -E "flask_app.py|Gateway.js" | grep -v grep
```

## Open app

Flask dashboard/API:

```text
http://127.0.0.1:5000
```

Gateway health/server:

```text
http://127.0.0.1:3000
```

## View logs

Flask:

```bash
tail -f flask.log
```

Gateway:

```bash
tail -f gateway.log
```

## Stop both

```bash
pkill -f "python .*flask_app.py" 2>/dev/null || true; pkill -f "node .*Gateway.js" 2>/dev/null || true
```

## If folder not found

Clone first:

```bash
cd ~
git clone https://github.com/kirannayakcontact-spec/Titan-nova-codex.git
cd ~/Titan-nova-codex
```

Then run:

```bash
bash deploy.sh
```

## Extra guide

Full Termux guide is also available in:

```text
TERMUX_DEPLOY.md
```
