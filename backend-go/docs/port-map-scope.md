# Port map scope

The map covers runtime Python sources that can change the Go port's behavior.
It includes the runtime Python sources cited by the
[finalization](contracts/finalization.md) and [batch](contracts/batch.md) contracts,
the family policy and implementation those entry points import, and selected
cross-family boundaries such as record custody during finalization. A file can
appear in both families. A match asks for a parity review, which can conclude
that the merged change needs no Go equivalent.

- Finalization includes admission and dispatch, quiet and merge jobs,
  retries and fences, terminal conversation writes, summary repair, and the
  episode and integration decisions made during finalization.
- Batch includes upload admission, custody, scheduling, recognition routing,
  projection, held recovery, and record-seal repair. It includes the
  batch-specific modules imported by the scheduler and sync route.

Shared dependencies outside these boundaries are excluded for the following
reasons.

| Excluded sources | Reason |
| --- | --- |
| `backend/database/_client.py`, `backend/database/firestore_transaction_retry.py`, `backend/database/read_boundary.py`, and `backend/database/rpc_deadline.py` | Shared Firestore access, retries, read errors, and deadlines are adapter infrastructure. Family-specific fences and transaction decisions are mapped. |
| `backend/utils/executors.py`, `backend/utils/http_client.py`, and `backend/utils/managed_compute.py` | Shared execution and client plumbing. Family scheduling, admission, and retry outcomes are mapped. |
| `backend/database/vector_db.py` and `backend/utils/memory/{canonical_consolidation,canonical_memory_adapter,memory_service,memory_system}.py` | Vector and memory internals have their own lifecycle. Finalization's decisions to invoke them are mapped. |
| `backend/utils/stt/{local_vad,modulate_batch,soniox_batch}.py` | Recognizer implementations belong to the speech adapter lane. Batch's vendor routing, admission, and outcome policy is mapped. |
| `backend/utils/other/{audio_opus,local_storage,raw_audio,storage}.py` | Shared codec and storage implementations. Batch and finalization's custody, source validation, and deletion decisions are mapped. |
| `backend/utils/sync/{files,legacy_dark,merge_audio,playback,playback_build}.py` | Legacy sync, file serving, and playback internals. Sync's batch-facing upload limits, status, custody, and recovery decisions are mapped. |
| `backend/testing/` and `backend/tests/` | Replay harnesses and tests exercise runtime policy. Their edits do not by themselves change that policy. |
| `backend/charts/batch-pipeline-worker/values.yaml` | The batch contract cites the deployed default for shard spread. This map follows Python runtime sources, including the corresponding default in `backend/config/batch_pipeline.py`. |

Update the map when moving a covered module or extracting family behavior into
a new file. A new path belongs in every family whose port needs to review it.
