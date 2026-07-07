"use strict";

const { firebaseStatus } = require("./firebase");
const { safetyStatus, evaluateMessage } = require("./safety");
const { schedulerStatus, scheduleJob } = require("./scheduler");
const { scraperStatus, ingestResult, listResults } = require("./result_scraper");
const { whatsappStatus, sendMessage, recordInbound } = require("./whatsapp");

function handleError(res, error) {
  res.status(error.statusCode || 500).json({ status: "error", error: error.message });
}

function asyncRoute(handler) {
  return async (req, res) => {
    try {
      await handler(req, res);
    } catch (error) {
      handleError(res, error);
    }
  };
}

function registerRoutes(app) {
  app.get("/api/firebase/status", (req, res) => res.json(firebaseStatus()));
  app.get("/api/safety/status", (req, res) => res.json(safetyStatus()));
  app.post("/api/safety/check", (req, res) => res.json(evaluateMessage(req.body || {})));
  app.get("/api/scheduler/status", asyncRoute(async (req, res) => res.json(await schedulerStatus())));
  app.post("/api/scheduler/jobs", asyncRoute(async (req, res) => {
    res.status(201).json(await scheduleJob(req.body.name, Number(req.body.intervalMs)));
  }));
  app.get("/api/result-scraper/status", asyncRoute(async (req, res) => res.json(await scraperStatus())));
  app.get("/api/result-scraper/results", asyncRoute(async (req, res) => res.json({ results: await listResults(req.query.limit) })));
  app.post("/api/result-scraper/results", asyncRoute(async (req, res) => {
    res.status(201).json(await ingestResult(req.body));
  }));
  app.get("/api/whatsapp/status", asyncRoute(async (req, res) => res.json(await whatsappStatus())));
  app.post("/api/whatsapp/messages", asyncRoute(async (req, res) => {
    const decision = evaluateMessage(req.body || {});
    if (!decision.allowed) return res.status(422).json({ status: "rejected", decision });
    return res.status(202).json(await sendMessage(req.body.to, req.body.message));
  }));
  app.post("/api/whatsapp/inbound", asyncRoute(async (req, res) => {
    res.status(201).json(await recordInbound(req.body.from, req.body.message));
  }));
}

module.exports = { registerRoutes };
