"use strict";

const { getCollection, setRecord } = require("./firebase");

const jobs = new Map();

async function persistJob(job) {
  await setRecord(`scheduler/jobs/${job.name}`, serialize(job));
}

async function scheduleJob(name, intervalMs, handler = () => {}) {
  if (!name || !Number.isFinite(intervalMs) || intervalMs < 1000) {
    const error = new Error("name and intervalMs >= 1000 are required");
    error.statusCode = 400;
    throw error;
  }
  if (jobs.has(name)) clearInterval(jobs.get(name).timer);
  const job = { name, intervalMs, runs: 0, lastRunAt: null, nextRunAt: new Date(Date.now() + intervalMs).toISOString(), timer: null };
  job.timer = setInterval(async () => {
    job.runs += 1;
    job.lastRunAt = new Date().toISOString();
    job.nextRunAt = new Date(Date.now() + intervalMs).toISOString();
    await persistJob(job);
    handler(job);
  }, intervalMs);
  if (job.timer.unref) job.timer.unref();
  jobs.set(name, job);
  await persistJob(job);
  return serialize(job);
}

function serialize(job) {
  return { name: job.name, intervalMs: job.intervalMs, runs: job.runs, lastRunAt: job.lastRunAt, nextRunAt: job.nextRunAt };
}

async function schedulerStatus() {
  const persisted = Object.values(await getCollection("scheduler/jobs"));
  const current = new Map(persisted.map((job) => [job.name, job]));
  for (const job of jobs.values()) current.set(job.name, serialize(job));
  return { status: "ok", module: "scheduler", jobs: Array.from(current.values()) };
}

module.exports = { schedulerStatus, scheduleJob };
