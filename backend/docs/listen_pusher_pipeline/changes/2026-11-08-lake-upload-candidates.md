# Durable discovery and storage fencing of lake uploads

Each lake put encrypts its payload and creates one GCS resumable upload session,
with create-only generation zero, the exact encrypted payload size and fixed
metadata set at initiation. Initiation sends no payload bytes. A candidate
transaction reads the owner and conversation deletion fences before persisting
`lake_upload_candidates/{sha256(bucket + '/' + object_key)}` in the customer
Firestore plane. The row records `bucket`, `key`, server UTC `created_at` and
`admitted_at`, `settled`, and `in_flight[attempt] = {admitted_at, session, size}`,
where `size` is the session's declared payload length (0 < size <= 8 MiB).
The session URI is a capability: it stays only in candidate state, never in
pointers, logs, metrics or raised error messages. A refused admission cancels
the empty session best-effort. No storage or KMS call runs inside a transaction.

After admission, one PUT sends the whole payload through the session, without
SDK retries or chunking. Encrypted payloads above 8 MiB are refused. Socket
connect/read budgets split the remaining five-second pointer-success deadline;
these budgets do not prove remote request quiescence. Creation/finalization
precondition failures retain create-only replay behavior. Fresh post-upload
owner/key checks and transactional settlement retain the existing deletion
fences. A successful settlement removes only its own attempt and session URI;
ambiguous results and worker loss retain durable discovery without a TTL.

Deletion uses a storage-enforced fence, with no age-based erasure. For every
pending session it sends DELETE, then the documented zero-byte PUT status query
with `Content-Range: bytes */<size>`. Terminal statuses are an allowlist measured
against GCS (dev bucket, 2026-11-09): 200/201 (finalized; also returned by a
cancel after finalization), 499 (cancelled; sticky for every later status, cancel
or upload), 412 (generation-0 finalize refused; sticky, and the session cannot
create the object even after it is deleted), and 404/410 (the service no longer
knows the session). Every other response fails closed: 308 (open), 400 (request
error; it proves nothing about the session), auth, throttling, 5xx and transport
errors. A writer whose finalize returns 412 runs the same fence on its own
session before settling it, so settlement never drops an unproven session. Retries cancel and query again. Only after all sessions are terminal
does deletion delete the object in the row's recorded bucket, verify absence,
and compare-and-delete the unchanged row transactionally. Former buckets and
an unset current bucket are covered. No later commit through a cancelled session
can recreate an object after discovery erasure.

Conversation deletion durably fences all donors before listings and synchronously
fences and erases their candidates before deleting conversation documents.
Failure retains discovery and returns retryable failure; public success stays
204. Account wipe retains candidates through intermediate steps. Its final step
fences pending sessions, verifies current prefix absence, repeats session fencing
and recorded-bucket deletion immediately before compare-and-delete, verifies
candidate absence, then destroys wrapped keys LAST. Any failure retains keys.
Legacy timestamp-only attempts (including rows predating `in_flight`) have no
storage capability to cancel and fail closed regardless of age. Writes have
never been admitted outside local/offline/dev; production admission stays closed.

There is no drain setting, delayed re-purge task or internal re-purge route.
C3 still owns general orphan/reference reconciliation. A candidate is never
proof that an object is unreferenced; ordinary janitor consumption must preserve
all live and historical references. Deletion remains pinned to release v1.

Protocol reference: [GCS resumable uploads](https://cloud.google.com/storage/docs/performing-resumable-uploads).
Local/offline uses disk-backed sessions with the same create/finalize/cancel/status
semantics, including locking cancellation against finalization. Race hooks live
in the local storage adapter, not in production lake branches.
