# Omi Replay Harness — Phase 0A Offline-Sync Feasibility

**LIFECYCLE: permanent** — this is the Phase 0A feasibility experiment for the
[Omi Replay Harness](https://github.com/BasedHardware/omi/issues/10462). It is
a parallel, **non-merge-blocking** experiment alongside the existing
`sync_cloud_tasks_stack` gauntlet, which remains the blocking coverage.

## Thesis

Phase 0A proves a **declarative topology contract** can launch the offline-sync
SUT out-of-process with a **network Cloud Tasks control plane** and a
**third-party-verifiable egress attestation** — capabilities the opaque
merge-blocking gauntlet structurally cannot offer.

The existing gauntlet (`sync_cloud_tasks_stack`) already runs separate
processes, but its topology is an opaque Python script (`run.py`), its Cloud
Tasks recorder is in-memory inside the admission process, and its egress guard
is loopback-only with no attestation. Phase 0A externalizes all three:

| Capability | Existing gauntlet | Phase 0A |
|---|---|---|
| Topology | Opaque `run.py` script | Declarative `topology.json` consumed by a generic launcher |
| Cloud Tasks | In-memory recorder in admission process | Out-of-process HTTP scheduler service (third network process) |
| Egress | Loopback-only block (any loopback peer) | Default-deny + enumerated allow-list + machine-verifiable attestation |
| Fault injection | Env-counter monkeypatches | Declared fault controls in the topology contract |

## What it proves

1. **Composition**: one synthetic PCM16 upload → admission → network Cloud Tasks
   loopback → worker → Firestore/Redis → deterministic finalizer fake → durable,
   retrievable terminal conversation. The out-of-process architecture composes.
2. **Generic launcher**: `runner.py` reads `topology.json`, allocates isolated
   ports, resolves placeholders, starts each role via its declared command, probes
   declared health endpoints, and builds an attestation. It contains zero
   sync-specific branching logic.
3. **Default-deny egress**: every role installs a socket guard with an explicit
   allow-list of declared fake endpoints. Every connection attempt is logged,
   then allowed or denied. The attestation proves zero denied attempts.
4. **Declared fault mutant**: a `terminal_guard_bypassed` fault control (declared
   in the topology contract) bypasses the worker's terminal-status guard. The
   loopback delivers the same task twice (at-least-once). Without the fault:
   one STT invocation (idempotency holds). With the fault: two STT invocations
   (defect caught).

## What it does NOT prove (feasibility-only boundaries)

- **No STT/LLM fidelity**: the deterministic VAD/STT/process_conversation leaves
  are canned responses, not wire-fidelity oracles. They prove the pipeline
  composes, not that transcripts are faithful.
- **No persist-before-send**: left as residue until an operation-scoped
  storage-fault seam exists.
- **No production Cloud Tasks equivalence**: the loopback is a minimal stateful
  scheduler model, not a faithful control plane. Named-task dedup and
  at-least-once delivery are preserved; retry/backoff/deadline semantics are not.
- **No capture/WS transport**: input is one synthetic PCM16 upload via
  `/v2/sync-local-files`, not replay of captured client traffic.
- **No LC3 codec path**: PCM16 only.
- **No release gate**: this experiment is advisory, not merge-blocking.
- **`_tasks_client` seam**: production `_get_tasks_client()` has no endpoint
  override, so the admission process swaps the global client to an HTTP forwarder.
  This is a labeled feasibility-only seam, not a production transport.

## How to run

```bash
npm run test:replay-harness-phase0a:emulator
```

Requires: backend `.venv` (`backend/scripts/sync-python-deps.sh`), Node
dependencies (`npm ci`), Java 21+ (Firestore emulator), Redis, Firebase CLI.

The runner:
1. Starts a Firebase Firestore emulator on a random loopback port.
2. Launches the generic runner, which reads `topology.json` and starts:
   - Redis (bind 127.0.0.1, ephemeral port)
   - Cloud Tasks loopback (HTTP server, ephemeral port)
   - Worker ASGI (uvicorn, ephemeral port)
   - Admission ASGI (uvicorn, ephemeral port)
3. Runs the **base** scenario (unmutated, duplicate delivery → one STT).
4. Tears down, relaunches, runs the **mutant** scenario (terminal guard
   bypassed, duplicate delivery → two STT, defect caught).
5. Builds and validates a topology/egress attestation for each scenario.
6. Reports the feasibility outcome.

Each scenario uses a unique state root, unique ports, and a unique Firestore
project namespace — concurrent invocations cannot collide.

## Files

| File | Role |
|---|---|
| `topology.json` | Declarative capability/topology contract |
| `runner.py` | Generic launcher (reads contract, starts roles, builds attestation) |
| `scenario.py` | Sync-specific test logic (upload, poll, assert, mutant) |
| `egress_guard.py` | Default-deny + allow-list + logging socket guard |
| `cloud_tasks_loopback.py` | Out-of-process Cloud Tasks HTTP scheduler service |
| `apps.py` | Role-configured ASGI entrypoint (admission + worker) |
| `attestation.py` | Attestation builder + independent checker |
| `run.sh` | Firebase emulator wrapper |

## Design references

- [Issue #10462](https://github.com/BasedHardware/omi/issues/10462)
- [Behavior conformance spec](https://github.com/hermes/omi-knowledge/tree/main/projects/behavior-conformance-spec) — Phase 0A feasibility section
