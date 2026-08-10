// LIFECYCLE: permanent

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CONSUMER_EVIDENCE_SCHEMA,
  DOMAINS,
  PRODUCER_EVIDENCE_SCHEMA,
  SERVICE_BASE_URL,
  SERVICE_EXECUTABLE,
  SERVICE_READINESS_SCHEMA,
  SHELLS,
  deterministicListenAudio,
} from "./evidence-matrix.mjs";
import { buildReport } from "./run-report.mjs";

const RUN = "run-report-test";
const TREE = "a".repeat(40);
const SURFACE = "b".repeat(40);
const DB = "/tmp/omi-run-report-test/service.sqlite";

function facts() {
  const consumerRows = SHELLS.flatMap((shell) => DOMAINS.map((domain) => ({
    runId: RUN,
    shell,
    domain,
    fixture: "none",
    evidence: "rendered-semantic",
    observation: {
      route: domain,
      state: "ready",
      semantic: `${domain} semantic text`,
      ...(domain === "listen" ? { transcript: "deterministic transcript" } : {}),
    },
    shellTreeHash: TREE,
    surfaceTreeHash: SURFACE,
  })));
  const producerRows = SHELLS.flatMap((shell) => DOMAINS.map((domain) => ({
    runId: RUN,
    shell,
    domain,
    evidence: "served-outcome",
    ...(domain === "listen" ? {
      listen: {
        protocolReady: 1,
        acceptedBinary: 1,
        acceptedBinaryBytes: deterministicListenAudio().byteLength,
      },
    } : { http: { successful: 1 } }),
    ...(domain === "chat" ? { chat: { acceptedAdmission: 1 } } : {}),
  })));
  return {
    runId: RUN,
    startedAt: "2026-08-10T00:00:00.000Z",
    expectedShellTreeHash: TREE,
    expectedSurfaceTreeHash: SURFACE,
    service: {
      databasePath: DB,
      launchedPid: 123,
      reachableAfter: true,
      readiness: {
        schema: SERVICE_READINESS_SCHEMA,
        runId: RUN,
        executable: SERVICE_EXECUTABLE,
        baseUrl: SERVICE_BASE_URL,
        databasePath: DB,
        pid: 123,
        evidencePath: "/v1/qa/evidence",
        devToken: "local-token",
        ownerAccountId: "local-owner",
      },
    },
    shells: {
      macos: { shell: "macos", runId: RUN, status: "pass", exitCode: 0 },
      ios: { shell: "ios", runId: RUN, status: "pass", exitCode: 0 },
    },
    consumer: { schema: CONSUMER_EVIDENCE_SCHEMA, runId: RUN, rows: consumerRows },
    producer: { schema: PRODUCER_EVIDENCE_SCHEMA, runId: RUN, rows: producerRows },
  };
}

function named(report, name) {
  return report.assertions.find((row) => row.name === name);
}

test("healthy direct-service two-shell report passes with no nullable shell", () => {
  const report = buildReport(facts());
  assert.equal(report.result, "pass");
  assert.equal(report.shells.macos.status, "pass");
  assert.equal(report.shells.ios.status, "pass");
  assert.equal(report.evidence.rows.length, 14);
});

test("RED-PROOF dead-backend: readiness history cannot replace a live final probe", () => {
  const input = facts();
  input.service.reachableAfter = false;
  const report = buildReport(input);
  assert.equal(report.result, "fail");
  assert.equal(named(report, "direct_service_readiness").result, "fail");
  assert.match(named(report, "direct_service_readiness").detail, /not reachable/);
});

test("RED-PROOF stale-dist: a stale surface tree makes the final report red", () => {
  const input = facts();
  input.consumer.rows[0].surfaceTreeHash = "c".repeat(40);
  const report = buildReport(input);
  assert.equal(report.result, "fail");
  assert.equal(named(report, "exact_evidence_matrix").result, "fail");
  assert.match(named(report, "no_generation_mismatch").detail, /surface tree hash/);
});

test("RED-PROOF generation-mismatch: a coordinate rendered as another domain", () => {
  const input = facts();
  input.consumer.rows[0].observation.route = "tasks";
  const report = buildReport(input);
  assert.equal(report.result, "fail");
  assert.equal(named(report, "no_generation_mismatch").result, "fail");
  assert.match(named(report, "no_generation_mismatch").detail, /rendered route/);
});

test("RED-PROOF ios:null is an explicit shell failure even with fourteen rows", () => {
  const input = facts();
  input.shells.ios = null;
  const report = buildReport(input);
  assert.equal(report.result, "fail");
  assert.match(named(report, "two_shell_results").detail, /ios structured result is missing/);
});

test("RED-PROOF reports and receipts cannot copy forbidden producer content or readiness secrets", () => {
  const input = facts();
  input.service.readiness.devToken = "secret-readiness-token";
  input.service.readiness.ownerAccountId = "secret-owner-account";
  const listen = input.producer.rows.find((row) => row.shell === "macos" && row.domain === "listen").listen;
  listen.transcript = "secret-producer-transcript";
  listen.prompt = "secret-user-prompt";
  const report = buildReport(input);
  assert.equal(report.result, "fail");
  const serialized = JSON.stringify(report);
  assert.doesNotMatch(serialized, /secret-readiness-token|secret-owner-account/);
  assert.doesNotMatch(serialized, /secret-producer-transcript|secret-user-prompt/);
});

test("every report assertion names its independent measurements", () => {
  const report = buildReport(facts());
  for (const row of report.assertions) {
    assert.ok(row.claim);
    assert.ok(row.measuredBy);
    assert.ok(row.corroboratedBy);
    assert.equal(row.singleMeasurement, false);
  }
});
