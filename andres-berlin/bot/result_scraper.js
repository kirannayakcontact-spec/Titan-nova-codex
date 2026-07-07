"use strict";

const { getCollection, pushRecord, setRecord } = require("./firebase");

let results = [];
let lastRunAt = null;

async function refreshResults() {
  const persisted = Object.values(await getCollection("scraper/results"));
  results = persisted.sort((a, b) => String(b.createdAt || "").localeCompare(String(a.createdAt || "")));
  const state = await getCollection("scraper/state");
  lastRunAt = state.lastRunAt || (results[0] && results[0].createdAt) || null;
}

async function ingestResult(payload) {
  if (!payload || !payload.event || typeof payload.result === "undefined") {
    const error = new Error("event and result are required");
    error.statusCode = 400;
    throw error;
  }
  await refreshResults();
  const result = { id: `${Date.now()}-${results.length + 1}`, ...payload, createdAt: new Date().toISOString() };
  await pushRecord("scraper/results", result, result.id);
  lastRunAt = result.createdAt;
  await setRecord("scraper/state", { lastRunAt });
  results.unshift(result);
  return result;
}

async function listResults(limit = 25) {
  await refreshResults();
  return results.slice(0, Math.max(1, Math.min(Number(limit) || 25, 100)));
}

async function scraperStatus() {
  const latest = await listResults(5);
  return { status: "ok", module: "result_scraper", lastRunAt, results: results.length, latest };
}

module.exports = { scraperStatus, ingestResult, listResults };
