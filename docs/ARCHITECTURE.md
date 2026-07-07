# Architecture

Titan Nova now uses the clean modular Andres Berlin runtime.

- `andres-berlin/backend/` contains the Flask backend package.
- `andres-berlin/bot/` contains the Node WhatsApp gateway.
- Root `package.json` owns Node dependencies and launches the gateway with `npm start`.
- Root Termux scripts are thin launch/deploy wrappers only; they should not patch runtime code.

The old monolith runtime and one-off patch scripts were removed to avoid duplicate logic and oversized files.
