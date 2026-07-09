"use strict";

const fs = require("fs");
const path = require("path");

const { getConfig } = require("./config");

const STORE_PATH = process.env.TITAN_NODE_STORE_PATH || path.join(__dirname, "..", "data", "node_runtime_store.json");
const HIGH_GROWTH_COLLECTIONS = ["wallet_transactions", "ledger_entries", "whatsapp/messages", "whatsapp/inbound"];
const storeCache = new Map();
const writeQueues = new Map();

function cleanPath(firebasePath) {
  const cleaned = String(firebasePath || "").split("/").filter(Boolean).join("/");
  if (!cleaned) {
    const error = new Error("firebase path is required");
    error.statusCode = 400;
    throw error;
  }
  return cleaned;
}

function collectionStorePath(collection) {
  return path.join(STORE_PATH.replace(/\.json$/, ""), `${collection.replace(/\//g, "__")}.json`);
}

function localStoreFor(firebasePath) {
  const cleaned = cleanPath(firebasePath);
  for (const collection of HIGH_GROWTH_COLLECTIONS) {
    if (cleaned === collection) return { storePath: collectionStorePath(collection), innerPath: null };
    const prefix = `${collection}/`;
    if (cleaned.startsWith(prefix)) return { storePath: collectionStorePath(collection), innerPath: cleaned.slice(prefix.length) };
  }
  return { storePath: STORE_PATH, innerPath: cleaned };
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

async function fileMtimeMs(storePath) {
  try {
    return (await fs.promises.stat(storePath)).mtimeMs;
  } catch (error) {
    if (error && error.code === "ENOENT") return null;
    throw error;
  }
}

function queueFor(storePath, operation) {
  const previous = writeQueues.get(storePath) || Promise.resolve();
  const next = previous.catch(() => undefined).then(operation);
  writeQueues.set(storePath, next.finally(() => {
    if (writeQueues.get(storePath) === next) writeQueues.delete(storePath);
  }));
  return next;
}

function firebaseStatus() {
  const { firebaseUrl } = getConfig();
  return {
    configured: Boolean(firebaseUrl),
    urlPreview: firebaseUrl ? `${firebaseUrl.slice(0, 24)}...` : "",
    fallbackStore: STORE_PATH,
    shardedCollections: HIGH_GROWTH_COLLECTIONS
  };
}

function firebaseUrl(firebasePath) {
  const { firebaseUrl: baseUrl } = getConfig();
  const url = new URL(`${baseUrl.replace(/\/$/, "")}/${cleanPath(firebasePath)}.json`);
  const token = process.env.FIREBASE_AUTH_TOKEN || process.env.FIREBASE_DATABASE_SECRET || "";
  if (token) url.searchParams.set("auth", token);
  return url;
}

async function request(method, firebasePath, payload) {
  const { firebaseUrl: baseUrl } = getConfig();
  if (!baseUrl || typeof fetch !== "function") return undefined;
  try {
    const response = await fetch(firebaseUrl(firebasePath), {
      method,
      headers: { "Content-Type": "application/json" },
      body: typeof payload === "undefined" ? undefined : JSON.stringify(payload)
    });
    if (!response.ok) return undefined;
    const text = await response.text();
    return text ? JSON.parse(text) : null;
  } catch (error) {
    return undefined;
  }
}

async function readStore(storePath) {
  const mtimeMs = await fileMtimeMs(storePath);
  const cached = storeCache.get(storePath);
  if (cached && cached.mtimeMs === mtimeMs) return clone(cached.data);
  let data = {};
  if (mtimeMs !== null) {
    try {
      const loaded = JSON.parse(await fs.promises.readFile(storePath, "utf8"));
      data = loaded && typeof loaded === "object" && !Array.isArray(loaded) ? loaded : {};
    } catch (error) {
      data = {};
    }
  }
  storeCache.set(storePath, { mtimeMs, data });
  return clone(data);
}

async function writeStore(storePath, data) {
  await fs.promises.mkdir(path.dirname(storePath), { recursive: true });
  const tempPath = path.join(path.dirname(storePath), `.${path.basename(storePath)}.${process.pid}.${Date.now()}.${Math.random().toString(16).slice(2)}.tmp`);
  await fs.promises.writeFile(tempPath, JSON.stringify(data, null, 2), "utf8");
  await fs.promises.rename(tempPath, storePath);
  storeCache.set(storePath, { mtimeMs: await fileMtimeMs(storePath), data: clone(data) });
}

function walk(data, firebasePath, create = false) {
  const parts = cleanPath(firebasePath).split("/");
  let cursor = data;
  for (const part of parts.slice(0, -1)) {
    if (!cursor[part] || typeof cursor[part] !== "object" || Array.isArray(cursor[part])) {
      if (!create) return [{}, parts[parts.length - 1]];
      cursor[part] = {};
    }
    cursor = cursor[part];
  }
  return [cursor, parts[parts.length - 1]];
}

function readPath(data, innerPath) {
  if (innerPath === null) return data;
  let cursor = data;
  for (const part of innerPath.split("/")) {
    if (!cursor || typeof cursor !== "object" || !(part in cursor)) return undefined;
    cursor = cursor[part];
  }
  return cursor;
}

async function getRecord(firebasePath, defaultValue = null) {
  const remote = await request("GET", firebasePath);
  if (typeof remote !== "undefined") return remote === null ? defaultValue : remote;
  const { storePath, innerPath } = localStoreFor(firebasePath);
  const value = readPath(await readStore(storePath), innerPath);
  return typeof value === "undefined" ? defaultValue : value;
}

async function mutateLocal(firebasePath, mutator) {
  const { storePath, innerPath } = localStoreFor(firebasePath);
  return queueFor(storePath, async () => {
    const data = await readStore(storePath);
    const result = mutator(data, innerPath);
    await writeStore(storePath, data);
    return result;
  });
}

async function setRecord(firebasePath, value) {
  const remote = await request("PUT", firebasePath, value);
  if (typeof remote !== "undefined") return remote;
  return mutateLocal(firebasePath, (data, innerPath) => {
    if (innerPath === null) {
      for (const key of Object.keys(data)) delete data[key];
      if (value && typeof value === "object" && !Array.isArray(value)) Object.assign(data, value);
      else data.value = value;
    } else {
      const [cursor, leaf] = walk(data, innerPath, true);
      cursor[leaf] = value;
    }
    return value;
  });
}

async function updateRecord(firebasePath, updates) {
  if (!updates || typeof updates !== "object" || Array.isArray(updates)) {
    const error = new Error("updates must be an object");
    error.statusCode = 400;
    throw error;
  }
  const remote = await request("PATCH", firebasePath, updates);
  if (typeof remote !== "undefined") return remote || updates;
  return mutateLocal(firebasePath, (data, innerPath) => {
    if (innerPath === null) {
      Object.assign(data, updates);
      return data;
    }
    const [cursor, leaf] = walk(data, innerPath, true);
    const current = cursor[leaf] && typeof cursor[leaf] === "object" && !Array.isArray(cursor[leaf]) ? cursor[leaf] : {};
    cursor[leaf] = { ...current, ...updates };
    return cursor[leaf];
  });
}

async function getCollection(firebasePath) {
  const value = await getRecord(firebasePath, {});
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

async function pushRecord(collection, value, id = `${Date.now()}-${Math.random().toString(16).slice(2)}`) {
  const record = { id, ...value };
  await setRecord(`${collection}/${record.id}`, record);
  return record;
}

module.exports = { firebaseStatus, getRecord, setRecord, updateRecord, getCollection, pushRecord };
