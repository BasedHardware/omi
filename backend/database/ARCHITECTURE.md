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
- `recording_sessions.py` stores realtime recording bindings. `sync_jobs.py` and
  `sync_ledger.py` own job/run leases and durable upload completion. `sync_bridges.py`
  stores revision-checked cleanup receipts on retained donor tombstones; it performs
  no retraction or audio copying. Those effects run in `utils/sync/bridge.py`.
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
