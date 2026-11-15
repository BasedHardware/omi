# Persistence boundaries

This package owns durable storage primitives and their transaction fences. Domain
orchestration belongs in `utils/` and `services/`; HTTP policy belongs in `routers/`.
Do not make a hard-delete primitive call back into conversation orchestration.

- `_client.py` supplies lazy Firestore clients, transaction execution and recursive
  subcollection deletion. New adapters obtain clients at call time and accept
  injected clients for hermetic tests.
- `helpers.py` owns encryption/read-write codecs. Conversation transcript fields
  are opaque at rest; new writes default to enhanced protection.
- `conversations.py` owns conversation documents, lifecycle persistence/revision
  checks and transcript codecs. Its hard-delete primitive purges subcollections
  and the document; user/source deletion orchestrators own external artifacts.
- `transcript_search.py` pages saved transcript reads through those same codecs,
  visibility and correction projections. Query-bound signed bookmarks and fixed
  document/deadline budgets (including correction projection in scan and exact reads) provide recall over unindexed old and new recordings
  without any new persistence or external index writes.
- `recording_sessions.py` stores realtime recording bindings. `sync_jobs.py` and
  `sync_ledger.py` own job/run leases and durable upload completion. `sync_bridges.py`
  stores revision-checked cleanup receipts on retained donor tombstones; it performs
  no retraction or audio copying. Those effects run in `utils/sync/bridge.py`.
- `smart_merge.py` owns the smart-merge absorb transaction; `smart_merge_audit.py`
  stages its content-free `users/{uid}/smart_merge_audit` sibling in that same
  transaction behind the destructive-operation gate (outside conversation cascades).
- Domain stores such as `users.py`, `action_items.py`, `memories.py`, `folders.py`,
  `calendar_meetings.py` and `chat.py` own their document operations. Memory ledger,
  projection-repair and account-deletion stores retain their authority fences.
- `redis_db.py`, `cache.py` and `redis_pubsub.py` own cache/pubsub adapters;
  `vector_db.py` owns vector storage. External effects cannot join a Firestore
  transaction and require explicit retry/convergence at the caller.
- `firestore_index_registry.py` and `firestore_read_metrics.py` describe query/read
  contracts. `backend/AGENTS.md` owns setup, safety and test-runner instructions.

Transaction tests use the strict Firestore fixture. It checks read-before-write
ordering; it does not simulate production contention or external-service retries.

- `ports/` contains storage-neutral typed protocols and entities. `space_store.py` supplies the Firestore per-space unit of work; folders/people repositories implement the ports while retaining typed module-function entry points. Action items, goals and workstreams implement typed repository ports while preserving their existing module dict/wire-model signatures. Transaction bodies are restartable and must finish all reads before the first write.

- `action_item_fence.py` supplies explicit Redis writer tickets at task commits.
  `SpaceStore.run` starts per-attempt commit fences after the body returns and
  releases every attempt on exit; only the final committed attempt publishes
  effects. Standalone writers own their fence context and existing retry policy.
  The task SDK monkey patch is retired; memory heads, list projection and batch
  privacy SDK hooks remain unchanged. Goal lifecycle detaches and refresh
  delivery claims also fence their task writes.
- The simulator in `testing/domain_sim/store.py` independently models task
  workflow state. Sim/emulator conformance covers cross-domain relationships,
  rollback, revisions, receipts, list and sync keysets, lifecycle and journals.
  Cell adapters are deferred to A2b; no runtime selector or serving flag is added.

### Typed cell domain adapters (A2b)

`database.cells.adapters.CellSpaceStore` is the lazy public composition entry
point, implemented by `database/cells/adapters/space_store.py`. It composes folders, people, action items,
goals and workstreams over the single `CellStore.run` flush path. An attempt-local
identity map buffers domain changes; SQL lists apply predicates, keysets and
limits before materializing results and overlay pending UoW edits. Task writer
tickets span flush and connection commit, with one post-commit list-version bump
per changed UoW. Domain result receipts and native content-free replay receipts
commit atomically. Typed query columns understand the shared codec's tagged
datetimes (`0004_task_workflow_typed.sql`, after B2's `0002_write_fence.sql`).
Only the synthetic domain conformance harness selects these adapters. Serving
routing and `CELL_STORE_MODE` are unchanged; B2 enrollment/write fences remain
required before any serving use. Adding stored columns requires an exclusive
lock and must happen before enrollment.

Legacy cell payloads need not duplicate their document key in an `id` field.
Read projections restore `id` from the key without rewriting the payload;
retirement and relationship operations also use document keys as identity.
Cell-native creates currently include a redundant `id` (Firestore creates may
omit it). This is an explicit metadata exception to byte parity: the shared
codec preserves the same content values, while W6 backfill must retain legacy
payloads verbatim and never depend on the redundant `id` being present.
