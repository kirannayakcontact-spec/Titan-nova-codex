"use strict";

const jobs = new Map();

function scheduleJob(name, intervalMs, handler = () => {}) {
  if (!name || !Number.isFinite(intervalMs) || intervalMs < 1000) {
    const error = new Error("name and intervalMs >= 1000 are required");
    error.statusCode = 400;
    throw error;
  }
  if (jobs.has(name)) clearInterval(jobs.get(name).timer);
  const job = { name, intervalMs, runs: 0, lastRunAt: null, nextRunAt: new Date(Date.now() + intervalMs).toISOString(), timer: null };
  job.timer = setInterval(() => {
    job.runs += 1;
    job.lastRunAt = new Date().toISOString();
    job.nextRunAt = new Date(Date.now() + intervalMs).toISOString();
    handler(job);
  }, intervalMs);
  if (job.timer.unref) job.timer.unref();
  jobs.set(name, job);
  return serialize(job);
}

function serialize(job) {
  return { name: job.name, intervalMs: job.intervalMs, runs: job.runs, lastRunAt: job.lastRunAt, nextRunAt: job.nextRunAt };
}

function schedulerStatus() {
  return { status: "ok", module: "scheduler", jobs: Array.from(jobs.values()).map(serialize) };
}

module.exports = { schedulerStatus, scheduleJob };
