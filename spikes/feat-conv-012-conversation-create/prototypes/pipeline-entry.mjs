import { pathToFileURL } from "node:url";

import { FixtureError } from "../lib.mjs";

/**
 * Option A: executable model of POST /v1/conversations as a finalization entry.
 * Capture already created the server-owned record and current-pointer identity.
 */
export class PipelineEntryPrototype {
  #currentByUser = new Map();
  #records = new Map();
  #nextId = 1;

  capture(uid, segments) {
    const id = `00000000-0000-4000-8000-${String(this.#nextId++).padStart(12, "0")}`;
    const record = { id, uid, status: "in_progress", segments: structuredClone(segments), processingRuns: 0 };
    this.#records.set(`${uid}:${id}`, record);
    this.#currentByUser.set(uid, id);
    return structuredClone(record);
  }

  finalizeCurrent(uid, { failAfterAdmission = false } = {}) {
    const id = this.#currentByUser.get(uid) ?? this.#findInProgress(uid)?.id;
    if (!id) throw new FixtureError(404, "in-progress-not-found", "no current in-progress conversation exists");
    const record = this.#records.get(`${uid}:${id}`);
    if (!record || record.status !== "in_progress") {
      throw new FixtureError(404, "in-progress-not-found", "the current pointer no longer names an in-progress row");
    }

    record.status = "processing";
    record.processingRuns += 1;
    this.#currentByUser.delete(uid);
    if (failAfterAdmission === "handled-exception") {
      record.status = "in_progress";
      throw new FixtureError(503, "processor-failed", "guard rolled admission back for a normal retry");
    }
    if (failAfterAdmission === "hard-crash") {
      throw new FixtureError(503, "processor-hard-crashed", "stale-orphan recovery must close the admitted row");
    }
    record.status = "completed";
    return structuredClone(record);
  }

  recoverStaleOrphan(uid, id) {
    const record = this.#records.get(`${uid}:${id}`);
    if (!record || record.status !== "processing") return false;
    record.status = "completed";
    return true;
  }

  #findInProgress(uid) {
    return [...this.#records.values()].find((record) => record.uid === uid && record.status === "in_progress") ?? null;
  }

  get(uid, id) {
    const record = this.#records.get(`${uid}:${id}`);
    return record ? structuredClone(record) : null;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const fixture = new PipelineEntryPrototype();
  const captured = fixture.capture("user-1", [{ text: "captured by the server" }]);
  console.log(JSON.stringify({ captured, finalized: fixture.finalizeCurrent("user-1") }, null, 2));
}
