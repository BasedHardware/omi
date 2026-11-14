# unlimited_v2 backfill/import daily transcribed-hours cap (SCA-2152)

Default-off admission cap for the `unlimited_v2` plan: no more than
`UNLIMITED_V2_BACKFILL_HOURS_CAP_HOURS` (default `24`) of managed
**backfill/import** transcription per UTC user-day. The flag ships `false`;
activation is a separate owner decision and is not part of the shipping change.

## Settings

| setting | default | meaning |
| --- | --- | --- |
| `UNLIMITED_V2_BACKFILL_HOURS_CAP_ENABLED` | `false` | The kill switch. Trimmed case-insensitive `1/true/yes/on` enables; anything else (including unset) disables, and the code performs no plan or meter reads. |
| `UNLIMITED_V2_BACKFILL_HOURS_CAP_HOURS` | `24` | The cap level in hours. Blank, unparseable or non-positive values keep the default; the boolean is the only on/off authority. |

Both are declared on every serving surface that admits transcription: the GKE
`backend-listen` deployment, Cloud Run `backend`, `backend-sync`,
`backend-sync-backfill`, `backend-integration`, and the GKE batch-pipeline worker
chart. Runtime env is the sole rollout authority (no client flag).

## Meter and scope

The cap reads `users/{uid}/hourly_usage` documents for the current UTC day and
sums `transcription_seconds` — the authoritative per-user-day basis the finops
`unit_cost_user_day.tx_sec` projection aggregates (`stt_usage_daily.csv`). It
does not estimate: there is no projection, sampling or client claim.

The meter is the **total** day seconds and cannot separate backfill seconds from
live seconds. The separation is the admission lane, which is exact for the work
being admitted:

- **In scope:** the sync `backfill` lane and the batch `backfill` lane (historical
  uploads, imports and held-audio recovery of backfill work).
- **Never in scope:** live listen (`/v4/listen`), fresh sync capture, and fresh
  batch capture. Those admissions never pass the backfill marker, so live capture
  is untouched even on a user-day already above the cap.

Only the current `unlimited_v2` plan is in scope. Free, Plus and the deprecated
paid tiers (`unlimited`, `architect`, `operator`) resolve exactly as before in
both modes; those plans already have a finite allowance that bounds a backfill
day. A plan or meter read that fails admits transcription and logs a warning; a
missing meter is never evidence the cap was reached.

## Behavior above the cap

The refusal reuses the existing exhausted-allowance contract:

- **Sync** (`funded_allowance`): denied segments take the existing durable hold
  path; nothing is deleted and no billing path changes.
- **Batch** (`funded_allowance`): the CPU admission holds the unit for the
  existing allowance hold window; the GPU dispatch re-check keeps its own
  contract for units already admitted.
- **Live listen**: unchanged. The cap is never evaluated on the live plane.

The cap is independent of the legacy/offline dispatch scope: with the flag on, a
backfill admission still resolves the allowance and is refused even on a host
where `STT_CAP_OFFLINE_ENFORCEMENT` is off.

Refusals increment `omi_unlimited_v2_backfill_day_cap_blocks_total{plane}` with a
bounded plane label (`sync`, `batch`) and are logged once per admission. Offline
decisions also surface as
`omi_stt_cap_dispatch_decisions_total{reason="allowance_exhausted"}`.

Per-process, the day sum is cached for at most 30 seconds per user, so a capped
account can overshoot its cap by at most the traffic in that window. The cache
holds one day per user and is pruned by day and bounded to 4096 entries.

## Readback (post-merge, post-roll)

Read the runtime value on each plane, the same way prior lever PRs read back
their settings:

```bash
# Canonical manifest-vs-live check (Cloud Run services)
python3 backend/scripts/validate-backend-runtime-env.py --env prod --check-live-cloud-run

# Cloud Run
gcloud run services describe backend --region=us-central1 --project=based-hardware \
  --format='value(spec.template.spec.containers[0].env)' | tr ',' '\n' | grep UNLIMITED_V2_BACKFILL
gcloud run services describe backend-integration --region=us-central1 --project=based-hardware \
  --format='value(spec.template.spec.containers[0].env)' | tr ',' '\n' | grep UNLIMITED_V2_BACKFILL
gcloud run services describe backend-sync --region=us-central1 --project=based-hardware \
  --format='value(spec.template.spec.containers[0].env)' | tr ',' '\n' | grep UNLIMITED_V2_BACKFILL
gcloud run services describe backend-sync-backfill --region=us-central1 --project=based-hardware \
  --format='value(spec.template.spec.containers[0].env)' | tr ',' '\n' | grep UNLIMITED_V2_BACKFILL

# GKE listen and batch worker
kubectl -n prod-omi-backend get deploy -l app.kubernetes.io/name=backend-listen \
  -o jsonpath='{range .items[*].spec.template.spec.containers[*].env[*]}{.name}={.value}{"\n"}{end}' \
  | grep UNLIMITED_V2_BACKFILL
kubectl -n prod-omi-backend get deploy -l app.kubernetes.io/name=batch-pipeline-worker \
  -o jsonpath='{range .items[*].spec.template.spec.containers[*].env[*]}{.name}={.value}{"\n"}{end}' \
  | grep UNLIMITED_V2_BACKFILL
```

Expected on every plane: `UNLIMITED_V2_BACKFILL_HOURS_CAP_ENABLED=false` and
`UNLIMITED_V2_BACKFILL_HOURS_CAP_HOURS=24`.

## Activation and rollback

Activation is out of scope for SCA-2152 and needs the goal owner's approval
(David approved the backfill cap 2026-11-14T04:10Z; activation is a separate
release-owner step after this issue's verify passes). When approved, set
`UNLIMITED_V2_BACKFILL_HOURS_CAP_ENABLED=true` on the planes that serve
transcription. Rollback is setting it back to `false`: no data migration, no held
audio discarded, no billing state to unwind.

## Limits

- A user-day is the UTC day the seconds are recorded (processing day), matching
  `unit_cost_user_day`; a backfill of older capture still counts against the day
  it is transcribed.
- The cap bounds transcription, not capture: audio receipt, archiving and
  offline upload acceptance are unchanged.
- Held audio above the cap competes for the following day's budget; it is never
  transcribed outside the cap.
- Batch GPU dispatch re-checks and batch held-audio recovery do not re-evaluate
  the cap; they only re-dispatch units already admitted under it. The CPU
  admission is the authoritative cap point for batch.
