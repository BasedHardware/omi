// LIFECYCLE: permanent
//
// One evidence vocabulary for the real two-shell integration lane. The producer
// and consumer documents remain separate until this arbiter joins them by the
// host-owned run + shell + domain key. A shell saying it rendered and a service
// saying it served are both necessary; neither may stand in for the other.

export const CONSUMER_EVIDENCE_SCHEMA = "omi.consumer-evidence.v1";
export const PRODUCER_EVIDENCE_SCHEMA = "omi.producer-evidence.v1";
export const SERVICE_READINESS_SCHEMA = "omi.dev-service-readiness.v1";
export const MATRIX_REPORT_SCHEMA = "omi.shell-domain-matrix.v1";

export const SHELLS = Object.freeze(["macos", "ios"]);
export const DOMAINS = Object.freeze([
  "memories",
  "tasks",
  "conversations",
  "folders",
  "listen",
  "chat",
  "settings",
]);
export const MATRIX_SIZE = SHELLS.length * DOMAINS.length;
export const SERVICE_EXECUTABLE = "apps/service/bin/dev-server.ts";
export const SERVICE_BASE_URL = "http://127.0.0.1:4851";
export const PRODUCER_EVIDENCE_PATH = "/v1/qa/evidence";

const HASH = /^[0-9a-f]{40}$/;
const keyOf = (shell, domain) => `${shell}/${domain}`;
const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const integer = (value) => Number.isSafeInteger(value) && value >= 0;

function requireExactKeys(value, allowed, label, failures) {
  if (!isObject(value)) return;
  const unexpected = Object.keys(value).filter((key) => !allowed.includes(key));
  if (unexpected.length > 0) {
    failures.push(`${label} has non-schema field(s): ${unexpected.join(", ")}`);
  }
}

export function deterministicListenAudio() {
  // 100 ms of signed PCM16 mono at 16 kHz. It is deliberately non-silent and
  // deterministic, while remaining synthetic and far too short to contain user
  // data. The native driver sends these bytes after protocol readiness; the
  // producer boundary reports counts only and never reflects their digest or
  // resulting transcript.
  const bytes = new Uint8Array(3_200);
  for (let sample = 0; sample < 1_600; sample += 1) {
    const value = ((sample * 257) % 24_001) - 12_000;
    bytes[sample * 2] = value & 0xff;
    bytes[sample * 2 + 1] = (value >> 8) & 0xff;
  }
  return bytes;
}

export function expectedCoordinates() {
  return SHELLS.flatMap((shell) => DOMAINS.map((domain) => ({ shell, domain })));
}

function requireText(value, label, failures) {
  if (typeof value !== "string" || value.trim() === "") failures.push(`${label} must be non-empty text`);
}

function validateCoordinate(row, index, expectedRunId, failures) {
  const at = `row[${index}]`;
  if (!isObject(row)) {
    failures.push(`${at} must be an object`);
    return null;
  }
  if (row.runId !== expectedRunId) failures.push(`${at} has wrong runId ${JSON.stringify(row.runId)}`);
  if (!SHELLS.includes(row.shell)) failures.push(`${at} has unknown shell ${JSON.stringify(row.shell)}`);
  if (!DOMAINS.includes(row.domain)) failures.push(`${at} has unknown domain ${JSON.stringify(row.domain)}`);
  if (!SHELLS.includes(row.shell) || !DOMAINS.includes(row.domain)) return null;
  return keyOf(row.shell, row.domain);
}

function requireExactMatrix(rows, expectedRunId, label, failures) {
  if (!Array.isArray(rows)) {
    failures.push(`${label}.rows must be an array`);
    return new Map();
  }
  if (rows.length !== MATRIX_SIZE) {
    failures.push(`${label}.rows must contain exactly ${MATRIX_SIZE} rows, got ${rows.length}`);
  }
  const byKey = new Map();
  rows.forEach((row, index) => {
    const key = validateCoordinate(row, index, expectedRunId, failures);
    if (key === null) return;
    if (byKey.has(key)) failures.push(`${label}.rows contains duplicate coordinate ${key}`);
    else byKey.set(key, row);
  });
  for (const { shell, domain } of expectedCoordinates()) {
    const key = keyOf(shell, domain);
    if (!byKey.has(key)) failures.push(`${label}.rows is missing coordinate ${key}`);
  }
  return byKey;
}

function countOnlyProducerRow(row, domain) {
  const normalized = {
    runId: row.runId,
    shell: row.shell,
    domain: row.domain,
    evidence: row.evidence,
  };
  if (domain === "listen") {
    normalized.listen = {
      protocolReady: row.listen?.protocolReady,
      acceptedBinary: row.listen?.acceptedBinary,
      acceptedBinaryBytes: row.listen?.acceptedBinaryBytes,
    };
  } else {
    normalized.http = { successful: row.http?.successful };
    if (domain === "chat") {
      normalized.chat = { acceptedAdmission: row.chat?.acceptedAdmission };
    }
  }
  return Object.freeze(normalized);
}

function renderedConsumerRow(row, domain) {
  const observation = {
    route: row.observation?.route,
    state: row.observation?.state,
    semantic: row.observation?.semantic,
    ...(domain === "listen" ? { transcript: row.observation?.transcript } : {}),
  };
  return Object.freeze({
    runId: row.runId,
    shell: row.shell,
    domain: row.domain,
    fixture: row.fixture,
    evidence: row.evidence,
    observation: Object.freeze(observation),
    shellTreeHash: row.shellTreeHash,
    surfaceTreeHash: row.surfaceTreeHash,
  });
}

export function validateServiceReadiness(record, {
  runId,
  databasePath,
  pid,
  executable = SERVICE_EXECUTABLE,
  baseUrl = SERVICE_BASE_URL,
} = {}) {
  const failures = [];
  if (!isObject(record)) return { ok: false, failures: ["service readiness record must be an object"] };
  requireExactKeys(record, [
    "schema",
    "runId",
    "executable",
    "baseUrl",
    "databasePath",
    "pid",
    "evidencePath",
    "devToken",
    "ownerAccountId",
  ], "service readiness", failures);
  if (record.schema !== SERVICE_READINESS_SCHEMA) failures.push(`service readiness schema must be ${SERVICE_READINESS_SCHEMA}`);
  if (record.runId !== runId) failures.push(`service readiness has wrong runId ${JSON.stringify(record.runId)}`);
  if (record.executable !== executable) failures.push(`unknown launcher executable ${JSON.stringify(record.executable)}; expected ${executable}`);
  if (record.baseUrl !== baseUrl) failures.push(`service readiness baseUrl must be ${baseUrl}`);
  if (record.databasePath !== databasePath) failures.push("service readiness names a different SQLite path");
  if (!Number.isSafeInteger(pid) || pid <= 0) failures.push("expected service pid must be a positive integer");
  if (record.pid !== pid) failures.push(`service readiness pid ${JSON.stringify(record.pid)} does not match launched pid ${JSON.stringify(pid)}`);
  if (record.evidencePath !== PRODUCER_EVIDENCE_PATH) failures.push(`service readiness evidencePath must be ${PRODUCER_EVIDENCE_PATH}`);
  requireText(record.devToken, "service readiness devToken", failures);
  requireText(record.ownerAccountId, "service readiness ownerAccountId", failures);
  return { ok: failures.length === 0, failures };
}

export function arbitrateEvidence({
  runId,
  consumer,
  producer,
  expectedShellTreeHash,
  expectedSurfaceTreeHash,
} = {}) {
  const failures = [];
  requireText(runId, "runId", failures);
  if (!HASH.test(expectedShellTreeHash ?? "")) failures.push("expectedShellTreeHash must be a 40-character git tree hash");
  if (!HASH.test(expectedSurfaceTreeHash ?? "")) failures.push("expectedSurfaceTreeHash must be a 40-character git tree hash");

  if (!isObject(consumer)) failures.push("consumer evidence must be an object");
  else {
    requireExactKeys(consumer, ["schema", "runId", "rows"], "consumer evidence", failures);
    if (consumer.schema !== CONSUMER_EVIDENCE_SCHEMA) failures.push(`consumer schema must be ${CONSUMER_EVIDENCE_SCHEMA}`);
    if (consumer.runId !== runId) failures.push(`consumer evidence has wrong runId ${JSON.stringify(consumer.runId)}`);
  }
  if (!isObject(producer)) failures.push("producer evidence must be an object");
  else {
    requireExactKeys(producer, ["schema", "runId", "rows"], "producer evidence", failures);
    if (producer.schema !== PRODUCER_EVIDENCE_SCHEMA) failures.push(`producer schema must be ${PRODUCER_EVIDENCE_SCHEMA}`);
    if (producer.runId !== runId) failures.push(`producer evidence has wrong runId ${JSON.stringify(producer.runId)}`);
  }

  const consumers = requireExactMatrix(consumer?.rows, runId, "consumer", failures);
  const producers = requireExactMatrix(producer?.rows, runId, "producer", failures);
  const matrix = [];

  for (const { shell, domain } of expectedCoordinates()) {
    const key = keyOf(shell, domain);
    const c = consumers.get(key);
    const p = producers.get(key);
    if (c) {
      requireExactKeys(c, [
        "runId",
        "shell",
        "domain",
        "fixture",
        "evidence",
        "observation",
        "shellTreeHash",
        "surfaceTreeHash",
      ], `${key} consumer row`, failures);
      if (c.fixture !== "none") failures.push(`${key} consumer evidence is fixture-backed`);
      if (c.evidence !== "rendered-semantic") failures.push(`${key} consumer evidence must be rendered-semantic, not ${JSON.stringify(c.evidence)}`);
      if (!isObject(c.observation)) failures.push(`${key} consumer observation must be an object`);
      else {
        requireExactKeys(
          c.observation,
          domain === "listen" ? ["route", "state", "semantic", "transcript"] : ["route", "state", "semantic"],
          `${key} observation`,
          failures,
        );
        if (c.observation.route !== domain) failures.push(`${key} rendered route ${JSON.stringify(c.observation.route)} does not match its domain`);
        if (c.observation.state !== "ready") failures.push(`${key} is readiness-only or not semantically ready`);
        requireText(c.observation.semantic, `${key} rendered semantic observation`, failures);
        if (domain === "listen") requireText(c.observation.transcript, `${key} rendered transcript`, failures);
      }
      if (c.shellTreeHash !== expectedShellTreeHash) failures.push(`${key} has stale or mismatched shell tree hash`);
      if (c.surfaceTreeHash !== expectedSurfaceTreeHash) failures.push(`${key} has stale or mismatched surface tree hash`);
    }
    if (p) {
      const allowedRowKeys = domain === "listen"
        ? ["runId", "shell", "domain", "evidence", "listen"]
        : domain === "chat"
          ? ["runId", "shell", "domain", "evidence", "http", "chat"]
          : ["runId", "shell", "domain", "evidence", "http"];
      requireExactKeys(p, allowedRowKeys, `${key} producer row`, failures);
      if (p.evidence !== "served-outcome") failures.push(`${key} producer evidence is dispatch-only or readiness-only`);
      if (domain !== "listen") {
        if (!isObject(p.http) || !integer(p.http.successful) || p.http.successful <= 0) {
          failures.push(`${key} producer evidence requires a positive successful served count`);
        } else {
          requireExactKeys(p.http, ["successful"], `${key} HTTP counts`, failures);
        }
      }
      if (domain === "chat") {
        if (!isObject(p.chat) || !integer(p.chat.acceptedAdmission) || p.chat.acceptedAdmission <= 0) {
          failures.push(`${key} producer evidence requires positive chat.acceptedAdmission`);
        } else {
          requireExactKeys(p.chat, ["acceptedAdmission"], `${key} Chat counts`, failures);
        }
      }
      if (domain === "listen") {
        const listen = p.listen;
        if (!isObject(listen)) failures.push(`${key} producer evidence is missing Listen acceptance`);
        else {
          requireExactKeys(
            listen,
            ["protocolReady", "acceptedBinary", "acceptedBinaryBytes"],
            `${key} Listen counts`,
            failures,
          );
          if (!integer(listen.protocolReady) || listen.protocolReady <= 0) failures.push(`${key} Listen never became protocol-ready`);
          if (!integer(listen.acceptedBinary) || listen.acceptedBinary <= 0) failures.push(`${key} Listen ready without accepted binary traffic`);
          if (!integer(listen.acceptedBinaryBytes) || listen.acceptedBinaryBytes < deterministicListenAudio().byteLength) failures.push(`${key} Listen accepted binary payload is trivial or absent`);
        }
      }
    }
    if (c && p) {
      matrix.push(Object.freeze({
        shell,
        domain,
        consumer: renderedConsumerRow(c, domain),
        producer: countOnlyProducerRow(p, domain),
      }));
    }
  }

  return Object.freeze({
    schema: MATRIX_REPORT_SCHEMA,
    runId,
    expectedRows: MATRIX_SIZE,
    rowCount: matrix.length,
    result: failures.length === 0 && matrix.length === MATRIX_SIZE ? "pass" : "fail",
    failures: Object.freeze(failures),
    rows: Object.freeze(matrix),
  });
}
