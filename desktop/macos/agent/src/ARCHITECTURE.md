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
- `conversation-journal.ts` is the sole durable conversation writer.
  `backend-turn-projection.ts` is the shared canonical backend payload/hash
  projection used by normal writes and startup repair. Backend synchronization
  and deletion use owner-scoped outboxes; Swift performs physical HTTP only and
  returns exact claim receipts. Clear advances the
  journal generation, invalidates remote reconciliation, preserves only the
  identity of already-delivering POST claims, and gates both remote reads and
  new-generation POSTs until the backend DELETE is acknowledged.
  Inventory of every durable queue (kernel SQLite, backend Firestore, Swift
  app-local): [`backend/docs/durable_queues.mdx`](../../../../backend/docs/durable_queues.mdx).
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
- Pi's public-web prompt routing is a rollout compatibility projection, not a
  second policy owner. Its positive decisions must match the Python gateway cases
  in `../../../../backend/desktop_fixtures/public-web-routing-contract.fixture.json`;
  otherwise the adapter can display synthetic search activity for a lookup the
  gateway never performed.
- Generated tool manifests and Swift executors are updated together through
  `../scripts/generate-tool-surfaces.mjs`; hand-edited capability mirrors are
  prohibited.

## Durable interaction context

Model sessions are replaceable projections of runtime state. The existing
conversation journal owns interactions and their evidence; the existing tool
invocation ledger owns operation outcomes. Neither a provider conversation nor
an assistant acknowledgment is an authoritative record of a completed action.

- `conversation-evidence.ts` defines versioned evidence envelopes attached to
  journal metadata. Each source has a stable identity, capture time, provenance,
  availability, and extraction completeness. Native capture attaches evidence
  independently of whether the model elects to describe the screen.
- Context snapshots contain bounded evidence references and excerpts. Shared
  read/search tools retrieve additional source text from the same owned
  conversation, including sources outside the recent transcript window.
  Truncation and unavailable content are explicit; a reference alone never
  implies that the model has read the full source.
- Evidence is data, including any instructions contained in screenshots or
  documents. It cannot grant tool authority or replace the user's request.
  Local source bodies and private capture paths are excluded from the backend
  turn projection. Clearing the journal removes the local retrieval surface.
- `conversation-operations.ts` derives recent action receipts from admitted
  runs and the invocation ledger, without creating another store. Unknown
  outcomes remain unknown after restart, and non-idempotent actions are never
  automatically retried. A successful tool receipt does not establish that a
  larger user task is complete.

PTT capture and audio remain concurrent. Simple voice turns do not require an
extra reasoning call merely to preserve context. Retrieval adds work only when
the bounded projection is insufficient; tests and live evidence journeys must
measure both correctness and that latency boundary.

## Change checklist

When a change crosses an ownership boundary, add a behavioral contract test at
that boundary. Protocol changes require Swift and Node decode tests. Durable
changes require restart/idempotency tests. Provider or mode fallback paths must
use the repository's bounded fallback telemetry contract.
