# Object lake provisioning (not applied)

C1 checks in primitives and policy only. No bucket or key is provisioned here.
Keep `OBJECT_LAKE_RELEASE=v1` until the lifecycle contract and retention hold migrate together.
`OBJECT_LAKE_WRITE_ENABLED=false` and percent 0 remain mandatory in production
until C4's explicit account-wipe coverage test is green (plan v2 O1). Production
bucket/KMS bindings remain empty. Dev literals are reserved names, not proof that
resources exist. Use a separately authorized operator change for every step below.

1. Allocate a never-used bucket name. A describe must return **404**, never treat
   403 as absence. Create in **us-central1**, **STANDARD**, with uniform bucket-level
   access and public access prevention enforced. Disable versioning and set
   **soft-delete retention to 0 at creation, before any writer IAM**. Do not enable
   Autoclass, retention locks, or object holds. Default GCS soft delete is unsafe
   for immediate erasure. Verify empty, including versions and soft-deleted objects.
2. Extract exactly the `lifecycle` field of `lake-forward.json`, apply it only to
   this new bucket, re-describe and compare verbatim. No Delete rule is allowed;
   transcripts stay Standard/Nearline forever except explicit deletion. The 90-day
   transition leaves a 30-day Nearline minimum-storage billing tail after tiering;
   privacy deletion may incur accepted early-deletion charges. Class is mid-path
   (`v1/spaces/<sid>/transcript/<entity>/<digest>`), so prefix lifecycle cannot select
   a class. Future divergent classes require C3 per-object registry/janitor policy,
   never a whole-bucket Coldline/Archive rule.
3. Create a KMS key ring and symmetric **software** key in **us-central1**, purpose
   `ENCRYPT_DECRYPT`, algorithm `GOOGLE_SYMMETRIC_ENCRYPTION`. Grant
   `roles/cloudkms.cryptoKeyEncrypterDecrypter` on this key and object admin on this
   bucket only to the backend/backend-sync/listen runtime identities that need it.
   Pusher has no lake callers in C1; a future caller PR must first include its KMS
   and cachetools runtime dependencies and qualify its identity. No credentials or
   service-account keys are created by C1.
4. Enable bucket Data Access audit logs (including reads) with a BigQuery sink;
   verify a dev read arrives in the sink. This supplies the read-logging half of
   the R13 audit requirement (HIPAA 45 CFR 164.312(b)). Never put user content or
   raw/wrapped DEKs in logs. Run the source validator and runtime-env composer,
   then fill the production overlay literals in the provisioning change, keeping
   write admission off until C4 is verified. The existing lifecycle workflow needs
   a new bucket variant, a `.github` change David must name separately. Until that
   variant exists, this contract is source-checked only; do not dispatch the legacy
   workflow against an existing bucket or claim live validation.

Once a **dev** bucket and key exist, a separately authorized smoke must exercise
put/get byte equality, create-only retry, old-version reads after rotation, prefix
verified absence, and key destroy causing `SpaceKeyDestroyed`. Record commands,
resource identities and results in that provisioning PR. C1 runs only hermetic
FakeKMS/local-storage tests, with no cloud credentials or production calls.

C2 owns codec integration, inline threshold/read kill switch and the lake's
pre-upload/post-upload deletion-marker and key-authority checks. C3 owns offload,
backfill, current-consent export filtering, registry and orphan janitor.

C4 ships required, retry-safe account wipe steps in this order: cell/directory
purge, **lake_prefix_purge**, Firestore user subtree, Typesense, memory registry,
then **lake_key_destroy LAST**, before the completed marker. The prefix step
requires a running wipe and rechecks the blocking deletion fence, then deletes
and verifies absence. Each pending upload has a resumable session; the final key
step cancels and verifies terminal session status, purges the current prefix,
then fences sessions again and deletes/verifies each recorded bucket before
transactional candidate erasure. Keys survive any failure. Socket deadlines
are pointer-success budgets; storage session status supplies deletion authority.
Legacy timestamp-only attempts fail closed without age-based erasure.

An unset `BUCKET_OBJECT_LAKE` skips prefix purge with zero marker/storage IO.
A configured bucket is purged even after writer rollback (false/percent 0).
Key destruction runs unconditionally, including with no bucket: the top-level
`space_keys/{sid}` collection is outside the generic user-subtree wipe. It retains
a permanent content-free `{space_id, state: destroyed, destroyed_at}` tombstone,
evicts local raw keys, and fresh authority reads fence cached unwraps on other
workers. Retained pointers report `TranscriptShredded` after key destruction.

Explicit conversation deletion synchronously purges every lake class for that
conversation and its deduplicated `sync_merged_from` donors before document
deletion, with verified absence. Storage unavailability returns retryable 503,
retaining the durable conversation tombstone and primary documents; success
remains 204. Before any listing, each conversation and donor gets a durable
`users/{uid}/deleted_conversations/{conversation_id}` fence, preserving any
existing intent metadata. Writers read this authority fresh before and after
upload, alongside the account marker and space key. A newly created late
candidate removes only its own generation and refuses to return a pointer;
a create-only retry never removes an existing referenced object. Verified-absence
failure is a retryable `LakePurgeIncomplete` (a `LakeFetchError`) with HTTP 503.
After verified prefix absence, deletion cancels pending resumable sessions in
each conversation's exact key range, queries terminal status, then deletes and
verifies every recorded bucket binding before compare-and-delete. This is
synchronous and has no delayed task, route or drain setting. Final same-key
settlement may also erase a fenced candidate after verified object deletion.

The developer delete endpoint calls the same orchestrator and therefore also
purges lake content, adding a raw Firestore snapshot and a synchronous GCS purge
even with current bucket configuration unset. Its existing error handling
returns HTTP 500 on lake outage, with durable intent and primary documents retained. Merge targets
encode their own objects; merge-internal donor cleanup and abandoned candidates
still rely on C3's orphan janitor.

The O1 activation precondition is the green wipe-coverage test
`backend/tests/unit/test_lake_wipe_step.py::test_o1_wipe_coverage_gate_and_crash_retry`,
plus separately authorized dev round-trip/shred qualification and provisioning.
No flag is activated by C4. Purge covers only the configured release: the `v1`
pin is load-bearing. A future release bump must widen purge to a release list.

Wrapped-DEK Firestore backups/PITR can restore readability for about seven days
while the regional KMS key remains usable. This is R13's accepted deletion tail;
per-space KMS keys were rejected on cost. Retired DEKs are retained until no object
references their version. Never prune version history during rotation.

Rollback: set write enabled false and percent 0; keep read resolution, bucket
bindings, version history and explicit deletion available for existing pointers.


Upload intent erasure uses terminal storage-session status, not elapsed time.
Candidates remain user-derived data with no TTL. The final key step cancels every
pending session and queries status, then verifies prefix absence and repeats
session fencing plus recorded-bucket deletion immediately before transactional
compare-and-delete. Legacy timestamp-only attempts cannot be cancelled and block
erasure, regardless of age. Lake writes have never been admitted outside
local/offline/dev, so production has no legacy rows.

Candidate admission reads owner and conversation fences in the same Firestore
transaction that records a session. A delayed writer cannot recreate discovery
after the purge scan; failed admission cancels the empty session best-effort.
The five-second put-success budget does not authorize erasure. Storage status
must prove finalization, cancellation or expiry; nonterminal status and transport
errors keep discovery and keys for retry. There are no delayed tasks or new
infrastructure bindings.
See [candidate protocol](../../docs/listen_pusher_pipeline/changes/2026-11-08-lake-upload-candidates.md).
