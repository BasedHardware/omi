// Node harness for the LIVE dispatch wiring (index.ts query handler), with no
// process/sockets. It reproduces the exact composition index.ts now uses:
//
//   plan = planQueryDispatch(query, availabilitySnapshot())
//   if (plan.needsSetup) -> guide setup (no run)
//   executeWithFallback(plan.order, runOne = activateAdapter + facade.handleQuery)
//
// Build first (`npm run build`), then: `node scripts/dispatch-harness.mjs`.

import {
  planQueryDispatch,
  buildAvailabilitySnapshot,
  isDispatchRetryable,
} from "../dist/runtime/dispatch-routing.js";
import { executeWithFallback } from "../dist/runtime/agent-fallback.js";

// Simulated runtime: which agents activate, and a stand-in for facade.handleQuery.
function makeRuntime({ failActivation = new Set(), runFailsOn = new Set() } = {}) {
  const events = [];
  return {
    events,
    // Mirrors index.ts activateAdapter: throws (retryably) when an agent can't come up.
    activateAdapter: async (agent) => {
      if (failActivation.has(agent)) throw new Error(`${agent} is not available.`);
    },
    // Mirrors facade.handleQuery: on a terminal run failure it SENDS an error
    // event and RETURNS (does not throw) — the documented boundary.
    handleQuery: async (agent) => {
      if (runFailsOn.has(agent)) {
        events.push(`error-event(${agent}: run failed)`);
        return;
      }
      events.push(`result(${agent}: ok)`);
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
      await runtime.handleQuery(agent);
    },
    isRetryable: isDispatchRetryable,
    log: (m) => console.log(`  log   : ${m}`),
  });
  console.log(`  ran   : ${runtime.events.join(" | ")}`);
  console.log(`  final : ${outcome.ok ? `handled by ${outcome.agent}` : "all agents failed"}`);
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

// boundary) terminal RUN failure is swallowed by handleQuery -> no fallback yet
await dispatch('boundary) openclaw runs but the agent RUN fails (not activation)',
  { adapterId: "openclaw", prompt: "edit this file" }, connected,
  makeRuntime({ runFailsOn: new Set(["openclaw"]) }));
