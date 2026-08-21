# SQLite Storage and Notification Fix

## Root cause

The dashboard still called the backend state endpoint with Firebase-specific recovery text. The repository’s state layer was also hard-coded to Firebase functions, so selecting SQLite did not actually change the source of truth. When the state request failed, the UI displayed `Firebase/Auth Sync` and mentioned a missing admin token even though the runtime was intended to be direct-open and local.

## Implemented correction

The runtime now defaults to `TITAN_STORAGE_MODE=sqlite`. It stores the complete application state transactionally in a SQLite database at `TITAN_SQLITE_PATH`, defaulting to `$TITAN_STATE_DIR/titan_nova.sqlite3`. Root state loads/saves and nested child PUT/PATCH/DELETE/GET operations are routed through the SQLite adapter. Firebase remains available only as an explicit opt-in by setting `TITAN_STORAGE_MODE=firebase` and providing `FIREBASE_URL`.

The frontend receives the storage mode from the server. SQLite failures now show `SQLite Local Sync` with a local database/path message; Firebase/Auth Sync wording is used only in Firebase mode. Firebase-missing startup warnings are suppressed in SQLite mode, so the log no longer reports a missing Firebase URL as an error for a local deployment.

## Verification

The following checks passed: 17 Python tests, Node syntax checks and regression tests, Python compilation, shell syntax checks, `git diff --check`, SQLite root/child persistence smoke test, and isolated Flask SQLite dashboard/API smoke test. The smoke tests confirmed `/api/state` returns the initialized local state, the dashboard renders successfully, the SQLite database is created, and child updates persist.

## Termux update commands

```bash
cd ~/Titan-nova-codex
git pull origin main
bash deploy.sh restart
```

For an explicit local SQLite setup, add this to the Termux environment before restarting:

```bash
export TITAN_STORAGE_MODE="sqlite"
export TITAN_SQLITE_PATH="$HOME/Titan-nova-codex/titan_nova.sqlite3"
cd ~/Titan-nova-codex
bash deploy.sh restart
```

Do not delete `titan_nova.sqlite3`; it contains the local application state. If an existing SQLite database is stored elsewhere, set `TITAN_SQLITE_PATH` to that absolute path before starting the app.
