# Durable discovery of unreferenced lake uploads

Every lake put first persists a durable discovery intent in the customer
Firestore plane at `lake_upload_candidates/{sha256(bucket + '/' + object_key)}`.
The row contains `bucket`, `key`, server UTC `created_at` / `admitted_at`,
`settled`, and an `in_flight` map from unique attempt ids to server admission
timestamps; it has no TTL. Failure to record admission refuses the upload.
Each writer transactionally removes only its own attempt after its put returns
or raises; worker loss or settlement failure leaves that attempt durable.
Concurrent writers of the same content-addressed key cannot settle each other. The object key contains user-derived
owner/conversation identifiers and a plaintext digest, so account wipe must erase
these rows. Existing intents and concurrent
creates are idempotent and retain the original creation time.

An intent precedes the GCS write, so refused transaction replays, superseded
sources, bounded retry exhaustion, deferred-swap CAS failures, ambiguous upload
responses and worker loss leave durable sweep discovery. Successful pointers
retain their intents too: an intent is a candidate, never proof of an orphan.
A fenced writer removes only a blob generation it just created; it retains the
shared intent because another pre-fence writer may still be uploading that name.
Reused referenced objects remain for the deleting orchestrator. Account wipe
retains intents after its first drained object-prefix purge. Immediately before
key destruction it checks every owner intent, including old bucket bindings.
It refuses completion until each attempt is settled or older than 630 seconds:
the maximum allowed put-success budget (30 seconds) plus a fixed ten-minute
safety margin. The maximum keeps configuration changes from shortening an
already admitted request's bound. Legacy rows without attempt state are treated
as unsettled since their creation timestamp. Missing/invalid state or discovery
read failure also blocks the step. Only after quiescence does it purge and verify
prefix absence again, erase and verify intents, then destroy keys. A recent
unsettled upload, final purge or intent erasure failure retains keys and blocks
completion for retry; no sleeps are used to wait out this final gate.

Every put has a monotonic success deadline derived as half the strictly positive
wipe drain interval. Upload and create-only replay requests disable SDK retries
and split the remaining budget between connect/read timeouts. Expired puts never
return a pointer and retain their blob and intent, since another writer may have
referenced the same name. Only a deletion fence permits self-cleanup of a newly
created generation. SDK socket timeouts do not guarantee total remote request
time, so these client budgets alone
do not prove quiescence of an ambiguous in-flight remote upload. The durable
final gate supplies the quiescence protocol instead. Encrypted payloads above
8 MiB are refused before admission: the pinned SDK switches larger payloads to
resumable requests, outside this single-request protocol.

C3 owns janitor candidate consumption as defense in depth. Its janitor must fence/quiesce writers and check
all live and historical references before deleting an unreferenced object;
referenced objects must remain intact. A missing object is safe to reconcile.
Do not TTL unresolved intents or infer unreferenced status from age alone.
This change records candidates only and does not run or provision a janitor.

Candidate admission transactionally reads the owner deletion marker, conversation
tombstone and intent before creating a missing intent. Firestore retries conflicts
against concurrent fence writes (each retry repeats those reads); the transaction
cannot recreate an intent after account wipe. It adds no GCS or KMS calls. The production write gate remains closed pending
C4; no runtime flags, bucket permissions or deployment values change.
