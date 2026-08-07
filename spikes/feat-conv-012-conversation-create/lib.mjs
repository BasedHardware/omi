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

  run(opId, request, mutation) {
    requireOpId(opId);
    const requestFingerprint = fingerprint(request);
    const prior = this.#entries.get(opId);
    if (prior) {
      if (prior.requestFingerprint !== requestFingerprint) {
        throw new FixtureError(409, "op-id-reused", "opId was already committed for a different mutation");
      }
      return structuredClone(prior.response);
    }

    const response = mutation();
    this.#entries.set(opId, { requestFingerprint, response: structuredClone(response) });
    return response;
  }

  size() {
    return this.#entries.size;
  }
}

export function samePayload(left, right) {
  return fingerprint(left) === fingerprint(right);
}
