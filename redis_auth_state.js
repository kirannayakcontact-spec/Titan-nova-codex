// Baileys still expects its atomic multi-file adapter. This wrapper hydrates that
// directory from Redis before connect and mirrors every credential update back.
const fs = require("fs");
const path = require("path");
const { createClient } = require("redis");

let clientPromise;
const persistChains = new Map();
const SAFE_FILE = /^[A-Za-z0-9_.-]+$/;

function redisClient() {
  if (!process.env.REDIS_URL) return null;
  if (!clientPromise) {
    const client = createClient({ url: process.env.REDIS_URL });
    client.on("error", err => console.error("Redis auth store error:", err.message));
    clientPromise = client.connect().then(() => client).catch(async error => {
      // A rejected promise must not poison all future reconnect attempts.
      clientPromise = undefined;
      try { await client.disconnect(); } catch (_) {}
      throw error;
    });
  }
  return clientPromise;
}

async function hydrate(directory, key) {
  const client = await redisClient();
  if (!client) return;
  const files = await client.hGetAll(key);
  const entries = Object.entries(files).filter(([name]) => SAFE_FILE.test(name));
  // A missing Redis hash is treated as first-run bootstrap so an existing local
  // login is not destroyed before it can be mirrored to Redis.
  if (!entries.length) return;
  fs.mkdirSync(directory, { recursive:true, mode:0o700 });
  const remoteNames = new Set(entries.map(([name]) => name));
  for (const name of fs.readdirSync(directory)) {
    if (SAFE_FILE.test(name) && !remoteNames.has(name)) {
      try { fs.rmSync(path.join(directory, name), {force:true}); } catch (_) {}
    }
  }
  for (const [name, encoded] of entries) {
    const target = path.join(directory, name);
    const tmp = `${target}.tmp`;
    fs.writeFileSync(tmp, Buffer.from(encoded, "base64"), { mode:0o600 });
    fs.renameSync(tmp, target);
  }
}

async function persistNow(directory, key) {
  const client = await redisClient();
  if (!client) return;
  const entries = {};
  for (const name of fs.readdirSync(directory)) {
    if (!SAFE_FILE.test(name)) continue;
    const file = path.join(directory, name);
    let stat;
    try { stat = fs.statSync(file); } catch (_) { continue; }
    if (stat.isFile()) entries[name] = fs.readFileSync(file).toString("base64");
  }
  const transaction = client.multi().del(key);
  if (Object.keys(entries).length) transaction.hSet(key, entries);
  await transaction.exec();
}

function persist(directory, key) {
  const previous = persistChains.get(directory) || Promise.resolve();
  const current = previous.catch(() => {}).then(() => persistNow(directory, key));
  persistChains.set(directory, current.finally(() => {
    if (persistChains.get(directory) === current) persistChains.delete(directory);
  }));
  return current;
}

async function usePersistentAuthState(directory, role = "owner_bot", fileAdapter) {
  if (typeof fileAdapter !== "function") throw new TypeError("Baileys file auth adapter is required");
  await hydrate(directory, `${process.env.TITAN_REDIS_PREFIX || "titan"}:wa-auth:${role}`);
  const state = await fileAdapter(directory);
  const originalSave = state.saveCreds;
  const key = `${process.env.TITAN_REDIS_PREFIX || "titan"}:wa-auth:${role}`;
  state.saveCreds = async (...args) => {
    await originalSave(...args);
    await persist(directory, key);
  };
  return state;
}

module.exports = { usePersistentAuthState };
