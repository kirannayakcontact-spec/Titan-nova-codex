"use strict";

const results = [];
let lastRunAt = null;

function ingestResult(payload) {
  if (!payload || !payload.event || typeof payload.result === "undefined") {
    const error = new Error("event and result are required");
    error.statusCode = 400;
    throw error;
  }
  const result = { id: `${Date.now()}-${results.length + 1}`, ...payload, createdAt: new Date().toISOString() };
  results.unshift(result);
  lastRunAt = result.createdAt;
  return result;
}

function listResults(limit = 25) {
  return results.slice(0, Math.max(1, Math.min(Number(limit) || 25, 100)));
}

function scraperStatus() {
  return { status: "ok", module: "result_scraper", lastRunAt, results: results.length, latest: listResults(5) };
}

module.exports = { scraperStatus, ingestResult, listResults };
