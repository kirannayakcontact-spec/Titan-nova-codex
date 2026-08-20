"use strict";

const { EVENT_ROUTES } = require("./session_config.js");

function registerBotRoutes(manager, app, auth){
  const guard = typeof auth === "function" ? auth : (req, res, next) => next();
  app.get("/api/bots/status", guard, (req, res) => res.json({status:"success", architecture:"5-bot-multi-session", bots:manager.snapshot()}));
  app.post("/api/bots/:role/reset", guard, async (req, res) => {
    try { res.json({status:"success", bot:await manager.reset(req.params.role)}); }
    catch (e) { res.status(400).json({status:"error", message:e.message}); }
  });
  app.post("/api/bots/send", guard, async (req, res) => {
    const body = req.body && typeof req.body === "object" && !Array.isArray(req.body) ? req.body : {};
    const event = String(body.eventType || "").trim();
    const role = EVENT_ROUTES[event];
    if (!role) return res.status(400).json({status:"error", message:"A valid eventType is required"});
    if (!String(body.to || "").trim()) return res.status(400).json({status:"error", message:"A recipient is required"});
    if (!String(body.text ?? "").trim()) return res.status(400).json({status:"error", message:"Message text is required"});
    try {
      await manager.send(role, body.to, body.text);
      res.json({status:"success", role, eventType:event});
    } catch (e) {
      const message = String(e?.message || e);
      const clientError = /required|valid whatsapp recipient|exceeds 4096|unknown bot role/i.test(message);
      res.status(clientError ? 400 : 503).json({status:"error", message});
    }
  });
}

module.exports = { registerBotRoutes };
