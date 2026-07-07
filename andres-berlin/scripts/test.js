#!/usr/bin/env node
"use strict";

const { spawnSync } = require("child_process");

function run(label, command, args, options = {}) {
  console.log(`\n> ${label}`);
  const result = spawnSync(command, args, {
    cwd: options.cwd || process.cwd(),
    env: { ...process.env, ...(options.env || {}) },
    stdio: "inherit",
    shell: false
  });
  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }
  if (result.status !== 0) process.exit(result.status || 1);
}

run("node syntax check", "npm", ["run", "check"]);
run("python firebase compile", "python3", ["-m", "py_compile", "backend/services/firebase.py"], {
  env: { PYTHONPATH: "." }
});
