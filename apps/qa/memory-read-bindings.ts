import type { MemoryReadCursorBindings } from "../service/composition/memory-read";
import { createQaCursorAdapter, QA_CURSOR_POLICY } from "./cursor-bindings";
import { produceQaRenders } from "./renders";

/**
 * The QA collaborators for the loopback read path.
 *
 * `apps/service/composition/memory-read.ts` used to import these at module
 * scope. That linked the QA cursor bindings and the QA deterministic
 * synthesizer — a model fake — into the production process, because the
 * production kernel reaches that module by two chains:
 *
 *   process → service-app → read-runtime → composition/memory-read
 *   process → service-app → memory-service-app → routes/memories → composition/memory-read
 *
 * The dual-runtime qualification contract requires the production import graph
 * to exclude every QA store and model fake, so the edge is supplied here by the
 * side that actually wants QA behaviour. Nothing moved out of the composition
 * root: it remains THE one construction site for `ApplicationReadPorts`.
 */
export const QA_MEMORY_READ_CURSOR_BINDINGS: MemoryReadCursorBindings = Object.freeze({
  createCursorAdapter: createQaCursorAdapter,
  policy: QA_CURSOR_POLICY,
});

export const qaMemoryReadProduceRenders = produceQaRenders;
