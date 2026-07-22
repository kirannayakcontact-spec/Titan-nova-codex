# Production upgrade and verification

## New services and configuration

Install Python and Node dependencies with `python -m pip install -r requirements.txt`
and `npm ci`. Run Redis, then set `REDIS_URL=redis://127.0.0.1:6379/0` for shared
Flask rate limits, the `deposit-ocr` queue, and persistent WhatsApp credentials.
Start an OCR worker with:

```bash
rq worker --url "$REDIS_URL" deposit-ocr
```

Set `TITAN_ALLOWED_ORIGINS` to the comma-separated, exact dashboard origins. The
default permits only local development. Rate limits can be tuned with
`TITAN_AUTH_RATE_LIMIT`, `TITAN_DEPOSIT_RATE_LIMIT`, and
`TITAN_ADMIN_RATE_LIMIT`. Keep Firebase credentials and Redis off public networks.

Without `REDIS_URL`, the compatibility runtime intentionally uses in-process rate
limit storage, local Baileys auth files, and synchronous OCR. This fallback is for
development only; production deployments should fail their own configuration
management checks if Redis is absent.

## Local verification

```bash
python -m pytest -q
npm test
python runtime_syntax_check.py
python titan_smoke_test.py
bash -n deploy.sh termux_diagnose.sh
```

Run `bash deploy.sh` only after configuring Redis and allowed origins. The script
now stops before replacing healthy processes when syntax or automated tests fail,
then checks both Flask and Gateway health after startup. `bash termux_diagnose.sh`
collects the same preflight results, versions, processes, ports, HTTP responses,
and bounded log tails for incident reports.
