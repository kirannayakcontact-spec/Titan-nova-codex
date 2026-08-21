# Titan Nova Performance Optimization

## Summary

The main performance bottlenecks were repeated full SQLite JSON parsing during dashboard/API polling, concurrent child read-modify-write races, duplicate member state polling alongside the shared realtime engine, and continuous background polling while the dashboard was hidden.

## Implemented changes

### SQLite state path

A short-lived in-memory cache is now used for SQLite state reads. The default cache window is 250 ms and is configurable with `TITAN_SQLITE_CACHE_TTL_MS`. Every successful write updates the cache immediately. A re-entrant lock serializes the complete child read-modify-write cycle, preventing simultaneous WhatsApp payment, withdrawal, wallet, and outbox updates from overwriting each other.

### Dashboard polling

The shared realtime frontend engine now uses a visibility-aware scheduler. The active dashboard continues to sync on the configured visible interval, while hidden browser tabs back off to at least 10 seconds. The legacy member polling loop becomes a fallback only when the shared realtime engine is not present, eliminating duplicate `/api/state` requests on current pages.

### Operational configuration

The Termux environment template and README document the cache setting and expected local behaviour. Normal users should keep the 250 ms default; setting it to `0` is intended only for debugging stale-state behaviour.

## Verification

Passed 21 Python regression tests, Node regression tests, JavaScript syntax checks, Python compilation, shell syntax checks, `git diff --check`, and the earlier SQLite root/child, payment activity, and no-QR Gateway smoke tests. No runtime database file was included in the commit.

## Termux update

```bash
cd ~/Titan-nova-codex
git pull origin main
export TITAN_STORAGE_MODE="sqlite"
export TITAN_SQLITE_PATH="$HOME/Titan-nova-codex/titan_nova.sqlite3"
export TITAN_SQLITE_CACHE_TTL_MS="250"
bash deploy.sh stop
bash deploy.sh restart
```
