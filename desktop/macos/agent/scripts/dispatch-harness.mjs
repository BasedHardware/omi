// Node harness for the LIVE dispatch wiring (index.ts query handler), with no
// process/sockets. It reproduces the exact composition index.ts now uses:
//
//   plan = planQueryDispatch(query, availabilitySnapshot())
//   if (plan.needsSetup) -> guide setup (no run)
//   executeWithFallback(plan.order, runOne = activateAdapter + facade.handleQuery)
//     - activation throw            -> fall back
//     - handleQuery outcome !ok     -> throw DispatchAttemptError -> fall back if retryable
//
// Build first (`npm run build`), then: `node scripts/dispatch-harness.mjs`.

import {
  planQueryDispatch,
  buildAvailabilitySnapshot,
  isDispatchRetryable,
  DispatchAttemptError,
} from "../dist/runtime/dispatch-routing.js";
import { executeWithFallback } from "../dist/runtime/agent-fallback.js";

// Simulated runtime mirroring index.ts activateAdapter + facade.handleQuery.
function makeRuntime({ failActivation = new Set(), runFailsOn = new Map() } = {}) {
  const events = [];
  return {
    events,
    activateAdapter: async (agent) => {
      if (failActivation.has(agent)) throw new Error(`${agent} is not available.`);
    },
    // Returns a QueryOutcome like the real facade under { suppressFailureEmit: true }.
    handleQuery: async (agent) => {
      const fail = runFailsOn.get(agent);
      if (fail) {
        events.push(`run-failed(${agent}${fail.retryable ? "" : ", non-retryable"})`);
        return { ok: false, message: `${agent} run failed`, retryable: fail.retryable };
      }
      events.push(`result(${agent}: ok)`);
      return { ok: true };
    },
  };
}

async function dispatch(label, query, snapshot, runtime) {
  console.log(`\n▶ ${label}`);
  const plan = planQueryDispatch(query, snapshot);
  console.log(`  route : ${plan.reason} — [${plan.order.join(", ") || "∅"}] ${plan.explanation}`);
  if (plan.needsSetup) {
    console.log(`  setup : ${plan.needsSetup} not connected → guide install (no run, no silent fallback)`);
    return;
  }
  const outcome = await executeWithFallback(plan.order, {
    runOne: async (agent) => {
      await runtime.activateAdapter(agent);
      const r = await runtime.handleQuery(agent);
      if (!r.ok) throw new DispatchAttemptError(r.message, r.retryable);
    },
    isRetryable: (e) => (e instanceof DispatchAttemptError ? e.retryable : isDispatchRetryable(e)),
    log: (m) => console.log(`  log   : ${m}`),
  });
  console.log(`  ran   : ${runtime.events.join(" | ")}`);
  console.log(`  final : ${outcome.ok ? `handled by ${outcome.agent}` : "surfaced error to client"}`);
}

const connected = buildAvailabilitySnapshot({ piMono: true, hermes: true, openclaw: true, codex: true });

// a) explicit mention, connected
await dispatch('a) "use openclaw to build it" (OpenClaw connected)',
  { prompt: "use openclaw to build it" }, connected, makeRuntime());

// b) explicit mention, NOT connected
await dispatch('b) "use codex to add a test" (Codex NOT connected)',
  { prompt: "use codex to add a test" }, { ...connected, codex: false }, makeRuntime());

// c) no mention, capability match (task-type inferred from text)
await dispatch('c) "research the tradeoffs" (no agent named)',
  { prompt: "research the tradeoffs" }, connected, makeRuntime());

// d) primary can't activate -> fallback advances
await dispatch('d) adapterId=openclaw but its process won\'t start',
  { adapterId: "openclaw", prompt: "edit this file" }, connected,
  makeRuntime({ failActivation: new Set(["openclaw"]) }));

// e) NEW: primary RUN fails retryably -> fallback advances to the next agent
await dispatch('e) openclaw RUN fails (retryable) -> falls back',
  { adapterId: "openclaw", prompt: "edit this file" }, connected,
  makeRuntime({ runFailsOn: new Map([["openclaw", { retryable: true }]]) }));

// f) NEW: run fails NON-retryably -> surface immediately, no fallback
await dispatch('f) openclaw RUN fails (non-retryable) -> surfaced, no fallback',
  { adapterId: "openclaw", prompt: "edit this file" }, connected,
  makeRuntime({ runFailsOn: new Map([["openclaw", { retryable: false }]]) }));
