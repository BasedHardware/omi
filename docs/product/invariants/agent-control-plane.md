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

## Surfaces

- Desktop TypeScript agent runtime (`desktop/macos/agent/src/runtime`)
- Adapter bindings, control tools, request-scoped relay, startup reconciliation

## Guard tests

Documented per-invariant in the canonical invariants doc, including:

- `desktop/macos/agent/tests/runtime-adapter.test.ts`
- `desktop/macos/agent/tests/run-attempt-lifecycle.test.ts`
- `desktop/macos/agent/tests/adapter-binding.test.ts`
- `desktop/macos/agent/tests/control-tools.test.ts`
- `desktop/macos/agent/tests/sqlite-store.test.ts`

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
