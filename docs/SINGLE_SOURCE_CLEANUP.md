# Titan Nova Single-Source Cleanup

Goal: keep one owner UI, one owner API, and one Firebase source path for every feature. Do not add duplicate patch modules for tab bugs.

## Current cleanup status

Completed on `main`:

- Removed duplicate disabled patch modules where allowed:
  - `ledger_market_settings.py`
  - `ledger_compact_ui.py`
  - `entries_quick_actions.py`
- Disabled wrong `titan_native_ui.py` shell so it no longer injects a competing Home/native UI.
- Kept `deposit_finance_force.py` as a small bridge that only loads required safe modules:
  - `titan_realtime_global`
  - `settlement_toggle_sticky`
  - `settlement_toggle_ui_guard`
  - `ledger_auto_mark_safe`
  - `deposit_finance_native`
  - `deposit_screenshot_routes`
  - `deposit_screenshot_ui`
- Added reporting script: `scripts/single_source_audit.py`.

## Pull request decisions

Close these duplicate/conflicting open PRs from the GitHub UI before merging anything else:

| PR | Decision | Reason |
| --- | --- | --- |
| #48 Setup blank guard patcher | Close | Duplicate of merged Setup blank fix #19. |
| #50 Scaffold | Close | Scaffold duplicated by merged #51 and #69. |
| #52 Phase 1 config health | Close | Duplicates modular health/config work and is not part of current root runtime cleanup. |
| #76 Backend timeouts + remove legacy backups | Close | Conflicts with current Termux runtime because it removes legacy backups that #78 restored. |
| #85 Setup Control Center status module | Close or hold | Adds another Setup/status surface in modular runtime; risks duplicate Setup control behavior. |

Hold these until after duplicate audit:

| PR | Decision | Reason |
| --- | --- | --- |
| #37 Owner number login code | Hold | Real feature; review after core cleanup. |
| #40 VIP delete UI patch | Hold | Needs verification against existing #39 persistent remove API. |
| #41 Professional project structure scaffold | Hold | Only useful if project formally migrates away from two-file runtime. |
| #42 Stability cleanup patch | Hold | May contain useful checks, but should not merge until duplicate report is reviewed. |

## Owner map

| Feature | Owner UI | Owner API/source |
| --- | --- | --- |
| Ledger cards | Ledger tab | `/api/ledger_card_update`, `profiles/{id}/dayRecords` |
| Entries | Entries tab | Existing `/api/entry_settings` and entry ingest flow, `entrySettings`, `entries` |
| Market settings | Market tab only | Existing market registry API, `marketRegistry` |
| Setup | Setup tab only | System/config/status only; no duplicate Market/Entries controls |
| Deposit | Finance/Deposit UI | `/api/deposit_flow_v1/*`, `depositSettings.v1`, `payments` |
| VIP | VIP tab | `/api/approve_vip_profile`, `/api/reject_vip_profile`, `/api/vip_profile_remove`, `profiles`, `wallets` |
| WhatsApp | Forward/Guard/WA status UI | Gateway routes, `targets`, `groups`, `contacts` |

## Commands after pulling latest

```bash
cd ~/titan-app

git fetch origin main
git reset --hard origin/main

python -m py_compile flask_app.py deposit_finance_force.py titan_native_ui.py scripts/single_source_audit.py
node --check Gateway.js
python scripts/single_source_audit.py > duplicate_report.txt
```

Read the first part of the report:

```bash
cat duplicate_report.txt | head -160
```

## Next cleanup phase

1. Review `duplicate_report.txt`.
2. Remove or merge duplicate APIs/functions inside the owning source file only.
3. Fix tab bugs inside the original tab function, not via new `after_request` overlay modules.
4. Keep direct Firebase child-path saves; do not reintroduce full root overwrites.
5. After duplicates are removed, then fix current Entries bug: Manual Market Time Setup open-state should be preserved inside the original Entries UI/render code.
