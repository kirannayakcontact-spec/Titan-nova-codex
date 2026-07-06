# Titan Nova WhatsApp QR Refresh Fix

Use this when the dashboard QR appears but WhatsApp says it is invalid or scanning does nothing.

## What this fixes

- Old/stale QR is no longer returned as valid.
- QR status responses are no-cache.
- QR includes an expiry countdown.
- The deploy command applies the QR refresh patch before starting Gateway.

## Deploy

```bash
titan
```

or:

```bash
cd ~/titan-app && ./titan_one_command.sh
```

## Recommended reconnect steps

1. Open WhatsApp on your phone.
2. Go to Linked devices.
3. If old Titan session exists, remove/log out that linked device.
4. In Titan dashboard, press Reset Session / Fresh QR.
5. Wait 5-10 seconds.
6. Scan the newest QR immediately.

## Manual reset from Termux

```bash
pkill -f "node Gateway.js" 2>/dev/null || true
rm -rf ~/titan-app/auth_info_baileys
cd ~/titan-app && ./titan_one_command.sh
```

## QR text check

```bash
curl -s http://127.0.0.1:3000/wa_login_status
```

A fresh QR should have `qrAvailable:true` and `qrExpiresInSeconds` greater than zero.
