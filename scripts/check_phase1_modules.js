"use strict";

const assert = require("assert");
const { loadGatewayConfig, startupWarnings } = require("../bot/config");
const { buildGatewayHealth } = require("../bot/health");

const config = loadGatewayConfig();
assert.ok(config.firebaseUrl.endsWith(".json"), "firebaseUrl must end with .json");
assert.ok(Array.isArray(startupWarnings(config)), "startupWarnings must return an array");

const health = buildGatewayHealth();
assert.strictEqual(health.gateway.entrypoint, "Gateway.js");
assert.strictEqual(health.gateway.behaviorChanged, false);

console.log("Phase 1 bot modules OK");
