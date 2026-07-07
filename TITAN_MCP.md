# Market Control Pro

Market Control Pro adds a dedicated admin page:

```text
/market_control_pro
```

## Controls

- Add or update market
- Save open and close time
- Enable or disable market
- Enable or disable Ledger
- Enable or disable Results
- Enable or disable Entries
- Enable or disable Schedule
- Enable or disable Auto Result
- Enable or disable Auto Pass/Fail
- Set Entry group targets
- Set Result group targets
- Set Forward group targets
- Set Schedule group targets
- Set Bookie/Admin group targets
- Archive or restore market

Hard delete is intentionally avoided on this page. Archive/OFF is safer for production because it avoids breaking old records, schedules, and results.

## Deploy

```bash
titan
```

Open:

```text
http://127.0.0.1:5000/market_control_pro
```
