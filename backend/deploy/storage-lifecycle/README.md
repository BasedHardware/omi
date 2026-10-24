# `private-cloud-sync` bucket lifecycle

Checked-in lifecycle configuration for `omi-private-cloud-sync` (prod) and
`omi-dev-private-cloud-sync` (dev). Applied only by
`.github/workflows/gcp_storage_lifecycle.yml` — never by hand.

`gcloud storage buckets update --lifecycle-file` **replaces the whole lifecycle
config**, so every legacy rule must be re-declared verbatim in these files.
`backend/scripts/validate_storage_lifecycle.py` refuses any file that drops a
rule present in the live bucket, lets a `Delete` rule reach `chunks/`, adds a
`SetStorageClass` rule not scoped to exactly `chunks/`, or adds a
noncurrent-version (`isLive: false`) rule.

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

Plan and evidence: `omi-knowledge-base/projects/gcp-cost-efficiency/evidence/2026-09-02-coldline-rollout-plan.md`.
