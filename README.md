# Titan Nova Codex

This repository currently acts as the launcher for the clean modular **Andres Berlin** starter under `andres-berlin/`.

## Node dependency ownership

Node dependencies are managed from the repository root `package.json`.

Run Node commands from the repository root so npm resolves the root `node_modules` and `package-lock.json`:

```bash
npm install
npm run check
npm start
```

The root package launches the Andres Berlin bot with `node andres-berlin/bot/index.js`. Runtime dependencies for that bot, including current and future WhatsApp/Baileys packages used by `andres-berlin/bot/`, must stay in the root `package.json` while this repository remains the launcher.

The `andres-berlin/package.json` file is kept only as package metadata and convenience scripts for the nested starter; it should not declare runtime dependencies unless `andres-berlin/` is split into a standalone repository.
