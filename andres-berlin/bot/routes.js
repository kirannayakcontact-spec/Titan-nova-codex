"use strict";

const { firebaseStatus } = require("./firebase");
const { safetyStatus } = require("./safety");
const { schedulerStatus } = require("./scheduler");
const { scraperStatus } = require("./result_scraper");
const { whatsappStatus } = require("./whatsapp");

function registerRoutes(app) {
  app.get("/api/firebase/status", (req, res) => res.json(firebaseStatus()));
  app.get("/api/safety/status", (req, res) => res.json(safetyStatus()));
  app.get("/api/scheduler/status", (req, res) => res.json(schedulerStatus()));
  app.get("/api/result-scraper/status", (req, res) => res.json(scraperStatus()));
  app.get("/api/whatsapp/status", (req, res) => res.json(whatsappStatus()));
}

module.exports = { registerRoutes };
