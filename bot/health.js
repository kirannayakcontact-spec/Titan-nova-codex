"use strict";

// Titan Nova Gateway health helpers.
// Phase 1 module scaffold. Import-safe and connection-free.

const os = require("os");
const { loadGatewayConfig, startupWarnings } = require("./config");

const PHASE1_HEALTH_VERSION = "2026-07-06-phase1-gateway-health-module";

function buildGatewayHealth(extra = {}) {
  const config = loadGatewayConfig();
  const warnings = startupWarnings(config);
  return {
    status: warnings.length ? "warning" : "ok",
    version: PHASE1_HEALTH_VERSION,
    checkedAt: new Date().toISOString(),
    gateway: {
      entrypoint: "Gateway.js",
      modularPhase: "phase1-config-health-scaffold",
      behaviorChanged: false,
      host: config.host,
      port: config.port,
      appTz: config.appTz,
      uptimeSeconds: Math.round(process.uptime()),
      node: process.version,
      platform: process.platform,
      hostname: os.hostname(),
    },
    config: {
      firebaseFromEnv: config.firebaseFromEnv,
      firebaseUrlRedacted: config.firebaseUrlRedacted,
      gatewayTokenConfigured: config.gatewayTokenConfigured,
      gatewayAuthDisabled: config.gatewayAuthDisabled,
      productionMode: config.productionMode,
      resultScrapeEnabled: config.resultScrapeEnabled,
      businessDayCutoffHour: config.businessDayCutoffHour,
      schedulePollMs: config.schedulePollMs,
    },
    warnings,
    ...extra,
  };
}

module.exports = {
  PHASE1_HEALTH_VERSION,
  buildGatewayHealth,
};
