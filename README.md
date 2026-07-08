# Titan Nova Codex

This repository is restored to the previous Titan Nova legacy runtime behavior.

## Active runtime

The active commands are back to the old two-file style:

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
pip install -r requirements.txt
npm install
```

## Check

```bash
python -m py_compile flask_app.py
node --check Gateway.js
npm run check
```

## Run in Termux

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

## One command update and start gateway

```bash
cd ~/Titan-nova-codex && git pull && npm install && npm run check && npm start
```

For the Flask dashboard/API, run:

```bash
cd ~/Titan-nova-codex && git pull && pip install -r requirements.txt && python flask_app.py
```
