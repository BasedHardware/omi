# `private-cloud-sync` bucket lifecycle

Checked-in lifecycle configuration for `omi-private-cloud-sync` (prod) and
`omi-dev-private-cloud-sync` (dev). Applied only by
`.github/workflows/gcp_storage_lifecycle.yml` — never by hand.

`gcloud storage buckets update --lifecycle-file` **replaces the whole lifecycle
config**, so every legacy rule must be re-declared verbatim in these files.
`backend/scripts/validate_storage_lifecycle.py` refuses any file that drops a
rule present in the live bucket, lets a `Delete` rule reach `chunks/`, adds a
`SetStorageClass` rule not scoped to exactly `chunks/`, or adds a
noncurrent-version (`isLive: false`) rule. The single sanctioned exception to
the last two is the scoped noncurrent `.opus.enc` Delete below.

Rollback: dispatch the workflow with `lifecycle_variant=rollback`. That stops
further transitions; objects already moved stay Coldline (reverting the class
needs a rewrite job). Rollback may drop only the rules the apply variant
declared — any other live rule blocks it until re-declared.

Prod Coldline scope (2026-10-24, p76): the `SetStorageClass` rule also
carries `matchesSuffix: [".batch.enc", ".batch.bin"]`, so only the large
batch artifacts under `chunks/` transition. Small `.opus.enc` chunk files
stay Standard — at their object count and read pattern, Coldline Class A
pricing on them never pays back (measured p76; the unscoped rule was headed
for a ~$1.9k/mo adder from ~11-14). `backend/tests/unit/test_storage_lifecycle_contract.py`
pins the suffix list. The dev bucket's rule carries no suffix.

Prod Archive transition dropped (2026-11-02): David withdrew the existing-stock
Coldline-to-Archive proposal in #24280 because of its large one-time operation
cost (about $38k for the 381.6M-object stock in the rollout carry report).
`prod.json` has no ARCHIVE rule, and the private-cloud lifecycle validator rejects
one in either environment. The forward policy in `canonical-forward.json`
still describes release-scoped packs in a **new empty regional bucket only**;
it does not authorize reclassifying existing prod stock (see `FORWARD.md`).

Prod noncurrent `.opus.enc` delete (2026-10-26, c3gcs): prod.json declares a
Delete rule for **noncurrent** `chunks/**.opus.enc` generations carrying
`numNewerVersions: 1`. It removes only strictly-superseded generations — a live
generation always has zero newer versions, and so does the newest generation of
a fully-deleted conversation — so the newest generation of every object name is
always retained and nothing that exists today is erased. David approved
noncurrent `.opus.enc` deletion "after a regen check" (10-23); the literal
"regenerable from raw" gate failed (1.5% — the raw is transient or merged away
by design; see `data/run-2026-10-12-subscription-overhaul` p76 REGEN-CHECK), so
this rule implements the provable-safety variant instead: 98.8% of noncurrent
generations have a live same-name object and the remainder are whole-conversation
orphans whose last generation the rule keeps. Value: removes the existing
14.49M-object / 502 GiB superseded stock (~$12/mo at-rest) and stops future
noncurrent `.opus.enc` from ever aging into Coldline transitions; the dominant
inflow (merge re-copies) is already stopped by skip-existing copies (#23507).
Applying this file is one-shot irreversible for the generations it deletes:
versioning does not protect noncurrent versions removed by a lifecycle rule.
**Dispatch gate:** the 2026-11-02 rollout handoff reports only the playback
30-day Delete and the batch-scoped Coldline transition live. `prod.json` still
declares the 3-day `merged/` Delete and the noncurrent `.opus.enc` Delete above;
**any prod apply would install both**, even with Archive removed. David has not
ruled on `merged/` after the 10-24 audio-loss incident freeze. The lead must not
dispatch prod `apply` until those additional delete rules are explicitly cleared.

Plan and evidence: `omi-knowledge-base/projects/gcp-cost-efficiency/evidence/2026-09-02-coldline-rollout-plan.md`.

`lake-forward.json` declares the new, unprovisioned object lake: encrypted space
content has no age-based deletion, versioning or soft-delete copies. Transcripts
stay Standard/Nearline. `validate_object_lake_bucket_contract.py` checks this
contract offline; [LAKE.md](LAKE.md) documents the separately authorized bucket,
KMS and audit-log provisioning. No existing bucket receives this policy.
