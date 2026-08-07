import { pathToFileURL } from "node:url";

import { FixtureError, OperationLedger, fingerprint, requireClientRecordId, samePayload } from "../lib.mjs";

/** Option C: client-created in-progress rows and pipeline-originated rows share one idempotent ledger. */
export class HybridPrototype {
  #records = new Map();
  #captureBindings = new Map();
  #ledger = new OperationLedger();

  // domain-pending(FEAT-CONV-012): "offline draft" is convenience language, not a ratified lifecycle state.
  createOffline(uid, { opId, id, startedAt, segments = [] }) {
    requireClientRecordId(id);
    const request = { mutation: "client-create", uid, id, startedAt, segments };
    return this.#ledger.run(opId, request, () => {
      const key = `${uid}:${id}`;
      const payload = { startedAt, segments: structuredClone(segments) };
      const prior = this.#records.get(key);
      if (prior) {
        if (prior.origin !== "client" || !samePayload(prior.createPayload, payload)) {
          throw new FixtureError(409, "record-id-conflict", "identity already belongs to a different record");
        }
        return { status: 200, record: structuredClone(prior), replay: "record" };
      }
      const record = {
        id,
        uid,
        origin: "client",
        status: "in_progress",
        captureId: null,
        createPayload: payload,
      };
      this.#records.set(key, record);
      return { status: 201, record: structuredClone(record), replay: null };
    });
  }

  // domain-pending(FEAT-CONV-012): ingest/bind semantics are deliberately exposed for David to rule on.
  ingestCapture(uid, { opId, captureId, id = null, startedAt, segments }) {
    const requestedId = id === null ? this.#mintPipelineId(uid, captureId) : requireClientRecordId(id);
    const request = { mutation: "pipeline-ingest", uid, captureId, id: requestedId, startedAt, segments };
    return this.#ledger.run(opId, request, () => {
      const bindingKey = `${uid}:${captureId}`;
      const existingBinding = this.#captureBindings.get(bindingKey);
      if (existingBinding && existingBinding !== requestedId) {
        throw new FixtureError(409, "capture-binding-conflict", "capture identity is already bound elsewhere");
      }

      const key = `${uid}:${requestedId}`;
      const prior = this.#records.get(key);
      if (prior) {
        if (prior.captureId && prior.captureId !== captureId) {
          throw new FixtureError(409, "record-binding-conflict", "record is already bound to another capture");
        }
        const clientSegments = prior.createPayload?.segments ?? [];
        if (clientSegments.length > 0 && !samePayload(clientSegments, segments)) {
          throw new FixtureError(
            409,
            "content-reconciliation-needs-ruling",
            "prototype refuses to guess whether client and pipeline content should merge or replace",
          );
        }
        prior.captureId = captureId;
        prior.status = "completed";
        prior.ingestedSegments = structuredClone(segments);
        this.#captureBindings.set(bindingKey, requestedId);
        return { status: 200, record: structuredClone(prior), replay: null };
      }

      const record = {
        id: requestedId,
        uid,
        origin: "pipeline",
        status: "completed",
        captureId,
        createPayload: { startedAt, segments: structuredClone(segments) },
        ingestedSegments: structuredClone(segments),
      };
      this.#records.set(key, record);
      this.#captureBindings.set(bindingKey, requestedId);
      return { status: 201, record: structuredClone(record), replay: null };
    });
  }

  // domain-pending(FEAT-CONV-012): pipeline-generated ids remain an option, not the selected identity policy.
  #mintPipelineId(uid, captureId) {
    const hex = fingerprint({ uid, captureId });
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-4${hex.slice(13, 16)}-8${hex.slice(17, 20)}-${hex.slice(20, 32)}`;
  }

  get(uid, id) {
    const record = this.#records.get(`${uid}:${id}`);
    return record ? structuredClone(record) : null;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const fixture = new HybridPrototype();
  const offline = fixture.createOffline("user-1", {
    opId: "op-client-1",
    id: "quiet-river-stone",
    startedAt: 1,
  });
  const ingested = fixture.ingestCapture("user-1", {
    opId: "op-ingest-1",
    id: "quiet-river-stone",
    captureId: "capture-1",
    startedAt: 1,
    segments: [{ text: "arrived from capture" }],
  });
  console.log(JSON.stringify({ offline, ingested }, null, 2));
}
