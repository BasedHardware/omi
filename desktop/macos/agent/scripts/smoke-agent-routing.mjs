// On-device smoke check for spoken agent routing.
//
//   npm run build && node scripts/smoke-agent-routing.mjs
//
// Unlike scripts/demo-agent-routing.mjs, which fabricates a registry to show
// every branch, this one asks the machine it is running on. The inventory comes
// from `ensureRegisteredAdapter` — the same production gate `index.ts` uses at
// boot — so "connected" here means connected for real: that adapter's
// activation env var is set on this host. The assertions then run through the
// real kernel and the real `spawn_background_agent` control tool.
//
// The exit code is the result: 0 all checks passed, 1 a check failed, 2 the
// host is not macOS (pass --any-platform to run it anywhere).
//
// Checks needing an agent this host does not have are SKIPPED, never faked, and
// each skip names the env var that would enable it. To inspect the full matrix
// without installing anything:
//
//   node scripts/smoke-agent-routing.mjs --with=codex,hermes,openclaw
//
// --with sets those activation vars to a placeholder for this process only.
// Routing reads the capability matrix and never the command, so selection is
// unaffected — but nothing is spawned under --with, so use it to inspect
// routing, not to prove an agent runs.
//
// WHAT THIS DOES NOT COVER: the audio path. Nothing here presses push-to-talk
// or turns speech into text. It starts from the utterance a transcript
// produces, and covers everything after it.

import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { PRODUCTION_ADAPTER_IDS, adapterCapabilitiesFor } from "../dist/adapters/interface.js";
import { AdapterRegistry } from "../dist/runtime/adapter-registry.js";
import {
  ADAPTER_ACTIVATION_ENV,
  ensureRegisteredAdapter,
} from "../dist/runtime/adapter-selection.js";
import { handleAgentControlToolCall } from "../dist/runtime/control-tools.js";
import { AgentRuntimeKernel } from "../dist/runtime/kernel.js";
import { SqliteAgentStore } from "../dist/runtime/sqlite-store.js";

const argv = process.argv.slice(2);
const anyPlatform = argv.includes("--any-platform");
const withArg = argv.find((arg) => arg.startsWith("--with="));

if (process.platform !== "darwin" && !anyPlatform) {
  console.error(
    `This is the macOS on-device check and the host is ${process.platform}.\n` +
      "Re-run it on a Mac, or pass --any-platform to exercise the logic anywhere.",
  );
  process.exit(2);
}

// --with only flips activation vars. It cannot make an agent real.
const simulated = new Set();
if (withArg) {
  const ids = withArg.slice("--with=".length).split(",").map((s) => s.trim()).filter(Boolean);
  for (const id of ids) {
    const envName = ADAPTER_ACTIVATION_ENV[id];
    if (!envName) {
      console.error(`--with: ${id} has no activation env var (unknown id, or always on).`);
      process.exit(2);
    }
    if (!process.env[envName]?.trim()) {
      process.env[envName] = `# simulated by smoke-agent-routing --with=${id}`;
      simulated.add(id);
    }
  }
}

const bold = (s) => `\x1b[1m${s}\x1b[0m`;
const dim = (s) => `\x1b[2m${s}\x1b[0m`;
const green = (s) => `\x1b[32m${s}\x1b[0m`;
const red = (s) => `\x1b[31m${s}\x1b[0m`;
const yellow = (s) => `\x1b[33m${s}\x1b[0m`;

// ----------------------------------------------------------------- inventory

const dir = mkdtempSync(join(tmpdir(), "omi-routing-smoke-"));
const store = new SqliteAgentStore({ databasePath: join(dir, "agent.db"), reconcileOnOpen: false });
const registry = new AdapterRegistry();

const connected = [];
const missing = [];
for (const adapterId of PRODUCTION_ADAPTER_IDS) {
  // The production gate itself, not a reimplementation of it.
  const registered = ensureRegisteredAdapter(registry, adapterId, { log: () => {} });
  (registered ? connected : missing).push(adapterId);
}

const kernel = new AgentRuntimeKernel({ store, registry });
const context = { kernel, getOwnerId: () => "smoke-owner" };
const CODING_TASK = { needsTools: true };
const canEdit = (id) => adapterCapabilitiesFor(id).supportsTools;

console.log(bold(`\nOmi agent routing — on-device smoke  ${dim(`(${process.platform})`)}\n`));
console.log(`  ${bold("connected")}  ${connected.length ? connected.join(", ") : dim("none")}`);
for (const id of connected) {
  if (simulated.has(id)) {
    console.log(dim(`              ${id} — simulated by --with, not actually installed`));
  }
}
console.log(`  ${bold("missing")}    ${missing.length ? missing.join(", ") : dim("none")}`);
for (const id of missing) {
  console.log(dim(`              ${id} — set ${ADAPTER_ACTIVATION_ENV[id]} to connect`));
}

// -------------------------------------------------------------------- checks

let passed = 0;
let failed = 0;
let skipped = 0;

function pass(name, notes = []) {
  passed += 1;
  console.log(`\n  ${green("PASS")}  ${name}`);
  for (const line of notes) console.log(`        ${dim(line)}`);
}

function skip(name, reason) {
  skipped += 1;
  console.log(`\n  ${yellow("SKIP")}  ${name}`);
  console.log(`        ${dim(reason)}`);
}

function fail(name, message) {
  failed += 1;
  console.log(`\n  ${red("FAIL")}  ${name}`);
  console.log(`        ${message}`);
}

function check(name, fn) {
  let result;
  try {
    result = fn();
  } catch (error) {
    fail(name, error.message);
    return;
  }
  if (result?.skip) skip(name, result.skip);
  else pass(name, result?.notes ?? []);
}

function must(condition, message) {
  if (!condition) throw new Error(message);
}

console.log(bold("\n  Criterion 1 — name an agent, that agent runs it"));

check("a named, connected, tool-capable agent wins", () => {
  const named = connected.find((id) => id !== "acp" && canEdit(id));
  if (!named) {
    return { skip: "needs a connected non-default agent that supports tools; try --with=hermes" };
  }
  const utterance = `use ${named} to run the test suite`;
  const route = kernel.resolveAgentRoute(utterance, CODING_TASK);
  must(route.kind === "route", `expected a route, got ${route.kind}`);
  must(route.adapterId === named, `expected ${named}, got ${route.adapterId}`);
  must(route.explicit === true, "expected the route to be marked explicit");
  return { notes: [`"${utterance}" -> ${route.adapterId}`, `chain: ${route.chain.join(" -> ")}`] };
});

console.log(bold("\n  Criterion 2 — several connected, best first, the rest as fallback"));

check("no agent named: selected by capability, with a fallback chain", () => {
  const eligible = connected.filter(canEdit);
  if (eligible.length === 0) return { skip: "no connected agent declares supportsTools" };
  const route = kernel.resolveAgentRoute("fix the failing test", CODING_TASK);
  must(route.kind === "route", `expected a route, got ${route.kind}`);
  must(route.explicit === false, "expected an implicit, capability-driven selection");
  must(eligible.includes(route.adapterId), `${route.adapterId} is not tool-capable or not connected`);
  for (const id of route.chain) {
    must(connected.includes(id), `the chain names ${id}, which is not connected on this host`);
    must(canEdit(id), `the chain names ${id}, which cannot edit files`);
  }
  return {
    notes: [
      `"fix the failing test" -> ${route.adapterId}`,
      `chain: ${route.chain.join(" -> ")}`,
      eligible.length === 1 ? "only one eligible agent here, so the chain is a single hop" : "",
    ].filter(Boolean),
  };
});

check("an agent that cannot do the job is excluded, not silently substituted", () => {
  const toolless = connected.find((id) => !canEdit(id));
  if (!toolless) return { skip: "no connected agent declares supportsTools:false (openclaw does)" };
  const route = kernel.resolveAgentRoute(`use ${toolless} to edit these files`, CODING_TASK);
  must(
    route.kind !== "route" || route.adapterId !== toolless,
    `${toolless} was selected for a file-editing task it cannot do`,
  );
  if (route.kind === "route") {
    must(
      route.requestedButIneligible?.adapterId === toolless,
      "the user was not told why their named agent was not used",
    );
  }
  return {
    notes: [
      route.kind === "route"
        ? `${toolless} ruled out, ran ${route.adapterId}, and said why`
        : `${toolless} ruled out: ${route.kind}`,
    ],
  };
});

check("a ruled-out agent leaves the fallback chain too", () => {
  const eligible = connected.filter(canEdit);
  if (eligible.length < 2) {
    return { skip: "needs two tool-capable connected agents; try --with=hermes,codex" };
  }
  const excluded = eligible[1];
  const route = kernel.resolveAgentRoute(`fix this, but don't use ${excluded}`, CODING_TASK);
  must(route.kind === "route", `expected a route, got ${route.kind}`);
  must(route.adapterId !== excluded, `${excluded} was selected despite being ruled out`);
  must(
    !route.chain.includes(excluded),
    `${excluded} was excluded from selection but survived in the fallback chain`,
  );
  return {
    notes: [`"fix this, but don't use ${excluded}" -> ${route.adapterId}`, `chain: ${route.chain.join(" -> ")}`],
  };
});

console.log(bold("\n  Criterion 3 — name one you do not have, get help installing it"));

// Every missing agent is checked, not just the first. None of these spawn, so
// the pass is cheap and covers whichever agents this host happens to lack.
const absentAgents = missing.filter((id) => id !== "pi-mono");
if (absentAgents.length === 0) {
  skip(
    "a named, uninstalled agent answers with install guidance",
    "every user-installable agent is already connected on this host",
  );
}
for (const absent of absentAgents) {
  const name = `"${absent}" is not installed here: the request answers with guidance`;
  const utterance = `get ${absent} to review this diff`;
  try {
    // The real control tool, not just the router. An install_required route
    // returns before anything is spawned, so this starts no subprocess.
    const raw = await handleAgentControlToolCall(context, "spawn_background_agent", {
      prompt: utterance,
      title: "Agent routing smoke",
      externalRefKind: "pill",
      externalRefId: `smoke-pill-${absent}`,
      originSurfaceKind: "floating_bar",
      requestId: `smoke-install-${absent}-${Date.now()}`,
      clientId: "smoke-client",
      ownerId: "smoke-owner",
    });
    const result = JSON.parse(raw);
    const guidance = result.agentUnavailable;
    must(guidance, "the spawn did not report the agent as unavailable");
    must(guidance.adapterId === absent, `reported ${guidance.adapterId}, expected ${absent}`);
    // The invariant is that the answer is actionable, not that it is a command.
    // Hermes has no one-line install, so its guidance is a note plus a docs URL.
    must(
      guidance.commands?.length > 0 || Boolean(guidance.docsUrl),
      "the guidance offered neither an install command nor a docs link",
    );
    must(Boolean(guidance.message?.trim()), "the guidance carried no message");
    // The whole point: a missing agent must not be silently swapped for one
    // that happens to be connected.
    must(!result.session, "a session was created for an agent that is not installed");
    pass(name, [
      `"${utterance}"`,
      guidance.message,
      ...(guidance.commands ?? []).map((command) => `$ ${command}`),
      ...(guidance.docsUrl ? [guidance.docsUrl] : []),
    ]);
  } catch (error) {
    fail(name, error.message);
  }
}

// -------------------------------------------------------------------- result

console.log(
  `\n  ${bold(failed ? red("FAILED") : green("OK"))}  ` +
    `${passed} passed, ${failed} failed, ${skipped} skipped\n`,
);
if (skipped) {
  console.log(
    dim(
      "  A skip is an honest gap, not a pass: this host lacks the agents those checks\n" +
        "  need. Connect them, or re-run with --with=<ids> to inspect the routing.\n",
    ),
  );
}
console.log(dim("  Not covered: the audio path. This starts at the utterance, not the button.\n"));

store.close();
try {
  rmSync(dir, { recursive: true, force: true });
} catch {
  // The OS cleans temp.
}

process.exit(failed ? 1 : 0);
