# Omi Replay Harness — Phase 0A Offline-Sync Feasibility

**LIFECYCLE: permanent** — this is the Phase 0A feasibility experiment for the
[Omi Replay Harness](https://github.com/BasedHardware/omi/issues/10462). It is
a parallel, **non-merge-blocking** experiment alongside the existing
`sync_cloud_tasks_stack` gauntlet, which remains the blocking coverage.

## Thesis

Phase 0A proves a **declarative topology contract** can launch the offline-sync
SUT out-of-process with a **network Cloud Tasks control plane** and a
**self-consistent egress attestation** — capabilities the opaque merge-blocking
gauntlet structurally cannot offer.

The existing gauntlet (`sync_cloud_tasks_stack`) already runs separate
processes, but its topology is an opaque Python script (`run.py`), its Cloud
Tasks recorder is in-memory inside the admission process, and its egress guard
is loopback-only with no attestation. Phase 0A externalizes all three:

| Capability | Existing gauntlet | Phase 0A |
|---|---|---|
| Topology | Opaque `run.py` script | Declarative `topology.json` consumed by a generic launcher |
| Cloud Tasks | In-memory recorder in admission process | Out-of-process HTTP scheduler service (third network process) |
| Egress | Loopback-only block (any loopback peer) | Default-deny + enumerated allow-list + self-consistent attestation |
| Fault injection | Env-counter monkeypatches | Declared fault controls in the topology contract |

## What it proves

1. **Composition**: one synthetic PCM16 upload → admission → network Cloud Tasks
   loopback → worker → Firestore/Redis → deterministic finalizer fake → durable,
   retrievable terminal conversation. The out-of-process architecture composes.
2. **Generic launcher**: `runner.py` reads `topology.json`, allocates isolated
   ports, resolves placeholders, starts each role via its declared command, probes
   declared health endpoints, and builds an attestation. It contains zero
   sync-specific branching logic.
3. **Default-deny egress**: every guarded Python role (admission, worker,
   cloud-tasks-loopback) installs a socket guard with an explicit allow-list of
   declared fake endpoints. TCP connection-oriented sends
   (`connect`, `connect_ex`, `create_connection`), DNS resolution
   (`getaddrinfo`, `gethostbyname`, `gethostbyname_ex`), and UDP unconnected
   sends (`sendto`, `sendmsg`) are observed and enforced. The attestation
   recomputes every egress decision from raw evidence **and the checked-in
   topology contract** (host+port, not just port), and rejects summary/decision
   forgeries. The runner/orchestrator and non-Python dependency processes (Redis
   server, Firestore emulator JVM) are bind-constrained to loopback but not
   per-connection observed; this scope is stated explicitly.
4. **Regression-sensitive mutant proof (real boundary, no self-calling fake)**:
   three scenarios use the externally observable STT invocation count as the sole
   black-box signal (no white-box marker, no provider fake that calls itself
   twice):
   - **BASE** (unmutated, duplicate delivery): composition holds, STT = 1.
   - **MUTANT_UNGUARDED** (`OMI_REPLAY_DEFEAT_IDEMPOTENCY` + duplicate delivery):
     defeats the **actual** duplicate-delivery/idempotency/terminal-ownership
     boundary in the composed SUT (terminal-status guard, content-ledger
     convergence, staged-audio cleanup, processed-segment ledger). A real
     duplicate delivery then genuinely re-runs the real pipeline; the
     deterministic STT leaf invokes the provider once per real pipeline run, so
     STT ≥ 2 arises **only** because two real deliveries each run the pipeline.
     The scenario FAILS unless the real boundary defeat surfaces the defect.
   - **MUTANT_GUARDED** (`OMI_REPLAY_TERMINAL_GUARD_BYPASSED`, deeper defenses
     active): perturbs only the terminal guard; content-ledger convergence acks
     the redelivery without re-running — STT = 1 (defense-in-depth holds).

## Honest attestation scope (not over-claimed)

The egress attestation is **self-consistent recomputation**, NOT an independent
or third-party attestation of real kernel egress or of an OS listener:

- The raw evidence is emitted by the in-process socket guard and the runner
  launcher, both part of the SUT under test. The attestation proves the
  attestation *mechanism* composes end-to-end (every summary is recomputed from
  raw evidence + the checked-in contract, and any mismatch is rejected); it is
  not a security audit.
- The validator binds the artifact to the checked-in `topology.json` supplied
  independently, so a modified worker command with a recomputed embedded hash is
  rejected.
- The validator recomputes each egress decision from host+port (a remote host on
  a declared port is rejected), rather than trusting the recorded `decision`.
- The validator requires `guard_installed` evidence for every explicitly guarded
  Python role and explicitly exempts non-Python roles.
- The validator binds each role's artifact-controlled summary (port, pid,
  ready, probe) and the resolved ports map to a raw `role_allocated` launcher/
  health-observation record, which is itself validated against the checked-in
  topology health contract — endpoint host, probe contract, and ready-success
  semantics (an HTTP 500 readiness probe is rejected). This defeats a paired
  forgery of the summary and ports map. **It does not independently witness that
  an OS process listened on the port**: the `role_allocated` record is runner-
  emitted, so a fully coherent forgery of all raw evidence is outside what
  self-consistency attestation can detect.

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
- **No independent kernel-egress attestation**: evidence is SUT-emitted; see
  Honest attestation scope above.
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
3. Runs the **base** scenario (unmutated, duplicate delivery → STT = 1).
4. Tears down, relaunches, runs the **mutant-unguarded** scenario (full
   idempotency-boundary defeat + duplicate delivery → STT ≥ 2, defect induced).
5. Tears down, relaunches, runs the **mutant-guarded** scenario (terminal guard
   bypassed, deeper defenses active, duplicate delivery → STT = 1, defense holds).
6. Builds and validates a topology/egress attestation for each scenario.
7. Reports the feasibility outcome.

Each scenario uses a unique state root, unique ephemeral ports, and a unique UID.
All scenarios share the single Firestore emulator project namespace
(`demo-omi-replay-harness`) within one emulator invocation; isolation across
scenarios is by UID and state root, not by project namespace. Concurrent
invocations of the harness cannot collide because each uses a fresh emulator and
fresh ports.

## Files

| File | Role |
|---|---|
| `topology.json` | Declarative capability/topology contract |
| `runner.py` | Generic launcher (reads contract, starts roles, builds attestation) |
| `scenario.py` | Sync-specific test logic (upload, poll, assert, mutant) |
| `egress_guard.py` | Default-deny + allow-list + logging socket guard |
| `cloud_tasks_loopback.py` | Out-of-process Cloud Tasks HTTP scheduler service |
| `apps.py` | Role-configured ASGI entrypoint (admission + worker) |
| `attestation.py` | Attestation builder + self-consistent checker |
| `run.sh` | Firebase emulator wrapper |

## Design references

- [Issue #10462](https://github.com/BasedHardware/omi/issues/10462)
- [Behavior conformance spec](https://github.com/hermes/omi-knowledge/tree/main/projects/behavior-conformance-spec) — Phase 0A feasibility section
