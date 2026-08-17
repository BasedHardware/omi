#!/usr/bin/env node
// Invoker for every frontend `node --test` script.
//
// Per-test: `--test-timeout` fails an incomplete test red.
// Per-file: `--import` of node-test-hang-guard.mjs dumps leftover handles.
// Per-run: this process fails red if the test runner itself never returns.
// Isolation is process so a leaked handle is attributed to one file.

import { spawn } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const DEFAULT_TEST_TIMEOUT_MS = 120_000;
const DEFAULT_RUN_TIMEOUT_MS = 15 * 60 * 1000;
const RUN_HANG_MARKER = "TEST RUN HANG:";

function positiveMs(raw, fallback, name) {
  if (raw == null || raw === "") return fallback;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    process.stderr.write(`${name} must be a positive number of milliseconds, got ${JSON.stringify(raw)}\n`);
    process.exit(2);
  }
  return parsed;
}

const guardPath = fileURLToPath(new URL("./node-test-hang-guard.mjs", import.meta.url));
const testTimeoutMs = positiveMs(process.env.OMI_TEST_TIMEOUT_MS, DEFAULT_TEST_TIMEOUT_MS, "OMI_TEST_TIMEOUT_MS");
const runTimeoutMs = positiveMs(process.env.OMI_TEST_RUN_TIMEOUT_MS, DEFAULT_RUN_TIMEOUT_MS, "OMI_TEST_RUN_TIMEOUT_MS");
const files = process.argv.slice(2);
if (files.length === 0) {
  process.stderr.write("usage: run-node-test.mjs <test-glob-or-file>...\n");
  process.exit(2);
}

const child = spawn(
  process.execPath,
  [
    "--import",
    pathToFileURL(guardPath).href,
    `--test-timeout=${testTimeoutMs}`,
    "--experimental-test-isolation=process",
    "--test",
    ...files,
  ],
  {
    stdio: "inherit",
    env: (() => {
      const env = { ...process.env };
      delete env.NODE_TEST_CONTEXT;
      return env;
    })(),
  },
);

let timedOut = false;
const runTimer = setTimeout(() => {
  timedOut = true;
  const pid = child.pid;
  process.stderr.write(
    `${RUN_HANG_MARKER} node --test still running after ${runTimeoutMs}ms\n` +
      `  runner pid: ${pid ?? "(unknown)"}\n` +
      `  argv: ${files.join(" ")}\n`,
  );
  if (pid) {
    try { process.kill(pid, "SIGTERM"); } catch { /* already gone */ }
    setTimeout(() => {
      try { process.kill(pid, "SIGKILL"); } catch { /* already gone */ }
    }, 2_000).unref();
  }
}, runTimeoutMs);

child.on("error", (error) => {
  clearTimeout(runTimer);
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  clearTimeout(runTimer);
  if (timedOut) process.exit(1);
  if (signal) process.exit(1);
  process.exit(code ?? 1);
});
