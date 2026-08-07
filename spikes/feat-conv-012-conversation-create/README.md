# FEAT-CONV-012 conversation create/ingest spike

Disposable decision evidence only. Nothing in this directory is a production router,
contract, adapter, storage model, or migration. The three executable fixtures compare:

1. `prototypes/pipeline-entry.mjs` — capture creates a server-owned `in_progress`
   record; the legacy create route is only a current-record processing entry.
2. `prototypes/client-id-create.mjs` — a client-supplied `legacy UUID | word-slug`
   record id plus an opId ledger for create and processing.
3. `prototypes/hybrid.mjs` — client-created in-progress records and pipeline-created
   records share an opId ledger and can bind when identity/content agree; ambiguous
   binding fails closed instead of inventing merge semantics.

The fixtures intentionally model only identity, idempotency, lifecycle admission,
conflicts, and crash/retry behavior. They do not run LLM work, storage, webhooks,
deletion, billing, auth, deployment, or data migration.

Run:

```sh
npm test --prefix spikes/feat-conv-012-conversation-create
npm run demo --prefix spikes/feat-conv-012-conversation-create
```

Ruling of record: FEAT-CONV-012 is `open` / `defer`; ADR-004 supplies the shared
contract non-negotiables. The fixtures and accompanying tradeoff memo do not change
either state.
