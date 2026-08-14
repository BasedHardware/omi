#!/usr/bin/env node
// LIFECYCLE: permanent
//
// Final arbiter for the direct single-service integration run. The report never
// invents evidence: it validates the platform readiness record, requires both
// structured shell results, and joins the exact producer/consumer matrix.

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  MATRIX_SIZE,
  MATRIX_REPORT_SCHEMA,
  arbitrateEvidence,
  rawRunIdFailure,
  validateServiceReadiness,
} from "./evidence-matrix.mjs";

export const RUN_REPORT_SCHEMA_VERSION = 3;

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
function exactKeys(value, expected, label, failures) {
  if (!isObject(value)) {
    failures.push(`${label} must be an object`);
    return;
  }
  const missing = expected.filter((key) => !Object.hasOwn(value, key));
  const extra = Object.keys(value).filter((key) => !expected.includes(key));
  if (missing.length > 0) failures.push(`${label} is missing field(s): ${missing.join(", ")}`);
  if (extra.length > 0) failures.push(`${label} has non-schema field(s): ${extra.join(", ")}`);
}

const assertion = (name, claim, measuredBy, corroboratedBy, result, detail) => Object.freeze({
  name,
  claim,
  measuredBy,
  corroboratedBy,
  singleMeasurement: corroboratedBy === null,
  result,
  detail,
});

export function buildReport(facts, { readinessRecord = facts?.service?.readiness } = {}) {
  if (facts === null || typeof facts !== "object" || Array.isArray(facts)) {
    throw new TypeError("run facts must be an object");
  }
  const factsFailures = [];
  exactKeys(facts, [
    "schema", "runId", "startedAt", "finishedAt", "expectedShellTreeHash",
    "expectedSurfaceTreeHash", "service", "launchers", "consumer", "producer",
  ], "run facts", factsFailures);
  if (facts.schema !== "omi.dev-stack-facts.v1") factsFailures.push("run facts schema is wrong");
  const runIdFailure = rawRunIdFailure(facts.runId);
  if (runIdFailure) factsFailures.push(runIdFailure);
  exactKeys(facts.service, ["databasePath", "launchedPid", "reachableAfter"], "run facts service", factsFailures);
  exactKeys(facts.launchers, ["macos", "ios"], "run facts launchers", factsFailures);
  for (const shell of ["macos", "ios"]) {
    exactKeys(facts.launchers?.[shell], ["status", "exitCode"], `${shell} launcher outcome`, factsFailures);
  }
  const readiness = validateServiceReadiness(readinessRecord, {
    runId: facts.runId,
    databasePath: facts.service?.databasePath,
    pid: facts.service?.launchedPid,
  });
  const matrix = arbitrateEvidence({
    runId: facts.runId,
    consumer: facts.consumer,
    producer: facts.producer,
    expectedShellTreeHash: facts.expectedShellTreeHash,
    expectedSurfaceTreeHash: facts.expectedSurfaceTreeHash,
  });
  const shellFailures = ["macos", "ios"].flatMap((shell) => {
    const result = facts.launchers?.[shell];
    if (result === null || result === undefined) return [`${shell} launcher outcome is missing`];
    if (result.status !== "pass") return [`${shell} launcher status is ${JSON.stringify(result.status)}`];
    if (!Number.isInteger(result.exitCode) || result.exitCode !== 0) return [`${shell} launcher exitCode is ${JSON.stringify(result.exitCode)}`];
    return [];
  });
  const backendAlive = facts.service?.reachableAfter === true;

  const assertions = [
    assertion(
      "facts_integrity",
      "the final host facts contain only the exact safe wrapper metadata",
      "launcher: exact schema-v1 host facts without readiness credentials or origins",
      "report: independently revalidates raw run identity and every wrapper key",
      factsFailures.length === 0 ? "pass" : "fail",
      factsFailures.join("; ") || "final host facts use the exact safe schema",
    ),
    assertion(
      "direct_service_readiness",
      "the exact platform dev-server executable owns the one run-scoped SQLite service",
      "platform: versioned readiness record written by apps/service/bin/dev-server.ts",
      "launcher: live PID and loopback readiness probe after shell collection",
      readiness.ok && backendAlive ? "pass" : "fail",
      [...readiness.failures, ...(backendAlive ? [] : ["service was not reachable after shell collection"])].join("; ") || "direct service readiness record and live probe agree",
    ),
    assertion(
      "two_shell_results",
      "macOS and iOS both built, launched, and returned structured results for this run",
      "shell launchers: separate host-owned exit outcomes after native validation",
      "consumer matrix: seven rendered semantic rows from each shell",
      shellFailures.length === 0 ? "pass" : "fail",
      shellFailures.join("; ") || "macos and ios structured results both passed",
    ),
    assertion(
      "exact_evidence_matrix",
      `the same run has exactly ${MATRIX_SIZE} joined shell/domain rows`,
      "consumer: rendered semantic observations with shell and surface tree hashes",
      "producer: successful served outcomes joined by run + shell + domain",
      matrix.result,
      matrix.failures.join("; ") || `${matrix.rowCount}/${MATRIX_SIZE} exact coordinates joined`,
    ),
    assertion(
      "no_generation_mismatch",
      "each evidence coordinate rendered the domain it names from the measured surface generation",
      "consumer: observation.route plus surfaceTreeHash from the live webview",
      "git/build provenance: expected surface tree hash for this run",
      matrix.failures.some((failure) => /rendered route|surface tree hash/.test(failure)) ? "fail" : "pass",
      matrix.failures.filter((failure) => /rendered route|surface tree hash/.test(failure)).join("; ") || "all rendered domains and surface tree hashes agree",
    ),
  ];

  const failed = assertions.filter((row) => row.result === "fail");
  const report = {
    schema: RUN_REPORT_SCHEMA_VERSION,
    run: {
      id: facts.runId,
      startedAt: facts.startedAt,
      finishedAt: facts.finishedAt ?? new Date().toISOString(),
    },
    result: failed.length === 0 ? "pass" : "fail",
    service: {
      executable: readinessRecord?.executable ?? null,
      databasePath: facts.service?.databasePath ?? null,
      pid: readinessRecord?.pid ?? null,
      readinessSchema: readinessRecord?.schema ?? null,
      reachableAfter: backendAlive,
    },
    launchers: {
      macos: facts.launchers?.macos ?? null,
      ios: facts.launchers?.ios ?? null,
    },
    evidence: matrix,
    assertions,
  };
  return Object.freeze(report);
}

export function nextActions(report) {
  const actions = [];
  if (report.assertions.some((row) => row.name === "direct_service_readiness" && row.result === "fail")) {
    actions.push("Implement the platform companion readiness record on apps/service/bin/dev-server.ts; no alternate launcher is accepted.");
  }
  if (report.assertions.some((row) => row.name === "two_shell_results" && row.result === "fail")) {
    actions.push("Run both core shell launchers and collect their versioned structured results; a missing simulator or shell result is a failure.");
  }
  if (report.evidence.result === "fail") {
    actions.push("Repair the named producer/consumer coordinate; aggregate traffic, fixtures, readiness, and screenshots cannot replace it.");
  }
  return actions;
}

function renderHuman(report) {
  const lines = [
    `run ${report.run.id}: ${report.result.toUpperCase()}`,
    `service ${report.service.executable ?? "missing"} pid ${report.service.pid ?? "missing"}`,
    `matrix ${report.evidence.rowCount}/${MATRIX_SIZE} (${MATRIX_REPORT_SCHEMA})`,
  ];
  for (const row of report.assertions) lines.push(`${row.result === "pass" ? "PASS" : "FAIL"} ${row.name}: ${row.detail}`);
  for (const action of nextActions(report)) lines.push(`NEXT: ${action}`);
  return `${lines.join("\n")}\n`;
}

function parseCli(argv) {
  const value = (name) => {
    const index = argv.indexOf(name);
    return index === -1 ? null : argv[index + 1];
  };
  return {
    factsPath: value("--facts"),
    readinessPath: value("--readiness"),
    outPath: value("--out"),
    json: argv.includes("--json"),
    assert: argv.includes("--assert"),
  };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const cli = parseCli(process.argv.slice(2));
  if (!cli.factsPath || !cli.readinessPath) {
    process.stderr.write("usage: run-report.mjs --facts <path> --readiness <path> [--out <path>] [--json] [--assert]\n");
    process.exit(2);
  }
  let facts;
  let readinessRecord;
  try {
    facts = JSON.parse(readFileSync(cli.factsPath, "utf8"));
    readinessRecord = JSON.parse(readFileSync(cli.readinessPath, "utf8"));
  } catch (error) {
    process.stderr.write(`could not read run facts: ${error.message}\n`);
    process.exit(1);
  }
  const report = buildReport(facts, { readinessRecord });
  if (cli.outPath) writeFileSync(cli.outPath, `${JSON.stringify(report, null, 2)}\n`);
  process.stdout.write(cli.json ? `${JSON.stringify(report, null, 2)}\n` : renderHuman(report));
  if (cli.assert && report.result !== "pass") process.exit(1);
}
