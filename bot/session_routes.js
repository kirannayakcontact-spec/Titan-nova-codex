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
    try {
      const event = String(req.body.eventType || "");
      const role = EVENT_ROUTES[event];
      if (!role) return res.status(400).json({status:"error", message:"A valid eventType is required"});
      await manager.send(role, req.body.to, req.body.text);
      res.json({status:"success", role, eventType:event});
    } catch (e) { res.status(503).json({status:"error", message:e.message}); }
  });
}

module.exports = { registerBotRoutes };
