import { pathToFileURL } from "node:url";

import { FixtureError, OperationLedger, requireClientRecordId, samePayload } from "../lib.mjs";

/** Option B: client identity plus opId-idempotent create and processing mutations. */
export class ClientIdCreatePrototype {
  #records = new Map();
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

  // domain-pending(FEAT-CONV-012): this create shape is spike evidence, not a ratified ConversationOp variant.
  create(uid, { opId, id, segments, startedAt }) {
    requireClientRecordId(id);
    const request = { mutation: "create", uid, id, segments, startedAt };
    return this.#ledger.run(this.#scope(uid), opId, request, () => {
      const key = `${uid}:${id}`;
      const payload = { segments: structuredClone(segments), startedAt };
      const prior = this.#records.get(key);
      if (prior) {
        if (!samePayload(prior.createPayload, payload)) {
          throw new FixtureError(409, "record-id-conflict", "record id already owns different create content");
        }
        return { status: 200, record: structuredClone(prior), replay: "record" };
      }
      const record = { id, uid, status: "in_progress", createPayload: payload, processingRuns: 0 };
      this.#records.set(key, record);
      return { status: 201, record: structuredClone(record), replay: null };
    });
  }

  // domain-pending(FEAT-CONV-012): whether processing is a create side effect or a separate mutation is undecided.
  process(uid, { opId, id, failAfterAdmission = false }) {
    requireClientRecordId(id);
    const request = { mutation: "process", uid, id };
    return this.#ledger.run(this.#scope(uid), opId, request, () => {
      const record = this.#records.get(`${uid}:${id}`);
      if (!record) throw new FixtureError(404, "record-not-found", "create must commit before processing");
      if (record.status === "completed") return { status: 200, record: structuredClone(record), replay: "record" };
      if (record.status !== "in_progress" && record.status !== "processing") {
        throw new FixtureError(409, "lifecycle-conflict", `cannot process status ${record.status}`);
      }
      record.status = "processing";
      record.processingRuns += 1;
      if (failAfterAdmission) throw new FixtureError(503, "processor-crashed", "retry the same opId to resume");
      record.status = "completed";
      return { status: 200, record: structuredClone(record), replay: null };
    });
  }

  get ledgerSize() {
    return this.#ledger.size();
  }

  get(uid, id) {
    const record = this.#records.get(`${uid}:${id}`);
    return record ? structuredClone(record) : null;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const fixture = new ClientIdCreatePrototype({ tenantId: "tenant-1", domain: "conversations" });
  const created = fixture.create("user-1", {
    opId: "op-create-1",
    id: "quiet-river-stone",
    segments: [{ text: "queued while offline" }],
    startedAt: 1,
  });
  const processed = fixture.process("user-1", { opId: "op-process-1", id: "quiet-river-stone" });
  console.log(JSON.stringify({ created, processed }, null, 2));
}
