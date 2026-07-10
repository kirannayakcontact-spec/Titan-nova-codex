# Titan Nova Runtime Cleanup Audit

Date: 2026-07-10
Branch: `cleanup/runtime-duplicates`

## Reference audit

The Flask launcher was loading three overlapping Ledger UI patches:

- `titan_ledger_autopf_ui_patch.py`
- `titan_ledger_autopf_visible_patch.py`
- `titan_ledger_control_overlay_patch.py`

All three injected browser JavaScript for the same Auto Pass/Fail controls. This created multiple DOM observers, duplicate global functions, and competing Ledger visibility logic.

The Gateway launcher did not load `gateway_financial_ingest_patch.js`. That file contained the retired text-only deposit path that could create payment records without a verified screenshot.

## Consolidation

Canonical Ledger UI:

- `titan_ledger_control_overlay_patch.py`

It now owns:

- Ledger screen detection
- one floating `CONTROL` button
- Auto Mark, Only WAIT, All VIPs, and Record Results settings
- Mark Now from saved results
- ANK/JODI/PANEL payout settings
- current-day Auto Pass/Fail summary
- safe result-control API writes

## Deleted files

- `titan_ledger_autopf_ui_patch.py` — duplicate Ledger UI injector
- `titan_ledger_autopf_visible_patch.py` — duplicate visibility/tab injector
- `gateway_financial_ingest_patch.js` — disabled unsafe financial ingest path

## Preserved files

Safe-mode skipped files were not deleted merely because they are skipped. Setup, Firebase, VIP, realtime, stability, and safety modules remain available for full UI mode and future controlled activation.

Legacy engines were preserved:

- `legacy-backup/flask_app.py.bak`
- `legacy-backup/Gateway.js.bak`

## Syntax and reference safety

`runtime_syntax_check.py` validates active runtime files before deployment:

- Python files are parsed with `ast.parse`.
- JavaScript files are checked with `node --check`.
- deleted module names are forbidden in launchers.
- required canonical module references must remain present.

`deploy.sh` runs this check before stopping the currently running Flask/Gateway processes. A failed check aborts deployment without taking the old working app offline.

## Expected runtime change

Flask active Ledger UI injectors:

- Before: 3
- After: 1

Unsafe disabled Gateway financial ingest files:

- Before: 1 retained but disabled
- After: 0
