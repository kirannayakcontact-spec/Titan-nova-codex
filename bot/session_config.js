"use strict";

const ROLES = Object.freeze(["owner_bot", "finance_bot", "game_bot", "result_bot"]);
const RESTRICTED_ROLES = Object.freeze(["finance_bot", "result_bot"]);
const EVENT_ROUTES = Object.freeze({
  crash: "owner_bot",
  deposit: "finance_bot",
  withdrawal: "finance_bot",
  game: "game_bot",
  result: "result_bot",
});
const ROLE_COLORS = Object.freeze({
  owner_bot: "\x1b[35m",
  finance_bot: "\x1b[33m",
  game_bot: "\x1b[36m",
  result_bot: "\x1b[32m",
});
const RESET_COLOR = "\x1b[0m";

module.exports = { ROLES, RESTRICTED_ROLES, EVENT_ROUTES, ROLE_COLORS, RESET_COLOR };
