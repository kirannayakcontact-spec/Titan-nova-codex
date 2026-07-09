"use strict";

// Titan Nova Gateway Firebase guard: retry transient Firebase failures and keep
// cache/write diagnostics in a small JSONL file.
(function titanGatewayFirebaseGuard(){
  if (global.__TITAN_GATEWAY_FIREBASE_GUARD_V1__) return;
  global.__TITAN_GATEWAY_FIREBASE_GUARD_V1__ = true;

  const fs = require("fs");
  const path = require("path");
  const axios = require("axios");
  const VERSION = "2026-07-09-gateway-firebase-guard-v1";
  const STATE_DIR = process.env.TITAN_STATE_DIR || process.cwd();
  const LOG_FILE = path.join(STATE_DIR, "titan_gateway_firebase_guard.jsonl");
  const RETRY_CODES = new Set([408, 425, 429, 500, 502, 503, 504]);
  const MAX_RETRIES = Math.max(1, Number(process.env.TITAN_GATEWAY_FIREBASE_RETRIES || 3) || 3);

  function event(kind, severity, message, detail){
    const rec = {time:new Date().toISOString(), version:VERSION, kind:String(kind||"event").slice(0,80), severity:String(severity||"info"), message:String(message||"").slice(0,500), detail:detail||{}};
    try { fs.mkdirSync(STATE_DIR, {recursive:true}); fs.appendFileSync(LOG_FILE, JSON.stringify(rec) + "\n"); } catch (_) {}
    try { console.log((severity === "error" ? "❌" : severity === "warning" ? "⚠️" : "✅"), "Gateway Firebase Guard:", rec.message); } catch (_) {}
    return rec;
  }

  function isFirebaseUrl(url){
    return /firebaseio\.com|firebasedatabase\.app/i.test(String(url || ""));
  }

  function methodOf(config){
    return String((config && config.method) || "get").toUpperCase();
  }

  function shouldRetry(config, err){
    const method = methodOf(config);
    if (!["GET", "PUT", "PATCH", "DELETE"].includes(method)) return false;
    if (!isFirebaseUrl(config && config.url)) return false;
    const status = err && err.response && err.response.status;
    if (!status) return true;
    return RETRY_CODES.has(Number(status));
  }

  function withFirebaseHeaders(config){
    if (!config || !isFirebaseUrl(config.url)) return config;
    const headers = Object.assign({}, config.headers || {});
    headers["Cache-Control"] = headers["Cache-Control"] || "no-cache, no-store";
    headers["Pragma"] = headers["Pragma"] || "no-cache";
    config.headers = headers;
    config.timeout = Math.max(Number(config.timeout || 0), Number(process.env.TITAN_GATEWAY_FIREBASE_TIMEOUT_MS || 15000) || 15000);
    return config;
  }

  const originalRequest = axios.request.bind(axios);
  async function guardedRequest(config){
    config = withFirebaseHeaders(Object.assign({}, config || {}));
    if (!isFirebaseUrl(config.url)) return originalRequest(config);
    let lastErr;
    for (let attempt = 0; attempt < MAX_RETRIES; attempt++){
      const started = Date.now();
      try {
        const res = await originalRequest(config);
        const ms = Date.now() - started;
        if (res && res.status && RETRY_CODES.has(Number(res.status)) && attempt + 1 < MAX_RETRIES){
          event("firebase_http_retry", "warning", `Firebase ${methodOf(config)} HTTP ${res.status}; retrying`, {attempt:attempt+1, ms, urlTail:String(config.url).slice(-90)});
          await new Promise(r => setTimeout(r, 180 * (attempt + 1)));
          continue;
        }
        return res;
      } catch (err) {
        lastErr = err;
        if (shouldRetry(config, err) && attempt + 1 < MAX_RETRIES){
          const status = err && err.response && err.response.status;
          event("firebase_exception_retry", "warning", `Firebase ${methodOf(config)} ${status ? "HTTP " + status : "network error"}; retrying`, {attempt:attempt+1, message:String(err && err.message || err).slice(0,220), urlTail:String(config.url).slice(-90)});
          await new Promise(r => setTimeout(r, 220 * (attempt + 1)));
          continue;
        }
        event("firebase_request_failed", "error", `Firebase ${methodOf(config)} failed: ${err && err.message ? err.message : err}`, {status:err && err.response && err.response.status, urlTail:String(config.url).slice(-90)});
        throw err;
      }
    }
    throw lastErr;
  }

  axios.request = guardedRequest;
  for (const method of ["get", "delete", "head", "options"]){
    const upper = method.toUpperCase();
    axios[method] = function(url, config){ return guardedRequest(Object.assign({}, config || {}, {method:upper, url})); };
  }
  for (const method of ["post", "put", "patch"]){
    const upper = method.toUpperCase();
    axios[method] = function(url, data, config){ return guardedRequest(Object.assign({}, config || {}, {method:upper, url, data})); };
  }

  event("gateway_firebase_guard_loaded", "info", `Gateway Firebase guard loaded ${VERSION}`, {maxRetries:MAX_RETRIES, logFile:LOG_FILE});
})();
