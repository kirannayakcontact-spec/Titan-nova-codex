"use strict";

const express = require("express");

const { getConfig } = require("./config");
const { registerRoutes } = require("./routes");

function createGateway() {
  const config = getConfig();
  const app = express();
  app.use(express.json({ limit: "1mb" }));

  app.get("/health", (req, res) => {
    res.json({ status: "ok", app: config.appName });
  });

  registerRoutes(app);
  return { app, config };
}

function startGateway() {
  const { app, config } = createGateway();
  app.listen(config.port, config.host, () => {
    console.log(`${config.appName} gateway running at http://${config.host}:${config.port}`);
  });
}

module.exports = { createGateway, startGateway };
