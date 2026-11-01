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

Prod Archive transition (2026-11-01, margincarry): prod.json also declares a
second `SetStorageClass` rule moving the **already-Coldline** batch stock to
ARCHIVE — `matchesStorageClass: ["COLDLINE"]`, same `chunks/` prefix and
`.batch.enc/.batch.bin` suffix scope as the Coldline rule, `age: 60` (created
≥60 days ago = ≥30 days past the Coldline transition, so nothing leaves
Coldline before the p76 cadence; the existing stock qualifies on first
evaluation). David approved the move 11-01 with the dispatch gate below
extended: do not dispatch prod `apply` carrying this rule until playback
on-demand (#24215) is live — Archive retrieval bills $0.05/GB vs Coldline
$0.02/GB, and on-demand playback is the reader that would pay it. Value:
~160 TB Coldline stock at ~$34/day falls to ~$11/day at Archive
($0.007 → $0.0022/GB-mo, ≈ −$22/day steady). Rollback (the existing
`lifecycle_variant=rollback`) drops this rule with the Coldline one; objects
already moved stay Archive (reverting class needs a rewrite job).

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
**Dispatch gate:** the live bucket's `merged/` Delete rule is currently removed
under the 10-24 audio-loss incident freeze; applying prod.json re-declares it,
so the lead must not dispatch `apply` for prod until the freeze is lifted (or
must explicitly accept re-declaring `merged/`).

Plan and evidence: `omi-knowledge-base/projects/gcp-cost-efficiency/evidence/2026-09-02-coldline-rollout-plan.md`.
