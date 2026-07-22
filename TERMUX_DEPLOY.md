# Titan Nova Termux Deploy

Use this file when you want easy Termux commands.

## Important

If an old deploy is stuck on `opencv-python-headless` or `pip install`, press `CTRL+C` once, pull the latest update, then use the fast commands below.

## Fast Commands

These commands skip heavy dependency install and tests. Use them after first setup.

Update from GitHub and restart:

```bash
cd ~/github && git pull origin main && bash deploy.sh update
```

Restart only:

```bash
cd ~/github && bash deploy.sh restart
```

Stop:

```bash
cd ~/github && bash deploy.sh stop
```

Status:

```bash
cd ~/github && bash deploy.sh status
```

## First Time Folder `github`

Run this once if `~/github` folder does not exist:

```bash
cd ~ && git clone https://github.com/kirannayakcontact-spec/Titan-nova-codex.git github && cd ~/github && bash deploy.sh install
```

After first install, use the fast commands above.

## If Your Folder Is Still `Titan-nova-codex`

Update and restart:

```bash
cd ~/Titan-nova-codex && git pull origin main && bash deploy.sh update
```

Restart:

```bash
cd ~/Titan-nova-codex && bash deploy.sh restart
```

Stop:

```bash
cd ~/Titan-nova-codex && bash deploy.sh stop
```

## Manual Two-Terminal Run

Terminal 1:

```bash
cd ~/github
python flask_app.py
```

Terminal 2:

```bash
cd ~/github
node whatsapp_multi_session.js
```

## Check If Both Are Running

```bash
ps -ef | grep -E "flask_app.py|whatsapp_multi_session.js|Gateway.js" | grep -v grep
```

## View Logs

Flask:

```bash
tail -f flask.log
```

Gateway:

```bash
tail -f gateway.log
```

## Heavy Full Check

Use only when you want complete dependency install and tests:

```bash
cd ~/github && bash deploy.sh full
```