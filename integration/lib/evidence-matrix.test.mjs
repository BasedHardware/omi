// LIFECYCLE: permanent
//
// Red-proofs for the exact two-shell/seven-domain arbiter. Each test names the
// mutation that must turn a seemingly healthy receipt red.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CONSUMER_EVIDENCE_SCHEMA,
  DOMAINS,
  MATRIX_SIZE,
  PRODUCER_EVIDENCE_SCHEMA,
  SERVICE_BASE_URL,
  SERVICE_EXECUTABLE,
  SERVICE_READINESS_SCHEMA,
  SHELLS,
  arbitrateEvidence,
  deterministicListenAudio,
  validateServiceReadiness,
} from "./evidence-matrix.mjs";

const RUN = "run-evidence-test";
const TREE = "1".repeat(40);
const SURFACE = "2".repeat(40);

function healthyConsumer() {
  return {
    schema: CONSUMER_EVIDENCE_SCHEMA,
    runId: RUN,
    rows: SHELLS.flatMap((shell) => DOMAINS.map((domain) => ({
      runId: RUN,
      shell,
      domain,
      fixture: "none",
      evidence: "rendered-semantic",
      observation: {
        route: domain,
        state: "ready",
        semantic: `${domain} rendered deterministic local content`,
        ...(domain === "listen" ? { transcript: "deterministic audio accepted" } : {}),
      },
      shellTreeHash: TREE,
      surfaceTreeHash: SURFACE,
    }))),
  };
}

function healthyProducer() {
  return {
    schema: PRODUCER_EVIDENCE_SCHEMA,
    runId: RUN,
    rows: SHELLS.flatMap((shell) => DOMAINS.map((domain) => ({
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
    }))),
  };
}

function verdict({ consumer = healthyConsumer(), producer = healthyProducer() } = {}) {
  return arbitrateEvidence({
    runId: RUN,
    consumer,
    producer,
    expectedShellTreeHash: TREE,
    expectedSurfaceTreeHash: SURFACE,
  });
}

function mustFail(result, pattern) {
  assert.equal(result.result, "fail");
  assert.match(result.failures.join("\n"), pattern);
}

test("healthy evidence is exactly the 2 x 7 Cartesian matrix", () => {
  const result = verdict();
  assert.deepEqual(result.failures, []);
  assert.equal(result.result, "pass");
  assert.equal(result.rowCount, MATRIX_SIZE);
  assert.deepEqual(
    result.rows.map(({ shell, domain }) => `${shell}/${domain}`),
    SHELLS.flatMap((shell) => DOMAINS.map((domain) => `${shell}/${domain}`)),
  );
});

test("RED-PROOF missing shell/domain row cannot be replaced by an aggregate", () => {
  const consumer = healthyConsumer();
  consumer.rows.pop();
  // red-proof: remove ios/settings and add consumer.total=13. The aggregate is
  // intentionally ignored and the coordinate remains missing.
  consumer.total = 13;
  mustFail(verdict({ consumer }), /exactly 14|missing coordinate ios\/settings/);
});

test("RED-PROOF duplicate coordinate cannot stand in for its missing sibling", () => {
  const consumer = healthyConsumer();
  consumer.rows[13] = { ...consumer.rows[12] };
  mustFail(verdict({ consumer }), /duplicate coordinate|missing coordinate/);
});

test("RED-PROOF wrong run and shell keys are rejected on both sides of the join", () => {
  const consumer = healthyConsumer();
  consumer.rows[0] = { ...consumer.rows[0], runId: "run-stale" };
  const producer = healthyProducer();
  producer.rows[1] = { ...producer.rows[1], shell: "ios" };
  mustFail(verdict({ consumer, producer }), /wrong runId|duplicate coordinate|missing coordinate/);
});

test("RED-PROOF fixture fallback never counts as live consumer evidence", () => {
  const consumer = healthyConsumer();
  consumer.rows[0] = { ...consumer.rows[0], fixture: "normal" };
  mustFail(verdict({ consumer }), /fixture-backed/);
});

test("RED-PROOF stale shell or surface tree hashes fail the coordinate", () => {
  const consumer = healthyConsumer();
  consumer.rows[0] = { ...consumer.rows[0], shellTreeHash: "3".repeat(40) };
  consumer.rows[1] = { ...consumer.rows[1], surfaceTreeHash: "4".repeat(40) };
  mustFail(verdict({ consumer }), /stale or mismatched shell tree hash|stale or mismatched surface tree hash/);
});

test("RED-PROOF dispatch, readiness, and screenshot rows are not rendered semantics", () => {
  for (const evidence of ["dispatch", "readiness", "screenshot"]) {
    const consumer = healthyConsumer();
    consumer.rows[0] = { ...consumer.rows[0], evidence };
    mustFail(verdict({ consumer }), /must be rendered-semantic/);
  }
});

test("RED-PROOF generation mismatch: the claimed domain must be what rendered", () => {
  const consumer = healthyConsumer();
  consumer.rows[0] = {
    ...consumer.rows[0],
    observation: { ...consumer.rows[0].observation, route: "tasks" },
  };
  mustFail(verdict({ consumer }), /rendered route.*does not match/);
});

test("RED-PROOF successful HTTP served counts are per coordinate", () => {
  const producer = healthyProducer();
  producer.rows.find((row) => row.shell === "ios" && row.domain === "folders").http.successful = 0;
  producer.totalSuccessful = 99;
  mustFail(verdict({ producer }), /ios\/folders.*positive successful served count/);
});

test("RED-PROOF invented store metadata is outside P7 readiness and producer schemas", () => {
  const databasePath = "/tmp/run/service.sqlite";
  const readiness = {
    schema: SERVICE_READINESS_SCHEMA,
    runId: RUN,
    executable: SERVICE_EXECUTABLE,
    baseUrl: SERVICE_BASE_URL,
    databasePath,
    pid: 123,
    evidencePath: "/v1/qa/evidence",
    devToken: "local-only-token",
    ownerAccountId: "local-fixture-owner",
    storeSetId: `sqlite:${RUN}`,
    storeCount: 1,
  };
  const readinessResult = validateServiceReadiness(readiness, { runId: RUN, databasePath, pid: 123 });
  assert.equal(readinessResult.ok, false);
  assert.match(readinessResult.failures.join("\n"), /non-schema field.*storeSetId.*storeCount/);

  const producer = healthyProducer();
  producer.storeSetId = `sqlite:${RUN}`;
  producer.rows[0].storeSetId = `sqlite:${RUN}`;
  mustFail(verdict({ producer }), /non-schema field.*storeSetId/);
});

test("RED-PROOF Chat requires the exact chat.acceptedAdmission count", () => {
  const producer = healthyProducer();
  const chat = producer.rows.find((row) => row.shell === "macos" && row.domain === "chat").chat;
  chat.durableAccepted = chat.acceptedAdmission;
  delete chat.acceptedAdmission;
  mustFail(verdict({ producer }), /chat\.acceptedAdmission|non-schema field.*durableAccepted/);
});

test("RED-PROOF Listen ready without accepted nontrivial binary traffic fails", () => {
  const producer = healthyProducer();
  const listen = producer.rows.find((row) => row.shell === "ios" && row.domain === "listen").listen;
  listen.protocolReady = 1;
  listen.acceptedBinary = 0;
  listen.acceptedBinaryBytes = 0;
  mustFail(verdict({ producer }), /ready without accepted binary traffic|trivial or absent/);
});

test("RED-PROOF the exact Listen count is acceptedBinary, never acceptedBinaryFrames", () => {
  const producer = healthyProducer();
  const listen = producer.rows.find((row) => row.shell === "macos" && row.domain === "listen").listen;
  listen.acceptedBinaryFrames = listen.acceptedBinary;
  delete listen.acceptedBinary;
  mustFail(verdict({ producer }), /ready without accepted binary traffic|non-schema field.*acceptedBinaryFrames/);
});

test("RED-PROOF producer evidence is counts-only and never exposes content", () => {
  const injections = [
    ["transcript", "fixture transcript"],
    ["audioSha256", "f".repeat(64)],
    ["devToken", "local-secret"],
    ["ownerAccountId", "local-owner"],
    ["prompt", "user prompt"],
    ["attachment", { name: "private.txt" }],
    ["fixture", "normal"],
    ["userContent", "arbitrary content"],
  ];
  for (const [field, value] of injections) {
    for (const location of ["document", "row", "http", "chat", "listen"]) {
      const producer = healthyProducer();
      const targets = {
        document: producer,
        row: producer.rows.find((row) => row.shell === "ios" && row.domain === "memories"),
        http: producer.rows.find((row) => row.shell === "ios" && row.domain === "memories").http,
        chat: producer.rows.find((row) => row.shell === "ios" && row.domain === "chat").chat,
        listen: producer.rows.find((row) => row.shell === "ios" && row.domain === "listen").listen,
      };
      targets[location][field] = value;
      const result = verdict({ producer });
      mustFail(result, new RegExp(`non-schema field.*${field}`));
      const serializedProducers = JSON.stringify(result.rows.map((row) => row.producer));
      assert.doesNotMatch(serializedProducers, new RegExp(field));
      assert.doesNotMatch(serializedProducers, /fixture transcript|local-secret|local-owner|user prompt|private\.txt|arbitrary content/);
    }
  }
});

test("RED-PROOF consumer Listen still requires a rendered non-empty transcript", () => {
  const consumer = healthyConsumer();
  consumer.rows.find((row) => row.shell === "ios" && row.domain === "listen").observation.transcript = "";
  mustFail(verdict({ consumer }), /ios\/listen rendered transcript must be non-empty text/);
});

test("RED-PROOF unknown service launcher executable cannot satisfy readiness", () => {
  const databasePath = "/tmp/run/service.sqlite";
  const healthy = {
    schema: SERVICE_READINESS_SCHEMA,
    runId: RUN,
    executable: SERVICE_EXECUTABLE,
    baseUrl: SERVICE_BASE_URL,
    databasePath,
    pid: 123,
    evidencePath: "/v1/qa/evidence",
    devToken: "local-only-token",
    ownerAccountId: "local-fixture-owner",
  };
  assert.equal(validateServiceReadiness(healthy, { runId: RUN, databasePath, pid: 123 }).ok, true);
  const result = validateServiceReadiness(
    { ...healthy, executable: "integration/lib/write-journey-door.mjs" },
    { runId: RUN, databasePath, pid: 123 },
  );
  assert.equal(result.ok, false);
  assert.match(result.failures.join("\n"), /unknown launcher executable/);
});

test("RED-PROOF a foreign readiness PID cannot stand in for the launched service", () => {
  const databasePath = "/tmp/run/service.sqlite";
  const result = validateServiceReadiness({
    schema: SERVICE_READINESS_SCHEMA,
    runId: RUN,
    executable: SERVICE_EXECUTABLE,
    baseUrl: SERVICE_BASE_URL,
    databasePath,
    pid: 999,
    evidencePath: "/v1/qa/evidence",
    devToken: "local-only-token",
    ownerAccountId: "local-fixture-owner",
  }, { runId: RUN, databasePath, pid: 123 });
  assert.equal(result.ok, false);
  assert.match(result.failures.join("\n"), /does not match launched pid/);
});
