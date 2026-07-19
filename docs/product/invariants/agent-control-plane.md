# INV-AGENT-*: Agent control-plane contracts

**Status:** locked
**Statement:** Omi owns session/run/attempt identity, authority, and lifecycle;
adapters are bound under that control plane. Future PRs that touch the runtime
must name the invariant they affect and update the matching guard test.

## MUST NOT

- Conflate Omi IDs with adapter-native session IDs.
- Authorize control operations from tool-supplied `ownerId` alone.
- Allow more than one non-terminal attempt with execution authority per run.
- Key request-scoped state by bare `requestId` under concurrent clients.
- Treat backend workstream product state or another runtime's checkpoint as
  authority for this runtime's run/attempt status.
- Keep a local task Candidate in an independent review state after a canonical
  backend receipt exists.
- Select an adapter outside the session's persisted provider boundary.
- Grant leaf workers agent-management tools or nested-agent authority.
- Persist a successful run while a required control operation remains failed.
- Let request/client correlation, a Swift callback, or possession of an opaque
  capability reference authorize a physical tool invocation.
- Mutate a live session's adapter/model/cwd because the default preference
  changed; defaults apply to new sessions and migration is explicit.
- Assemble policy or model context from Swift-supplied prompt fragments.

## Converged authority contract

- The kernel routes a typed intent proposal and applies the resulting control
  action in one boundary. Swift does not run a second semantic classifier.
- Each session pins an immutable, generation-numbered execution profile. An
  idle session can migrate only through an expected-generation transaction;
  active runs reject migration.
- Each accepted run pins one versioned, generation-numbered ContextSnapshot.
  Source updates declare `available`, `empty`, `unavailable`, or `redacted`;
  kernel policy, renderer version, recent turns, and capability projection are
  not caller-selected prompt text.
- Run/attempt capability checks stay inside the kernel. Before Swift sees a
  physical command, the kernel persists a single-use invocation as `prepared`
  and transitions it to `dispatched`. Restart changes `prepared` to `failed`
  and `dispatched` to `outcome_unknown`; non-idempotent writes are never
  automatically replayed.
- An accepted control invocation holds a kernel execution lease, not request
  lifetime authority. The lease revalidates owner, live run/attempt, and pinned
  execution profile at each physical effect boundary, propagates abort to
  in-flight adapter work, and terminalizes revocation as `failed` before
  dispatch or `outcome_unknown` after dispatch. A multi-agent control call
  revalidates between siblings, retains every admitted child, and immediately
  cancels admitted siblings if a later admission fails; cleanup failures expose
  the admitted run IDs instead of leaving invisible work.
- Every local runtime harness establishes the signed-in owner before its first
  owner-scoped RPC, even when the adapter needs no Firebase token. Query,
  interrupt, warmup, and session-invalidation transport mutations reject a
  caller owner that differs from the active runtime owner.
- Swift treats the runtime `init` handshake as a compatibility boundary: the
  negotiated protocol version must match exactly and every required capability
  must be declared before the runtime becomes ready. Missing or stale
  capabilities fail startup closed instead of surfacing later as unknown wire
  messages.
- Owner replacement is a correlated pre-visibility barrier. Node first makes
  the previous owner inert, synchronously terminalizes its foreground/external
  runs, pending tool claims, and session bindings, then returns an exact-owner
  receipt. Swift fully drains physical tool tasks and stops the child process
  before the replacement owner can become visible; a missing, malformed, or
  timed-out receipt also fails closed by confirming process exit.
- Swift owner-scoped work carries an immutable owner plus authorization
  generation through startup, wire admission, response routing, callbacks,
  credentials, and local/API mutations. Signing out and back into the same uid
  is a new generation and cannot revive an earlier continuation.
- Swift validates and executes only `authorized_tool_execution`, echoing the
  complete immutable claim tuple and generated manifest digest. Ordinary
  `tool_use` events are display-only.
- Control-plane list operations return bounded summaries, never complete
  persisted run inputs, surface context, results, or metadata. Detail remains an
  explicit run lookup, and realtime provider responses enforce a byte ceiling so
  one oversized tool result cannot tear down the voice session.
- Session archival state is not run lifecycle. A PTT or chat request for a
  completed child must discover the recent canonical child run and answer from
  its bounded final result (or explicit run inspection); it must never infer
  completion from `sessions.status` or filter away an open reusable session as
  though it were still running. Legacy child-discovery requests that say
  `closed` retain that user intent by selecting terminal runs, not archived
  sessions.
- A realtime spawn acknowledgement is an admission receipt, not a child
  completion claim. The kernel derives that acknowledgement deterministically;
  only the canonical child run's terminal lifecycle may report completion,
  failure, cancellation, or timeout. The receipt is persistence-only: it
  records the canonical journal fact but does not claim a deterministic local
  TTS lease or stop the native realtime stream. The active provider's post-tool
  continuation is the sole audible response for the spawned turn; any pre-tool
  speculation is cleared so it stays out of the visible reply without
  interrupting the native voice lane, and the turn advances from that provider
  continuation rather than from the receipt itself. Session-refresh recovery
  must recognize that validated receipt as committed work and never replay it
  into a duplicate child run.
- Workstream consolidation moves task-scoped history through the canonical
  journal migration transaction, preserving typed payloads, revisions, outbox
  state, sequencing, and restart visibility; it never inserts or deletes turn
  rows directly.

## Surfaces

- Desktop TypeScript agent runtime (`desktop/macos/agent/src/runtime`)
- Adapter bindings, control tools, request-scoped relay, startup reconciliation
- Adapter credential scopes, session execution roles, and terminal control obligations

## Guard tests

Documented per-invariant in the canonical invariants doc, including:

- `desktop/macos/agent/tests/runtime-adapter.test.ts`
- `desktop/macos/agent/tests/run-attempt-lifecycle.test.ts`
- `desktop/macos/agent/tests/adapter-binding.test.ts`
- `desktop/macos/agent/tests/control-tools.test.ts`
- `desktop/macos/agent/tests/sqlite-store.test.ts`
- `desktop/macos/agent/tests/workstream-continuity.test.ts`
- `desktop/macos/agent/tests/desktop-intent-router.test.ts`
- `desktop/macos/agent/tests/session-execution-profile.test.ts`
- `desktop/macos/agent/tests/run-tool-capability.test.ts`
- `desktop/macos/agent/tests/convergence-authority-ratchet.test.ts`
- `desktop/macos/agent/tests/runtime-stdio-contract.test.ts`
- `desktop/macos/agent/tests/cross-surface-contract-smoke.test.ts`
- `desktop/macos/Desktop/Tests/AuthorizedToolExecutionTests.swift`
- `desktop/macos/Desktop/Tests/KernelContractWireTests.swift`
- `desktop/macos/Desktop/Tests/AgentRuntimeStatusStoreTests.swift`

## Path globs

- `desktop/macos/agent/src/runtime/**`
- `docs/doc/developer/agent-control-plane.mdx`
- `docs/doc/developer/agent-control-plane-invariants.mdx`

## PR rule

Name the specific control-plane invariant (or `INV-AGENT-*`) in the PR body if
you touch the path globs above. Prefer the named sections in the canonical doc
(Identity, Authority, Lifecycle, …).

## Canonical docs (do not duplicate)

- [`docs/doc/developer/agent-control-plane.mdx`](../../doc/developer/agent-control-plane.mdx)
- [`docs/doc/developer/agent-control-plane-invariants.mdx`](../../doc/developer/agent-control-plane-invariants.mdx)
