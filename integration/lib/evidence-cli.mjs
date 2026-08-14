#!/usr/bin/env node
// LIFECYCLE: permanent
// Thin file/CLI plumbing around evidence-matrix.mjs. Verdict logic stays in the
// imported module so the shell launcher cannot grow a second arbiter in bash.

import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  CONSUMER_EVIDENCE_SCHEMA,
  SERVICE_EXECUTABLE,
  rawRunIdFailure,
  validateServiceReadiness,
} from "./evidence-matrix.mjs";

const argv = process.argv.slice(2);
const command = argv.shift();
const flag = (name) => {
  const index = argv.indexOf(name);
  return index === -1 ? null : argv[index + 1];
};
const readJson = (path) => JSON.parse(readFileSync(path, "utf8"));
const writeJson = (path, value) => writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
const validator = resolve(dirname(fileURLToPath(import.meta.url)), "../../core/shells/tools/validate-consumer-evidence.mjs");

function requireRawRunId(runId) {
  const failure = rawRunIdFailure(runId);
  if (failure) throw new Error(failure);
}

function deriveNativeShell(document, label) {
  if (!Array.isArray(document?.rows) || document.rows.length !== 7) {
    throw new Error(`${label} native document must contain exactly seven rows`);
  }
  const shells = new Set(document.rows.map((row) => row?.shell));
  if (shells.size !== 1) throw new Error(`${label} native rows do not carry one consistent shell`);
  const [shell] = shells;
  if (shell !== "macos" && shell !== "ios") throw new Error(`${label} native rows carry an unknown shell`);
  return shell;
}

function validateNativeDocument(path, label, runId, expectedShell) {
  const before = readFileSync(path);
  const document = JSON.parse(before.toString("utf8"));
  const shell = deriveNativeShell(document, label);
  if (shell !== expectedShell) throw new Error(`${label} native rows have wrong shell attribution`);
  const result = spawnSync(process.execPath, [validator, "--file", path, "--run-id", runId, "--shell", shell], {
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || `${label} native validator failed`).trim());
  }
  const after = readFileSync(path);
  if (!before.equals(after)) throw new Error(`${label} native document bytes changed during validation`);
  return document;
}

if (command === "validate-run-id") {
  const runId = flag("--run-id");
  try {
    requireRawRunId(runId);
    process.stdout.write(`${runId}\n`);
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exit(1);
  }
} else if (command === "validate-readiness") {
  const path = flag("--record");
  const runId = flag("--run-id");
  const databasePath = flag("--database");
  const pid = Number(flag("--pid"));
  const tokenOut = flag("--token-out");
  if (!path || !runId || !databasePath || !tokenOut || !Number.isSafeInteger(pid) || pid <= 0) {
    process.stderr.write("validate-readiness needs --record, --run-id, --database, --token-out, and positive integer --pid\n");
    process.exit(2);
  }
  try {
    requireRawRunId(runId);
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exit(1);
  }
  const record = readJson(path);
  const result = validateServiceReadiness(record, {
    runId,
    databasePath,
    pid,
    executable: SERVICE_EXECUTABLE,
  });
  if (!result.ok) {
    process.stderr.write(`${result.failures.join("\n")}\n`);
    process.exit(1);
  }
  writeFileSync(tokenOut, record.devToken, { mode: 0o600, flag: "wx" });
  process.stdout.write(`${JSON.stringify({
    pid: record.pid,
    runId: record.runId,
    executable: record.executable,
  })}\n`);
} else if (command === "merge-consumer") {
  const macosPath = flag("--macos");
  const iosPath = flag("--ios");
  const runId = flag("--run-id");
  const out = flag("--out");
  if (!macosPath || !iosPath || !runId || !out) {
    process.stderr.write("merge-consumer needs --macos, --ios, --run-id, and --out\n");
    process.exit(2);
  }
  requireRawRunId(runId);
  const macos = validateNativeDocument(macosPath, "macos", runId, "macos");
  const ios = validateNativeDocument(iosPath, "ios", runId, "ios");
  writeJson(out, {
    schema: CONSUMER_EVIDENCE_SCHEMA,
    runId,
    rows: [...macos.rows, ...ios.rows],
  });
} else if (command === "mutate") {
  const path = flag("--file");
  const kind = flag("--kind");
  if (!path || !kind) {
    process.stderr.write("mutate needs --file and --kind\n");
    process.exit(2);
  }
  const value = readJson(path);
  if (kind === "stale-dist") value.rows[0].surfaceTreeHash = "0".repeat(40);
  else if (kind === "generation-mismatch") value.rows[0].observation.route = "tasks";
  else throw new Error(`unknown mutation ${kind}`);
  writeJson(path, value);
} else {
  process.stderr.write("usage: evidence-cli.mjs <validate-run-id|validate-readiness|merge-consumer|mutate> ...\n");
  process.exit(2);
}
