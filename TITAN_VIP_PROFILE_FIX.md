# VIP Profile Persistence Fix

This fixes the issue where a VIP profile comes back after refresh.

## Root cause

The Firebase save guard preserved missing records in protected `profiles`, so a profile removed in the UI could be merged back from the latest Firebase state during guarded root save.

## Fix

- Adds deleted profile tombstones in `deletedProfiles`.
- The Firebase merge guard now respects `deletedProfiles` and does not revive removed profiles.
- Adds admin API for persistent VIP removal:

```text
POST /api/vip_profile_remove
```

- Adds admin API for pending profile creation:

```text
POST /api/vip_profile_create_pending
```

## Manual remove by phone

```bash
curl -X POST http://127.0.0.1:5000/api/vip_profile_remove \
  -H 'Content-Type: application/json' \
  -d '{"phone":"91XXXXXXXXXX"}'
```

## Manual create pending profile

```bash
curl -X POST http://127.0.0.1:5000/api/vip_profile_create_pending \
  -H 'Content-Type: application/json' \
  -d '{"phone":"91XXXXXXXXXX","name":"New VIP"}'
```

## Deploy

```bash
titan
```
