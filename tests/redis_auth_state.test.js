"use strict";

describe("Redis-backed WhatsApp auth adapter", () => {
  test("exports the persistent adapter and keeps Redis optional", () => {
    delete process.env.REDIS_URL;
    const store = require("../redis_auth_state.js");
    expect(typeof store.usePersistentAuthState).toBe("function");
  });
});
