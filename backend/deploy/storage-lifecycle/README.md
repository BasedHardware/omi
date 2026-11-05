# `private-cloud-sync` bucket lifecycle

Checked-in lifecycle configuration for `omi-private-cloud-sync` (prod) and
`omi-dev-private-cloud-sync` (dev). Applied only by
`.github/workflows/gcp_storage_lifecycle.yml` — never by hand.

`gcloud storage buckets update --lifecycle-file` **replaces the whole lifecycle
config**, so every legacy rule must be re-declared verbatim in these files.
`backend/scripts/validate_storage_lifecycle.py` refuses any file that drops a
rule present in the live bucket, lets a `Delete` rule reach `chunks/`, adds a
`SetStorageClass` rule not scoped to exactly `chunks/`, or adds a
noncurrent-version (`isLive: false`) rule other than the approved seven-day
derived-cache Delete below. Raw-audio `chunks/` deletion has no exception.

Rollback: dispatch the workflow with `lifecycle_variant=rollback`. Prod restores
the pre-change live rules: playback Delete age 30 and the batch-scoped Coldline
transition below. It removes merged Delete age 3 and the derived-cache noncurrent
Delete. Dev rollback stops further transitions; objects already moved stay
Coldline (reverting the class needs a rewrite job). Rollback may drop only rules
the apply variant declared — any other live rule blocks it until re-declared.

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

Prod derived-cache cleanup (David, 2026-11-05 17:01/17:03Z; lead2/coordinator
ruling `af2845`): `prod.json` declares exactly four rules:

- `playback/`: Delete at age 30 days.
- `chunks/` `.batch.enc` / `.batch.bin`: COLDLINE at age 30 days, from
  STANDARD / MULTI_REGIONAL.
- `merged/`: Delete at age 3 days.
- `playback/` and `merged/`: Delete with `isLive: false` and
  `daysSinceNoncurrentTime: 7`.

Approval record in the Omi workspace:
`data/run-2026-10-13-two-lane-nemotron/swarm/state/refs/1105-noncurrent-7d-approval.md`.
Playback is a regenerable derived cache. Noncurrent versions deleted by lifecycle
cannot be recovered through versioning. Raw-audio noncurrent
`chunks/**.opus.enc` deletion remains **pending explicit clearance** per
`retention_contract.json`; it is absent from prod and rejected by the validator.

Plan and evidence: `omi-knowledge-base/projects/gcp-cost-efficiency/evidence/2026-09-02-coldline-rollout-plan.md`.
