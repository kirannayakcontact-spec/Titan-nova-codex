"use strict";

// Baileys still expects its atomic multi-file adapter. This wrapper hydrates that
// directory from Redis before connect and mirrors every credential update back.
const fs = require("fs");
const path = require("path");
const { createClient } = require("redis");

let clientPromise;
function redisClient() {
  if (!process.env.REDIS_URL) return null;
  if (!clientPromise) {
    const client = createClient({ url: process.env.REDIS_URL });
    client.on("error", err => console.error("Redis auth store error:", err.message));
    clientPromise = client.connect().then(() => client);
  }
  return clientPromise;
}

async function hydrate(directory, key) {
  const client = await redisClient();
  if (!client) return;
  const files = await client.hGetAll(key);
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  for (const [name, encoded] of Object.entries(files)) {
    if (!/^[A-Za-z0-9_.-]+$/.test(name)) continue;
    fs.writeFileSync(path.join(directory, name), Buffer.from(encoded, "base64"), { mode: 0o600 });
  }
}

async function persist(directory, key) {
  const client = await redisClient();
  if (!client) return;
  const entries = {};
  for (const name of fs.readdirSync(directory)) {
    const file = path.join(directory, name);
    if (fs.statSync(file).isFile()) entries[name] = fs.readFileSync(file).toString("base64");
  }
  const transaction = client.multi().del(key);
  if (Object.keys(entries).length) transaction.hSet(key, entries);
  await transaction.exec();
}

async function usePersistentAuthState(directory, role = "owner_bot", fileAdapter) {
  if (typeof fileAdapter !== "function") throw new TypeError("Baileys file auth adapter is required");
  const key = `${process.env.TITAN_REDIS_PREFIX || "titan"}:wa-auth:${role}`;
  await hydrate(directory, key);
  const state = await fileAdapter(directory);
  const originalSave = state.saveCreds;
  state.saveCreds = async () => {
    await originalSave();
    await persist(directory, key);
  };
  return state;
}

module.exports = { usePersistentAuthState };
