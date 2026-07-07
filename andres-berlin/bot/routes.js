"use strict";

const { firebaseStatus } = require("./firebase");
const { safetyStatus, evaluateMessage } = require("./safety");
const { schedulerStatus, scheduleJob } = require("./scheduler");
const { scraperStatus, ingestResult, listResults } = require("./result_scraper");
const { whatsappStatus, sendMessage, recordInbound } = require("./whatsapp");

function handleError(res, error) {
  res.status(error.statusCode || 500).json({ status: "error", error: error.message });
}

function registerRoutes(app) {
  app.get("/api/firebase/status", (req, res) => res.json(firebaseStatus()));
  app.get("/api/safety/status", (req, res) => res.json(safetyStatus()));
  app.post("/api/safety/check", (req, res) => res.json(evaluateMessage(req.body || {})));
  app.get("/api/scheduler/status", (req, res) => res.json(schedulerStatus()));
  app.post("/api/scheduler/jobs", (req, res) => {
    try { res.status(201).json(scheduleJob(req.body.name, Number(req.body.intervalMs))); } catch (error) { handleError(res, error); }
  });
  app.get("/api/result-scraper/status", (req, res) => res.json(scraperStatus()));
  app.get("/api/result-scraper/results", (req, res) => res.json({ results: listResults(req.query.limit) }));
  app.post("/api/result-scraper/results", (req, res) => {
    try { res.status(201).json(ingestResult(req.body)); } catch (error) { handleError(res, error); }
  });
  app.get("/api/whatsapp/status", (req, res) => res.json(whatsappStatus()));
  app.post("/api/whatsapp/messages", (req, res) => {
    try {
      const decision = evaluateMessage(req.body || {});
      if (!decision.allowed) return res.status(422).json({ status: "rejected", decision });
      return res.status(202).json(sendMessage(req.body.to, req.body.message));
    } catch (error) { return handleError(res, error); }
  });
  app.post("/api/whatsapp/inbound", (req, res) => res.status(201).json(recordInbound(req.body.from, req.body.message)));
}

module.exports = { registerRoutes };
