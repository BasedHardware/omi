# Desktop Agent Runtime Architecture

This package is the local desktop agent daemon. It owns durable agent identity,
execution profiles, routing, context admission, run/attempt state, physical-tool
authorization, and the cross-surface conversation journal. Swift is a transport
and presentation client; adapters execute model work but do not own policy.

## Boundaries

```text
Swift desktop client
  <-> protocol.ts / index.ts (versioned JSONL transport)
       -> runtime/kernel.ts (public kernel facade)
          -> kernel-{core,sessions,runs,coordinator,artifacts}.ts
          -> desktop-intent-router.ts
          -> external-surface-tool-policy.ts
          -> context-snapshot.ts
          -> session-execution-profile.ts
          -> conversation-journal.ts
          -> run-tool-capability.ts -> tool-invocation-ledger.ts
          -> sqlite-store.ts (durable state)
       -> adapters/* (model-provider execution only)
       -> omi-tools-{stdio,http}.ts (generated physical-tool surfaces)
```

## Ownership rules

- `protocol.ts` defines every message crossing the Swift/Node boundary. New
  authority-bearing operations must be typed here and correlated to their
  persisted owner, session, run, attempt, and claim generation where applicable.
- `index.ts` validates transport envelopes and connects physical I/O to kernel
  operations. It must not reimplement routing, profile, journal, or capability
  policy.
- `runtime/kernel.ts` is the public facade. Its split `kernel-*` modules contain
  the implementation domains and may share the narrow types in `kernel-types.ts`.
- `desktop-intent-router.ts` is the sole semantic route decision owner. Callers
  use atomic route-and-apply operations rather than reproducing policy.
- `external-surface-tool-policy.ts` implements a kernel-owned proposal policy
  invoked by the atomic route/relay path for every surface. It may recover a
  malformed permission proposal into the native tool or reject an external-app
  target, and it gates pill visibility against the persisted user prompt. Swift
  and provider prompts never reimplement this decision.
- `session-execution-profile.ts` owns immutable, generation-fenced session
  profiles. Preference changes affect future sessions only unless an explicit
  migration succeeds.
- `context-snapshot.ts` owns versioned context source selection, admission, and
  rendering. Surface policy and tool capability fingerprints are distinct from
  the shared base-content version.
- `conversation-journal.ts` is the sole durable conversation writer. Backend
  synchronization and deletion use its owner-scoped outboxes; Swift performs
  physical HTTP only and returns exact claim receipts. Clear advances the
  journal generation, invalidates remote reconciliation, preserves only the
  identity of already-delivering POST claims, and gates both remote reads and
  new-generation POSTs until the backend DELETE is acknowledged.
- `run-tool-capability.ts` and `tool-invocation-ledger.ts` jointly authorize and
  record physical effects. Request IDs are tracing keys, never authorization.
- `sqlite-store.ts` owns schema creation, migrations, startup reconciliation,
  and transactions. Other modules do not issue lifecycle-altering schema DDL.
- `adapters/*` translate a pinned run into provider calls. They cannot choose a
  different provider, mutate a session profile, or directly execute desktop
  effects.
- `artifact-storage.ts` owns per-run managed artifact directories. Every leaf
  attempt receives that directory as both its adapter cwd and MCP workspace;
  delegated objectives and raw control-tool cwd values cannot default a
  deliverable to Desktop. Explicit external-delivery reports remain a narrow
  compatibility import path and are copied into the managed directory.
- Generated tool manifests and Swift executors are updated together through
  `../scripts/generate-tool-surfaces.mjs`; hand-edited capability mirrors are
  prohibited.

## Change checklist

When a change crosses an ownership boundary, add a behavioral contract test at
that boundary. Protocol changes require Swift and Node decode tests. Durable
changes require restart/idempotency tests. Provider or mode fallback paths must
use the repository's bounded fallback telemetry contract.
