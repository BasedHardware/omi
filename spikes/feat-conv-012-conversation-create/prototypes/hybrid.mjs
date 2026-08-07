import { pathToFileURL } from "node:url";

import { FixtureError, OperationLedger, fingerprint, requireClientRecordId, samePayload } from "../lib.mjs";

/** Option C: two identity entry modes share one receipt ledger, then finalization remains separate. */
export class HybridPrototype {
  #records = new Map();
  // domain-pending(FEAT-CONV-012): capture binding is provisional evidence, not ratified domain vocabulary.
  #captureBindings = new Map();
  #finalizationJobs = new Map();
  #ledger = new OperationLedger();
  #tenantId;
  #domain;

  constructor({ tenantId, domain }) {
    this.#tenantId = tenantId;
    this.#domain = domain;
  }

  #scope(uid) {
    return { tenantId: this.#tenantId, userId: uid, domain: this.#domain };
  }

  // domain-pending(FEAT-CONV-012): "offline draft" and client create are provisional entry semantics.
  createOffline(uid, { opId, id, startedAt, source, captureDeviceId = null, segments = [] }) {
    requireClientRecordId(id);
    const request = { mutation: "client-create", uid, id, startedAt, source, captureDeviceId, segments };
    return this.#ledger.run(this.#scope(uid), opId, request, () => {
      const key = `${uid}:${id}`;
      const payload = { startedAt, source, captureDeviceId, segments: structuredClone(segments) };
      const prior = this.#records.get(key);
      if (prior) {
        // domain-pending(FEAT-CONV-012): origin and create payload ownership are not contract fields.
        if (prior.origin !== "client" || !samePayload(prior.createPayload, payload)) {
          throw new FixtureError(409, "record-id-conflict", "identity already belongs to a different record");
        }
        return { status: 200, record: structuredClone(prior), replay: "record" };
      }
      const record = {
        id,
        uid,
        // domain-pending(FEAT-CONV-012): origin provenance is a spike-only comparison field.
        origin: "client",
        status: "in_progress",
        // domain-pending(FEAT-CONV-012): captureId is a provisional binding key.
        captureId: null,
        // domain-pending(FEAT-CONV-012): createPayload is a fixture snapshot, not a proposed record shape.
        createPayload: payload,
      };
      this.#records.set(key, record);
      return { status: 201, record: structuredClone(record), replay: null };
    });
  }

  // domain-pending(FEAT-CONV-012): bind/capture semantics are deliberately exposed for David to rule on.
  bindCapture(uid, { opId, captureId, id = null, startedAt, source, captureDeviceId = null, segments }) {
    const requestedId = id === null ? this.#mintPipelineId(uid, captureId) : requireClientRecordId(id);
    const request = {
      mutation: "pipeline-bind",
      uid,
      captureId,
      id: requestedId,
      startedAt,
      source,
      captureDeviceId,
      segments,
    };
    return this.#ledger.run(this.#scope(uid), opId, request, () => {
      // domain-pending(FEAT-CONV-012): binding identity and its authorization proof remain undecided.
      const bindingKey = `${uid}:${captureId}`;
      const existingBinding = this.#captureBindings.get(bindingKey);
      if (existingBinding && existingBinding !== requestedId) {
        throw new FixtureError(409, "capture-binding-conflict", "capture identity is already bound elsewhere");
      }

      const key = `${uid}:${requestedId}`;
      const prior = this.#records.get(key);
      const captureMetadata = { startedAt, source, captureDeviceId };
      if (prior) {
        // domain-pending(FEAT-CONV-012): createPayload and capture metadata ownership/tolerance need a ruling.
        const clientMetadata = {
          startedAt: prior.createPayload?.startedAt,
          source: prior.createPayload?.source,
          captureDeviceId: prior.createPayload?.captureDeviceId ?? null,
        };
        if (!samePayload(clientMetadata, captureMetadata)) {
          throw new FixtureError(
            409,
            "capture-metadata-needs-ruling",
            "prototype refuses to guess timestamp/source/device ownership or tolerance",
          );
        }
        // domain-pending(FEAT-CONV-012): captureId is a provisional one-to-one binding.
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
        // domain-pending(FEAT-CONV-012): captureId and ingestedSegments are spike-only binding evidence.
        prior.captureId = captureId;
        prior.ingestedSegments = structuredClone(segments);
        this.#captureBindings.set(bindingKey, requestedId);
        return { status: 200, record: structuredClone(prior), replay: null };
      }

      const record = {
        id: requestedId,
        uid,
        // domain-pending(FEAT-CONV-012): origin provenance is a spike-only comparison field.
        origin: "pipeline",
        status: "in_progress",
        // domain-pending(FEAT-CONV-012): captureId is a provisional binding key.
        captureId,
        // domain-pending(FEAT-CONV-012): createPayload is a fixture snapshot, not a proposed record shape.
        createPayload: { ...captureMetadata, segments: structuredClone(segments) },
        // domain-pending(FEAT-CONV-012): ingestedSegments is not a proposed contract field.
        ingestedSegments: structuredClone(segments),
      };
      this.#records.set(key, record);
      this.#captureBindings.set(bindingKey, requestedId);
      return { status: 201, record: structuredClone(record), replay: null };
    });
  }

  admitFinalization(uid, { opId, id }) {
    requireClientRecordId(id);
    const request = { mutation: "finalize", uid, id };
    return this.#ledger.run(this.#scope(uid), opId, request, () => {
      const record = this.#records.get(`${uid}:${id}`);
      if (!record) throw new FixtureError(404, "record-not-found", "bind/create must commit before finalization");
      if (record.status === "completed") return { status: 200, record: structuredClone(record), replay: "record" };
      if (record.status !== "in_progress" && record.status !== "processing") {
        throw new FixtureError(409, "lifecycle-conflict", `cannot finalize status ${record.status}`);
      }
      const jobKey = `${uid}:${id}:1`;
      const job = this.#finalizationJobs.get(jobKey) ?? { id: jobKey, status: "queued", leaseEpoch: 0 };
      this.#finalizationJobs.set(jobKey, job);
      record.status = "processing";
      return { status: 202, record: structuredClone(record), job: structuredClone(job), replay: null };
    });
  }

  runFinalizer(uid, id, { hardCrash = false, reclaimExpired = false } = {}) {
    const record = this.#records.get(`${uid}:${id}`);
    const job = this.#finalizationJobs.get(`${uid}:${id}:1`);
    if (!record || !job) throw new FixtureError(404, "finalization-not-found", "no durable finalization admission exists");
    if (job.status === "completed") return { record: structuredClone(record), job: structuredClone(job) };
    if (job.status === "leased" && !reclaimExpired) {
      throw new FixtureError(503, "finalization-lease-active", "retry waits until the prior lease expires");
    }
    job.status = "leased";
    job.leaseEpoch += 1;
    if (hardCrash) throw new FixtureError(503, "finalizer-hard-crashed", "a later lease may retry after expiry");
    record.status = "completed";
    job.status = "completed";
    return { record: structuredClone(record), job: structuredClone(job) };
  }

  // domain-pending(FEAT-CONV-012): pipeline-generated ids remain an option, not selected identity policy.
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
  const fixture = new HybridPrototype({ tenantId: "tenant-1", domain: "conversations" });
  // domain-pending(FEAT-CONV-012): offline/bind metadata below is spike vocabulary only.
  const offline = fixture.createOffline("user-1", {
    opId: "op-client-1",
    id: "quiet-river-stone",
    startedAt: 1,
    source: "phone",
    captureDeviceId: "device-1",
  });
  const bound = fixture.bindCapture("user-1", {
    opId: "op-bind-1",
    id: "quiet-river-stone",
    captureId: "capture-1",
    startedAt: 1,
    source: "phone",
    captureDeviceId: "device-1",
    segments: [{ text: "arrived from capture" }],
  });
  const admitted = fixture.admitFinalization("user-1", {
    opId: "op-finalize-1",
    id: "quiet-river-stone",
  });
  const completed = fixture.runFinalizer("user-1", "quiet-river-stone");
  console.log(JSON.stringify({ offline, bound, admitted, completed }, null, 2));
}
