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
- Swift validates and executes only `authorized_tool_execution`, echoing the
  complete immutable claim tuple and generated manifest digest. Ordinary
  `tool_use` events are display-only.

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
- `desktop/macos/Desktop/Tests/AuthorizedToolExecutionTests.swift`
- `desktop/macos/Desktop/Tests/KernelContractWireTests.swift`

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
