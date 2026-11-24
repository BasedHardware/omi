# `private-cloud-sync` bucket lifecycle

Checked-in lifecycle configuration for `omi-private-cloud-sync` (prod) and
`omi-dev-private-cloud-sync` (dev). Applied only by
`.github/workflows/gcp_storage_lifecycle.yml` — never by hand.

`gcloud storage buckets update --lifecycle-file` **replaces the whole lifecycle
config**, so the declarations include the full rule set. For prod, the
workflow compares the ordered rules against live, permits only the reviewed
Coldline size-floor change, and uses a metageneration-conditional Cloud
Storage JSON API patch. A concurrent bucket change blocks the patch.

The prod age-30 transition matches `STANDARD` and `MULTI_REGIONAL`
`chunks/` objects ending in `.batch.enc` or `.batch.bin` above 128 KiB.
The rollback variant restores the previous size eligibility and preserves the
live playback/merged cache rules. It can trigger catch-up transitions for
small objects that aged past 30 days. Release should estimate the backlog
and cost before dispatching rollback.

A Nov 24 read-only GCS describe at metageneration 34 confirmed that
`merged/` Delete at day 3, `playback/` Delete at day 30, and their shared
noncurrent Delete at day 7 were already live. The workflow blocks the update
if the live rule set differs beyond the size floor. The [SCA-4225 handoff](https://multica-01.tail76ea03.ts.net/scaling-forever/issues/01a20dfc-3d64-7d96-85fd-139b6949ef89)
records the exact before and after rules. The historical
noncurrent `.opus.enc` chunk deletion proposal is absent from the live bucket
and from both prod variants.

Prod Archive transition dropped (2026-11-02). David withdrew the existing-stock
Coldline-to-Archive proposal in #24280. The forward policy in
`canonical-forward.json` describes release-scoped packs in a new empty regional
bucket only. See [FORWARD.md](FORWARD.md).

Plan and evidence: `omi-knowledge-base/projects/gcp-cost-efficiency/evidence/2026-09-02-coldline-rollout-plan.md`.

`lake-forward.json` declares the new, unprovisioned object lake: encrypted space
content has no age-based deletion, versioning or soft-delete copies. Transcripts
stay Standard/Nearline. `validate_object_lake_bucket_contract.py` checks this
contract offline; [LAKE.md](LAKE.md) documents the separately authorized bucket,
KMS and audit-log provisioning. No existing bucket receives this policy.


## Batch staging lifecycle (separate, procedural)

The private-cloud-sync workflow above does not apply the batch staging bucket's
policy. Before and after any separately authorized batch lifecycle change, follow
the [mandatory batch lifecycle-change check](../../docs/runbooks/held-staging-inputs.md#mandatory-batch-lifecycle-change-check-procedural).
The existing `backend/scripts/check_sync_staging_lifecycle.py` enforces live Delete
age strictly greater than the runtime input terminal, in addition to all existing
hold/privacy floors. Review the proposed Delete against that same strict cutoff
before applying it and retain both checker receipts. Metadata denial or any failed
prerequisite blocks qualification. No automatic batch scheduler/apply integration
is claimed; out-of-band changes bypass this procedural detection.
