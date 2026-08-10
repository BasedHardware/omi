#!/usr/bin/env node
import { readFileSync } from "node:fs";

const expectedDomains = [
  "memories",
  "tasks",
  "conversations",
  "folders",
  "listen",
  "chat",
  "settings",
];
const exactKeys = (value, keys) =>
  value !== null &&
  typeof value === "object" &&
  !Array.isArray(value) &&
  Object.keys(value).sort().join("\0") === [...keys].sort().join("\0");
const fail = (reason) => {
  process.stderr.write(`ERROR: invalid native consumer evidence: ${reason}\n`);
  process.exit(1);
};

const args = process.argv.slice(2);
const take = (name) => {
  const index = args.indexOf(name);
  if (index < 0 || index + 1 >= args.length) fail(`missing ${name}`);
  return args[index + 1];
};
const file = take("--file");
const runId = take("--run-id");
const shell = take("--shell");
if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/u.test(runId)) fail("unsafe run id");
if (shell !== "macos" && shell !== "ios") fail("unknown shell");

let document;
try {
  document = JSON.parse(readFileSync(file, "utf8"));
} catch {
  fail("result is not readable JSON");
}
if (!exactKeys(document, ["schema", "runId", "rows"])) fail("document keys are not exact");
if (document.schema !== "omi.consumer-evidence.v1") fail("wrong schema");
if (document.runId !== runId) fail("wrong run id");
if (!Array.isArray(document.rows) || document.rows.length !== 7) fail("expected seven rows");

const seen = new Set();
for (const row of document.rows) {
  if (!exactKeys(row, [
    "runId", "shell", "domain", "fixture", "evidence", "observation",
    "shellTreeHash", "surfaceTreeHash",
  ])) fail("row keys are not exact");
  if (row.runId !== runId || row.shell !== shell) fail("wrong row identity");
  if (!expectedDomains.includes(row.domain) || seen.has(row.domain)) fail("missing or duplicate domain");
  seen.add(row.domain);
  if (row.fixture !== "none" || row.evidence !== "rendered-semantic") fail("non-live evidence row");
  if (!/^[0-9a-f]{40}$/u.test(row.shellTreeHash) || !/^[0-9a-f]{40}$/u.test(row.surfaceTreeHash)) {
    fail("invalid tree hash");
  }
  const observationKeys = row.domain === "listen"
    ? ["route", "state", "semantic", "transcript"]
    : ["route", "state", "semantic"];
  if (!exactKeys(row.observation, observationKeys)) fail("observation keys are not exact");
  if (row.observation.route !== row.domain || row.observation.state !== "ready") fail("observation identity is wrong");
  if (typeof row.observation.semantic !== "string" || row.observation.semantic.trim() === "" || Buffer.byteLength(row.observation.semantic) > 256) {
    fail("semantic is not bounded and non-empty");
  }
  if (row.domain === "listen" &&
      (typeof row.observation.transcript !== "string" || row.observation.transcript.trim() === "" || Buffer.byteLength(row.observation.transcript) > 1024)) {
    fail("Listen transcript is not bounded and non-empty");
  }
}
if (expectedDomains.some((domain) => !seen.has(domain))) fail("missing domain");
process.stdout.write(`consumer-evidence: valid run=${runId} shell=${shell} rows=7\n`);
