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
requires a running wipe and rechecks the blocking deletion fence, drains writers
for `OBJECT_LAKE_WIPE_DRAIN_SECONDS` (default 5, bounded 0..60; zero skips sleep), then deletes and
verifies absence. A put that passed its initial fence before deletion rechecks
authority after upload and self-deletes when fenced. Transport or verified-absence
failures fail the wipe for retry; keys survive any earlier step failure.

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
After verified prefix absence, deletion removes settled upload candidates and
candidates older than the 630-second quiescence bound in each conversation's
exact key range. Young unsettled candidates do not delay HTTP 204: their fenced
writers remove the row transactionally when their last same-key attempt settles,
after late-generation cleanup. Worker loss leaves discovery and possibly a late
blob for account wipe or C3 janitor erasure; this PR does not implement a janitor.

The developer delete endpoint calls the same orchestrator and therefore also
purges lake content, adding a raw Firestore snapshot and a synchronous GCS purge
when the bucket is configured. Its existing error handling returns HTTP 500 on
lake outage, with durable intent and primary documents retained. Merge targets
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


Upload intent erasure: `lake_upload_candidates` keys contain owner/conversation
identifiers and plaintext digests, so they are user-derived data. The required
final `lake_key_destroy` step checks every candidate for quiescence, then repeats
verified prefix purge, deletes and verifies absence of every candidate under the
owner's pinned release prefix (including abandoned intents and old bucket
bindings), and destroys keys last. Young unsettled attempts block this final step
until they settle or exceed the fixed 630-second quiescence bound. Its single-field
`key` range uses the automatic collection index. A newly created upload fenced
at its post-put check removes its own blob generation. The shared discovery
intent stays while other pre-fence uploads are active; the last fenced writer
can erase it under the conversation tombstone, and account wipe erases any
remaining intents at its final key step. Failed cleanup fails closed and retries.

Candidate admission reads the owner and conversation fences in the same
Firestore transaction that creates the candidate. A writer delayed until after
the purge scan therefore cannot recreate an intent even if it dies before put.
With the bucket unset, the prefix step still performs zero IO; the final key
step erases any old candidate rows before tombstoning the keys, without GCS IO.

Put-success budgets remain positive: a positive drain gives half its duration;
zero drain uses a fixed five-second put budget. The maximum budget remains 30
seconds, so changing drain configuration cannot shrink the 630-second quiescence
bound (maximum budget plus a fixed ten-minute safety margin).
