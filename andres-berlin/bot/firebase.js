"use strict";

const fs = require("fs");
const path = require("path");

const { getConfig } = require("./config");

const STORE_PATH = process.env.TITAN_NODE_STORE_PATH || path.join(__dirname, "..", "data", "node_runtime_store.json");

function cleanPath(firebasePath) {
  const cleaned = String(firebasePath || "").split("/").filter(Boolean).join("/");
  if (!cleaned) {
    const error = new Error("firebase path is required");
    error.statusCode = 400;
    throw error;
  }
  return cleaned;
}

function firebaseStatus() {
  const { firebaseUrl } = getConfig();
  return {
    configured: Boolean(firebaseUrl),
    urlPreview: firebaseUrl ? `${firebaseUrl.slice(0, 24)}...` : "",
    fallbackStore: STORE_PATH
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

function readStore() {
  if (!fs.existsSync(STORE_PATH)) return {};
  try {
    return JSON.parse(fs.readFileSync(STORE_PATH, "utf8"));
  } catch (error) {
    return {};
  }
}

function writeStore(data) {
  fs.mkdirSync(path.dirname(STORE_PATH), { recursive: true });
  fs.writeFileSync(STORE_PATH, JSON.stringify(data, null, 2));
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

async function getRecord(firebasePath, defaultValue = null) {
  const remote = await request("GET", firebasePath);
  if (typeof remote !== "undefined") return remote === null ? defaultValue : remote;
  let cursor = readStore();
  for (const part of cleanPath(firebasePath).split("/")) {
    if (!cursor || typeof cursor !== "object" || !(part in cursor)) return defaultValue;
    cursor = cursor[part];
  }
  return cursor;
}

async function setRecord(firebasePath, value) {
  const remote = await request("PUT", firebasePath, value);
  if (typeof remote !== "undefined") return remote;
  const data = readStore();
  const [cursor, leaf] = walk(data, firebasePath, true);
  cursor[leaf] = value;
  writeStore(data);
  return value;
}

async function updateRecord(firebasePath, updates) {
  if (!updates || typeof updates !== "object" || Array.isArray(updates)) {
    const error = new Error("updates must be an object");
    error.statusCode = 400;
    throw error;
  }
  const remote = await request("PATCH", firebasePath, updates);
  if (typeof remote !== "undefined") return remote || updates;
  const data = readStore();
  const [cursor, leaf] = walk(data, firebasePath, true);
  const current = cursor[leaf] && typeof cursor[leaf] === "object" && !Array.isArray(cursor[leaf]) ? cursor[leaf] : {};
  cursor[leaf] = { ...current, ...updates };
  writeStore(data);
  return cursor[leaf];
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
