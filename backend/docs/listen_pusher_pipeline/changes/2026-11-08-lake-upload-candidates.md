# Durable discovery of unreferenced lake uploads

Every lake put first persists a content-free, create-only intent in the customer
Firestore plane at `lake_upload_candidates/{sha256(bucket + '/' + object_key)}`.
The row contains only `bucket`, `key` and UTC `created_at`; it has no TTL. Failure
to read/create the intent refuses the upload. Existing intents and concurrent
creates are idempotent and retain the original creation time.

An intent precedes the GCS write, so refused transaction replays, superseded
sources, bounded retry exhaustion, deferred-swap CAS failures, ambiguous upload
responses and worker loss leave durable sweep discovery. Successful pointers
retain their intents too: an intent is a candidate, never proof of an orphan.
No serving-path deletion is added, because another writer may reference the
same content-addressed object even when the current writer refuses its pointer.

C3 owns candidate consumption. Its janitor must fence/quiesce writers and check
all live and historical references before deleting an unreferenced object;
referenced objects must remain intact. A missing object is safe to reconcile.
Do not TTL unresolved intents or infer unreferenced status from age alone.
This change records candidates only and does not run or provision a janitor.

Each put adds one Firestore intent read and, for a new candidate, one create.
When concurrent first puts race on the same candidate, the loser's create
returns AlreadyExists and it reads the candidate once more (two reads total).
It adds no GCS or KMS calls. The production write gate remains closed pending
C4; no runtime flags, bucket permissions or deployment values change.
