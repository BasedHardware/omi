# Durable discovery of unreferenced lake uploads

Every lake put first persists a durable discovery intent in the customer
Firestore plane at `lake_upload_candidates/{sha256(bucket + '/' + object_key)}`.
The row contains `bucket`, `key`, server UTC `created_at` / `admitted_at`,
`settled`, and an `in_flight` map from unique attempt ids to server admission
timestamps; it has no TTL. Failure to record admission refuses the upload.
Each writer transactionally removes only its own attempt after its put returns
successfully; worker loss or settlement failure leaves that attempt durable.
Concurrent writers of the same content-addressed key cannot settle each other. The object key contains user-derived
owner/conversation identifiers and a plaintext digest, so account wipe must erase
these rows. Existing intents and concurrent
creates are idempotent and retain the original creation time.

An intent precedes the GCS write, so refused transaction replays, superseded
sources, bounded retry exhaustion, deferred-swap CAS failures, ambiguous upload
responses and worker loss leave durable sweep discovery. Successful pointers
retain their intents too: an intent is a candidate, never proof of an orphan.
A fenced writer removes only a blob generation it just created; it retains the
shared intent while another pre-fence writer is still uploading that name. Under
a conversation tombstone, final same-key settlement deletes the row
transactionally after late-generation cleanup. Explicit conversation deletion
also removes settled rows in the exact conversation key range after verified
prefix purge. Every candidate's object is deleted in its recorded bucket and
verified absent before its row can be erased, including former buckets and when
current bucket configuration is unset. Storage failures retain discovery and
make deletion retry. Unsettled rows remain regardless of age during the initial
conversation delete. Their fenced writers can settle and erase them after
recorded-bucket cleanup; otherwise deletion schedules a durable re-purge using
the existing sync Cloud Tasks queue, identity and handler service, 24 hours after
the newest admission (rounded strictly past the bound). The hidden OIDC route
`/internal/lake/conversation-repurge` repeats recorded-bucket deletion and absence
verification before erasing expired rows. Early task deliveries return 503;
duplicate deliveries after erasure return 204. Queue/configuration failures
return retryable deletion failure while retaining rows. No queue is provisioned.

The 24-hour bound is the explicit assumption that no storage request can commit
a day after admission; SDK socket timeouts do not prove that assumption. A newer
admission controls the bound even if that attempt settles before an older lost
attempt. Account wipe retains its quiescence gate, now using this fixed day,
then purges the current prefix again, re-deletes and verifies every candidate's
recorded bucket immediately before erasure, verifies candidate absence, and
destroys keys last. Malformed state, recent unsettled attempts and cleanup
failures keep keys for retry. Legacy candidates use their creation timestamp.

Every put has a monotonic success deadline: half a positive wipe drain interval,
or a fixed five-second put budget when drain is zero. Drain accepts 0..60 seconds;
zero skips sleep while preserving prefix verification and the fixed 24-hour
request assumption. Upload and create-only replay requests disable SDK retries
and split the remaining budget between connect/read timeouts. Expired puts never
return a pointer and retain their blob and intent, since another writer may have
referenced the same name. Only a deletion fence permits self-cleanup of a newly
created generation. SDK socket timeouts do not guarantee total remote request
time, so these client budgets alone
do not prove quiescence of an ambiguous in-flight remote upload. The day-long assumption and required re-purge govern abandoned requests instead. Encrypted payloads above
8 MiB are refused before admission: the pinned SDK switches larger payloads to
resumable requests, outside this single-request protocol.

C3 owns janitor candidate consumption as defense in depth. Its janitor must fence/quiesce writers and check
all live and historical references before deleting an unreferenced object;
referenced objects must remain intact. A missing object is safe to reconcile.
Do not TTL unresolved intents or infer unreferenced status from age alone.
This change records and erases candidates at explicit deletion boundaries; it schedules deletion-specific re-purges, without running or provisioning a general janitor.

Candidate admission transactionally reads the owner deletion marker, conversation
tombstone and intent before creating a missing intent. Firestore retries conflicts
against concurrent fence writes (each retry repeats those reads); the transaction
cannot recreate an intent after account wipe. It adds no GCS or KMS calls. The production write gate remains closed pending
C4; no runtime flags, bucket permissions or deployment values change.
