# Desktop agent routing (spoken agent selection)

A task can name its agent out loud ("use codex to fix this"). Selection is
deterministic — no model in the loop.

macOS runtime, `desktop/macos/agent/src/runtime/`:

| Module | Answers |
|---|---|
| `agent-mention.ts` | Which agent did the user name, and which did they rule out |
| `adapter-scoring.ts` | Which connected agents can do this task, best first |
| `agent-install.ts` | What to tell a user who named an agent they have not installed |
| `agent-routing.ts` | Composes the three into one decision |
| `agent-fallback.ts` | Retries a failed run on the next agent in the chain |

Windows mirrors the utterance half in `desktop/windows/src/main/codingAgent/agentMention.ts`
(`agentsForTask` in `taskRunner.ts`); it already had the fallback loop macOS was
missing.

## Rules

The routing suites and the parity fixture enforce these; a change that breaks one
fails those suites rather than passing quietly.

1. **Selection reads the capability matrix, never a model.** `DesktopIntentRouter`
   documents that it has no language heuristics; keep string matching at the
   surface and capability facts in `desktop/macos/agent/src/adapters/interface.ts`. An agent that declares
   `supportsTools: false` is ineligible for a tool task as a fact, and the user is
   told why rather than silently given a different agent.
2. **An explicitly requested adapter is never substituted.** A caller that passes
   `adapterId` gets exactly that agent; only an unnamed task may be ranked.
3. **A ruled-out agent is dropped from the chain, not just from selection.**
   "don't use hermes" is not honoured by a runtime that starts elsewhere and then
   falls back to Hermes.
4. **Fallback reacts to the terminal run event, never to the spawn.**
   `spawnBackgroundAgent` returns a receipt and runs the adapter asynchronously
   (`void execution` in `kernel-runs.ts`), so a spawn-time retry loop cannot
   observe the failure it is meant to recover from. The untried chain rides on run
   metadata (`agentFallbackChain`) and `agent-fallback.ts` subscribes to
   `run.failed`. The retry records what it replaced in `agentFallbackFrom`.
   Because that metadata is caller-supplied, `agentFallbackPlanForRun`
   re-validates the chain on read — a retry may only target a production adapter
   that is currently registered — so a hand-written chain cannot point the retry
   at an arbitrary or unregistered provider.
5. **Alias and negation rules are a cross-platform contract.** They are
   implemented twice (macOS + Windows) and pinned by
   `contracts/parity/agent_routing.json`; change behaviour by editing the fixture,
   and both conformance suites must pass.

## Adapter activation and credentials

External adapters are activated by command env vars, one per agent:
`OMI_CODEX_ADAPTER_COMMAND`, `OMI_HERMES_ADAPTER_COMMAND`,
`OMI_OPENCLAW_ADAPTER_COMMAND`. `adapterIsActivated` in
`desktop/macos/agent/src/runtime/adapter-selection.ts` reads them, and `ensureRegisteredAdapter` is the
boot-time gate that decides what "connected" means.

Each external adapter receives its own credentials only —
`ADAPTER_SPECIFIC_ENV_ALLOWLIST` in `desktop/macos/agent/src/adapters/acp.ts` is keyed by adapter id,
because these commands run under `shell: true` and one agent's API key must never
reach another. Adding a key to the shared allowlist instead would hand it to every
external agent.

## Checking it on a real machine

```bash
cd desktop/macos/agent && npm run smoke:agent-routing
```

`desktop/macos/agent/scripts/smoke-agent-routing.mjs` takes its inventory from
`ensureRegisteredAdapter`, the same gate `index.ts` uses at boot, so "connected"
means connected on that host. It then asserts the routing behaviours through the
real kernel and the real `spawn_background_agent` control tool, and exits non-zero
on failure.

A check needing an agent the host lacks is skipped and names the env var that
would enable it, rather than being faked, so the output cannot overstate what ran.
`--with=<ids>` flips activation vars for one process to inspect the full matrix,
and labels those agents as simulated. Nothing spawns a subprocess: the
`install_required` branch returns before one starts.

It starts at the utterance a transcript produces. **The audio path above it —
push-to-talk, capture, transcription — is not covered by this script.**

## Tests

`desktop/macos/agent/tests/`: `agent-mention`, `adapter-scoring`, `agent-routing`,
`agent-routing-kernel`, `agent-routing-continuation`, `agent-fallback`,
`agent-install`, `parity-agent-routing`, `adapter-selection`, `runtime-adapter`.

Windows: `desktop/windows/src/main/codingAgent/parityAgentRouting.test.ts` and `taskRunner.test.ts`.

Both platforms run the same vectors from `contracts/parity/agent_routing.json`
through their own production code; see `contracts/parity/README.md`.
