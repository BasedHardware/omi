#!/usr/bin/env node
// LIFECYCLE: permanent
// Thin file/CLI plumbing around evidence-matrix.mjs. Verdict logic stays in the
// imported module so the shell launcher cannot grow a second arbiter in bash.

import { readFileSync, writeFileSync } from "node:fs";

import {
  CONSUMER_EVIDENCE_SCHEMA,
  SERVICE_EXECUTABLE,
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

if (command === "validate-readiness") {
  const path = flag("--record");
  const runId = flag("--run-id");
  const databasePath = flag("--database");
  const pid = Number(flag("--pid"));
  if (!path || !runId || !databasePath || !Number.isSafeInteger(pid) || pid <= 0) {
    process.stderr.write("validate-readiness needs --record, --run-id, --database, and positive integer --pid\n");
    process.exit(2);
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
  process.stdout.write(`${JSON.stringify({
    pid: record.pid,
    baseUrl: record.baseUrl,
    devToken: record.devToken,
    ownerAccountId: record.ownerAccountId,
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
  const macos = readJson(macosPath);
  const ios = readJson(iosPath);
  for (const [name, result] of [["macos", macos], ["ios", ios]]) {
    if (result.schema !== CONSUMER_EVIDENCE_SCHEMA) throw new Error(`${name} result has wrong schema`);
    if (result.runId !== runId) throw new Error(`${name} result has wrong runId`);
    if (result.shell !== name) throw new Error(`${name} result has wrong shell attribution`);
    if (!Array.isArray(result.rows)) throw new Error(`${name} result has no rows`);
  }
  writeJson(out, {
    schema: CONSUMER_EVIDENCE_SCHEMA,
    runId,
    rows: [...macos.rows, ...ios.rows],
  });
} else if (command === "stamp-shell") {
  const path = flag("--file");
  const shell = flag("--shell");
  const runId = flag("--run-id");
  const exitCode = Number(flag("--exit-code"));
  if (!path || !["macos", "ios"].includes(shell) || !runId || !Number.isInteger(exitCode)) {
    process.stderr.write("stamp-shell needs --file, --shell, --run-id, and integer --exit-code\n");
    process.exit(2);
  }
  const value = readJson(path);
  if (value.schema !== CONSUMER_EVIDENCE_SCHEMA) throw new Error(`${shell} result has wrong schema`);
  if (value.runId !== runId || value.shell !== shell) throw new Error(`${shell} result has wrong host attribution`);
  writeJson(path, { ...value, status: exitCode === 0 ? "pass" : "fail", exitCode });
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
  process.stderr.write("usage: evidence-cli.mjs <validate-readiness|stamp-shell|merge-consumer|mutate> ...\n");
  process.exit(2);
}
