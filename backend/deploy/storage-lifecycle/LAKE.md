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

C2 owns codec integration, inline threshold/read kill switch and
`owner_storage_write_gate(space_id, bucket)` around puts/deletes. C3 owns offload,
backfill, current-consent export filtering, registry and janitor. C4 must explicitly
purge lake content with verified absence and destroy `space_keys/{sid}` **LAST**.
The top-level key collection is invisible to today's generic user-subtree wipe.
Before purge, C4 must durably fence deleted owners and quiesce in-flight puts to prevent object/key recreation.
Until C4 ships, no production key documents or lake objects may be created.

Destroy evicts local raw keys and every unwrap rechecks document existence before
using the bounded TTL KMS cache, so other workers observe document deletion too.
An already-running read/write still requires C4's account quiescence/write fence.
Wrapped-DEK Firestore backups/PITR can restore readability for about seven days
while the regional KMS key remains usable. This is R13's accepted deletion tail;
per-space KMS keys were rejected on cost. Retired DEKs are retained until no object
references their version. Never prune version history during rotation.

Rollback: set write enabled false and percent 0; keep read resolution, bucket
bindings, version history and explicit deletion available for existing pointers.
