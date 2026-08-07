import { ClientIdCreatePrototype } from "./prototypes/client-id-create.mjs";
import { HybridPrototype } from "./prototypes/hybrid.mjs";
import { PipelineEntryPrototype } from "./prototypes/pipeline-entry.mjs";

const pipeline = new PipelineEntryPrototype();
const captured = pipeline.capture("u1", [{ text: "captured online" }]);

const clientId = new ClientIdCreatePrototype({ tenantId: "tenant-1", domain: "conversations" });
const clientCreated = clientId.create("u1", {
  opId: "create-1",
  id: "quiet-river-stone",
  segments: [{ text: "queued offline" }],
  startedAt: 1,
});

const hybrid = new HybridPrototype({ tenantId: "tenant-1", domain: "conversations" });
// domain-pending(FEAT-CONV-012): offline/bind metadata below is spike vocabulary only.
hybrid.createOffline("u1", {
  opId: "client-1",
  id: "gentle-meadow-stone",
  startedAt: 1,
  source: "phone",
  captureDeviceId: "device-1",
});
const hybridBound = hybrid.bindCapture("u1", {
  opId: "bind-1",
  id: "gentle-meadow-stone",
  captureId: "capture-1",
  startedAt: 1,
  source: "phone",
  captureDeviceId: "device-1",
  segments: [{ text: "arrived from capture" }],
});
const hybridAdmitted = hybrid.admitFinalization("u1", {
  opId: "finalize-1",
  id: "gentle-meadow-stone",
});

console.log(
  JSON.stringify(
    {
      pipelineEntry: { captured, finalized: pipeline.finalizeCurrent("u1") },
      clientIdCreate: {
        created: clientCreated,
        processed: clientId.process("u1", { opId: "process-1", id: "quiet-river-stone" }),
      },
      hybrid: {
        bound: hybridBound,
        admitted: hybridAdmitted,
        completed: hybrid.runFinalizer("u1", "gentle-meadow-stone"),
      },
    },
    null,
    2,
  ),
);
