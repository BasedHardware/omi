// Live walkthrough of agent routing, against the compiled runtime in dist/.
//
// Run: npm run build && node scripts/demo-agent-routing.mjs
//
// Each scenario is one of the three behaviours Track 1 asks for, run through a
// real AgentRuntimeKernel with a real AdapterRegistry and a real SQLite store.
// Nothing is stubbed except the adapter factories, which are never invoked —
// selection reads the declared capability matrix, not a live process.

import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { AdapterRegistry } from "../dist/runtime/adapter-registry.js";
import { AgentRuntimeKernel } from "../dist/runtime/kernel.js";
import { SqliteAgentStore } from "../dist/runtime/sqlite-store.js";

const CODING_TASK = { needsTools: true };

const dir = mkdtempSync(join(tmpdir(), "omi-routing-demo-"));
const store = new SqliteAgentStore({
  databasePath: join(dir, "agent.db"),
  reconcileOnOpen: false,
});

function kernelWith(...adapterIds) {
  const registry = new AdapterRegistry();
  for (const adapterId of adapterIds) {
    // Never called: resolveAgentRoute only reads the registered ids and the
    // declared capability matrix.
    registry.register(adapterId, () => {
      throw new Error("adapter factory is not used by routing");
    }, 1);
  }
  return new AgentRuntimeKernel({ store, registry });
}

const dim = (s) => `\x1b[2m${s}\x1b[0m`;
const bold = (s) => `\x1b[1m${s}\x1b[0m`;
const green = (s) => `\x1b[32m${s}\x1b[0m`;
const yellow = (s) => `\x1b[33m${s}\x1b[0m`;

let scenarioNumber = 0;
function scenario(title, connected, utterance) {
  scenarioNumber += 1;
  const kernel = kernelWith(...connected);
  const route = kernel.resolveAgentRoute(utterance, CODING_TASK);

  console.log(`\n${bold(`${scenarioNumber}. ${title}`)}`);
  console.log(dim(`   connected: ${connected.join(", ")}`));
  console.log(`   user says: ${bold(`"${utterance}"`)}`);

  if (route.kind === "install_required") {
    console.log(`   ${yellow("→ not connected")}  ${route.adapterId}`);
    console.log(`   ${route.guidance.message}`);
    for (const command of route.guidance.commands) {
      console.log(`     ${green("$")} ${command}`);
    }
    if (route.guidance.docsUrl) console.log(dim(`     docs: ${route.guidance.docsUrl}`));
    return;
  }

  if (route.kind === "no_agent_available") {
    console.log(`   ${yellow("→ nothing can run this")}`);
    for (const reason of route.reasons) console.log(dim(`     ${reason}`));
    return;
  }

  console.log(
    `   ${green("→ runs on")} ${bold(route.adapterId)}` +
      dim(route.explicit ? "  (named by the user)" : "  (selected by capability)"),
  );
  console.log(dim(`     fallback order: ${route.chain.join(" → ")}`));
  if (route.requestedButIneligible) {
    console.log(
      `     ${yellow("note:")} ${route.requestedButIneligible.adapterId} was asked for but cannot ` +
        `run this task (missing ${route.requestedButIneligible.missing.join(", ")})`,
    );
  }
  for (const reason of route.reasons) console.log(dim(`     ${reason}`));
}

console.log(bold("\nOmi Track 1 — agent routing, running against dist/\n"));

// Test 1: name an agent, that agent runs the task.
scenario("Named agent runs the task", ["acp", "hermes", "openclaw"], "use hermes to run the test suite");

// Test 3: name an agent that isn't connected, get help installing it.
scenario("Named agent isn't installed", ["acp", "hermes"], "get codex to review this diff");

// ...and the same sentence once Codex is connected: it simply runs.
scenario("Same request, Codex connected", ["acp", "codex"], "get codex to review this diff");

// Test 2: several connected, pick the best and keep a fallback chain.
scenario("No agent named — pick the best", ["acp", "hermes", "openclaw"], "fix the failing test");

// The capability matrix doing real work: OpenClaw declares supportsTools:false.
scenario("Named agent can't do the job", ["acp", "openclaw"], "use openclaw to edit these files");

// Negation is clause-scoped, so the second agent survives.
scenario("Ruling one agent out", ["acp", "hermes"], "fix this, but don't use hermes");

// Nothing eligible at all.
scenario("Nothing can run it", ["openclaw"], "edit these files");

console.log(
  dim("\nBefore this change every line above ran on the default adapter (acp), silently.\n"),
);

store.close();
try {
  rmSync(dir, { recursive: true, force: true });
} catch {
  // Windows may still hold the file; the OS cleans temp.
}
