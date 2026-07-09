# Titan Nova Termux Deploy

Use this file when you want an easy Termux deploy command.

## Easiest deploy command

Most users should run this:

```bash
cd ~/Titan-nova-codex && git pull origin main && bash deploy.sh
```

If your folder is `~/titan-app`, run this:

```bash
cd ~/titan-app && git pull origin main && bash deploy.sh
```

After the first run, you can deploy again with only:

```bash
bash deploy.sh
```

## What deploy.sh does

1. Pulls latest code from GitHub.
2. Installs Python requirements.
3. Installs Node packages.
4. Stops old Flask/Gateway processes.
5. Starts Flask and Gateway in background.
6. Shows latest logs.

## Check if both are running

```bash
ps -ef | grep -E "flask_app.py|Gateway.js" | grep -v grep
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

## Manual two-terminal run

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

## If command says folder not found

Clone first:

```bash
cd ~
git clone https://github.com/kirannayakcontact-spec/Titan-nova-codex.git
cd ~/Titan-nova-codex
bash deploy.sh
```
