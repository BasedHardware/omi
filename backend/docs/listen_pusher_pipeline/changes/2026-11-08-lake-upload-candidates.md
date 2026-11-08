# Durable discovery of unreferenced lake uploads

Every lake put first persists a create-only discovery intent in the customer
Firestore plane at `lake_upload_candidates/{sha256(bucket + '/' + object_key)}`.
The row contains only `bucket`, `key` and UTC `created_at`; it has no TTL. Failure
to read/create the intent refuses the upload. The object key contains user-derived
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
key destruction it purges and verifies prefix absence again, then erases intents,
then destroys keys. This catches an admitted late upload whose worker dies before
the post-put fence check; a final purge or intent erasure failure blocks completion
and retains keys for retry.

Every put has a monotonic success deadline derived as half the strictly positive
wipe drain interval. Upload and create-only replay requests disable SDK retries
and split the remaining budget between connect/read timeouts. Expired puts never
return a pointer and retain their blob and intent, since another writer may have
referenced the same name. Only a deletion fence permits self-cleanup of a newly
created generation. SDK socket timeouts do not guarantee total remote request
time, so these client budgets alone
do not prove quiescence of an ambiguous in-flight remote upload.

C3 owns candidate consumption. Its janitor must fence/quiesce writers and check
all live and historical references before deleting an unreferenced object;
referenced objects must remain intact. A missing object is safe to reconcile.
Do not TTL unresolved intents or infer unreferenced status from age alone.
This change records candidates only and does not run or provision a janitor.

Candidate admission transactionally reads the owner deletion marker, conversation
tombstone and intent before creating a missing intent. Firestore retries conflicts
against concurrent fence writes (each retry repeats those reads); the transaction
cannot recreate an intent after account wipe. It adds no GCS or KMS calls. The production write gate remains closed pending
C4; no runtime flags, bucket permissions or deployment values change.
