import { createHash } from "node:crypto";

const CLIENT_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CLIENT_SLUG = /^[a-z]{2,12}(?:-[a-z]{2,12}){2,4}$/;

export class FixtureError extends Error {
  constructor(status, code, message) {
    super(message);
    this.name = "FixtureError";
    this.status = status;
    this.code = code;
  }
}

export function requireClientRecordId(id) {
  if (!CLIENT_UUID.test(id) && !CLIENT_SLUG.test(id)) {
    throw new FixtureError(422, "invalid-record-id", "client ids must be legacy UUIDs or 3-5 word slugs");
  }
  return id;
}

export function requireOpId(opId) {
  if (typeof opId !== "string" || opId.trim() === "") {
    throw new FixtureError(422, "missing-op-id", "every mutation requires opId");
  }
  return opId;
}

export function fingerprint(value) {
  return createHash("sha256").update(stableJson(value)).digest("hex");
}

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

export class OperationLedger {
  #entries = new Map();

  run(scope, opId, request, mutation) {
    requireLedgerScope(scope);
    requireOpId(opId);
    const ledgerKey = fingerprint({ scope, opId });
    const requestFingerprint = fingerprint(request);
    const prior = this.#entries.get(ledgerKey);
    if (prior) {
      if (prior.requestFingerprint !== requestFingerprint) {
        throw new FixtureError(409, "op-id-reused", "opId was already committed for a different mutation");
      }
      if (prior.outcome === "terminal-conflict") {
        throw new FixtureError(prior.error.status, prior.error.code, prior.error.message);
      }
      return structuredClone(prior.response);
    }

    try {
      const response = mutation();
      this.#entries.set(ledgerKey, { requestFingerprint, outcome: "success", response: structuredClone(response) });
      return response;
    } catch (error) {
      if (error instanceof FixtureError && isTerminalConflict(error.status)) {
        this.#entries.set(ledgerKey, {
          requestFingerprint,
          outcome: "terminal-conflict",
          error: { status: error.status, code: error.code, message: error.message },
        });
      }
      throw error;
    }
  }

  size() {
    return this.#entries.size;
  }
}

function requireLedgerScope(scope) {
  for (const key of ["tenantId", "userId", "domain"]) {
    if (typeof scope?.[key] !== "string" || scope[key].trim() === "") {
      throw new FixtureError(422, "invalid-op-scope", `operation scope requires ${key}`);
    }
  }
}

function isTerminalConflict(status) {
  return status === 400 || status === 402 || status === 409 || status === 413 || status === 422;
}

export function samePayload(left, right) {
  return fingerprint(left) === fingerprint(right);
}
