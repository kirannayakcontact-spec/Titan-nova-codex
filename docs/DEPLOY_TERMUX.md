# Termux Deploy Notes

Current commands stay the same during modular migration.

## Flask dashboard

```bash
python flask_app.py
```

## WhatsApp Gateway

```bash
node Gateway.js
```

## Same phone setup

Use localhost for Gateway URL:

```bash
GATEWAY_URL=http://127.0.0.1:3000
HOST=127.0.0.1
```

## Split phone setup

Gateway phone:

```bash
HOST=0.0.0.0 node Gateway.js
```

Dashboard phone/server:

```bash
GATEWAY_URL=http://PHONE-IP:3000 python flask_app.py
```

## Before deploy

```bash
python -m py_compile flask_app.py
node --check Gateway.js
```
