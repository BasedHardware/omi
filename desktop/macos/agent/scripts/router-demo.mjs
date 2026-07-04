// Standalone demo of the agent router + fallback, no real agents required.
// Build first (`npm run build`), then: `node scripts/router-demo.mjs`.
//
// Exercises the four Track-1 cases against a simulated availability snapshot
// and a simulated failing primary, printing the routing decision + fallback
// trail for each — same routing shape as live PTT, with a simplified harness.

import { resolveAgent, AGENT_DISPLAY_NAMES } from "../dist/runtime/agent-router.js";
import { DispatchAttemptError, isDispatchRetryable } from "../dist/runtime/dispatch-routing.js";
import { executeWithFallback } from "../dist/runtime/agent-fallback.js";

function show(title, plan) {
  console.log(`\n▶ ${title}`);
  console.log(`  decision : ${plan.reason}`);
  if (plan.needsSetup) console.log(`  setup    : ${AGENT_DISPLAY_NAMES[plan.needsSetup]} not connected → guide install`);
  console.log(`  plan     : ${plan.order.length ? plan.order.join(" → ") : "(none)"}`);
  console.log(`  says     : ${plan.explanation}`);
}

// (a) explicit mention, agent connected
show(
  'a) "use openclaw to refactor this" — OpenClaw connected',
  resolveAgent({ task: "use openclaw to refactor this", availability: { openclaw: true, hermes: true, codex: true } })
);

// (b) explicit mention, agent NOT connected
show(
  'b) "use codex to write tests" — Codex NOT connected',
  resolveAgent({ task: "use codex to write tests", availability: { codex: false, openclaw: true } })
);

// (c) no mention, multiple agents connected
show(
  'c) "research the best approach" — no agent named, several connected',
  resolveAgent({ task: "research the best approach", taskType: "research", availability: { openclaw: true, hermes: true, codex: true } })
);

// (d) primary fails → fallback triggers
console.log('\n▶ d) "edit this code" — primary crashes, fallback runs');
const plan = resolveAgent({ task: "edit this code", taskType: "code_edit", availability: { openclaw: true, hermes: true, codex: true } });
console.log(`  plan     : ${plan.order.join(" → ")}`);
const result = await executeWithFallback(plan.order, {
  runOne: async (agent) => {
    if (agent === plan.order[0]) throw new Error(`${agent} timed out`);
    return `completed by ${agent}`;
  },
  isRetryable: (error) =>
    error instanceof DispatchAttemptError ? error.retryable : isDispatchRetryable(error),
  log: (m) => console.log(`  log      : ${m}`),
});
console.log(`  result   : ${result.ok ? `✓ ${result.value}` : "✗ all agents failed"}`);
