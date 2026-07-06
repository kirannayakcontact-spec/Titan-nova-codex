# Firebase Schema Notes

This document is a placeholder for the canonical Firebase paths used by Titan Nova.

## Rule

Do not rename or move Firebase paths without a migration.

## Paths to document during Phase 2

- profiles
- wallets
- walletTransactions
- entries
- ledgerSchedules
- resultRecords
- marketRegistry
- paymentOutbox
- loadForwarderOutbox
- resultTargets
- whatsappSafetyTargets
- auditLog

## Why this matters

Flask and Gateway must read and write the same paths. If one side saves to a different path, the UI looks saved but refresh/Gateway behavior will be wrong.
