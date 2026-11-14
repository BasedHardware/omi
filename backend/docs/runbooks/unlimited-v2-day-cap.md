# unlimited_v2 daily transcribed-hours cap (SCA-2096)

Default-off admission cap for the `unlimited_v2` plan: no more than
`UNLIMITED_V2_TX_HOURS_CAP_HOURS` (default `8`) of managed transcription per UTC
user-day. The flag ships `false`; activation is a separate owner decision and is
not part of the shipping change.

## Settings

| setting | default | meaning |
| --- | --- | --- |
| `UNLIMITED_V2_TX_HOURS_CAP_ENABLED` | `false` | The kill switch. Trimmed case-insensitive `1/true/yes/on` enables; anything else (including unset) disables, and the code performs no plan or meter reads. |
| `UNLIMITED_V2_TX_HOURS_CAP_HOURS` | `8` | The cap level in hours. Blank, unparseable or non-positive values keep the default; the boolean is the only on/off authority. |

Both are declared on every serving surface that admits transcription: the GKE
`backend-listen` deployment, Cloud Run `backend`, `backend-sync`,
`backend-sync-backfill`, `backend-integration`, and the GKE batch-pipeline worker
chart. Runtime env is the sole rollout authority (no client flag).

## Meter and scope

The cap reads `users/{uid}/hourly_usage` documents for the current UTC day and
sums `transcription_seconds` — the authoritative per-user-day basis the finops
`unit_cost_user_day.tx_sec` projection aggregates (`stt_usage_daily.csv`). It
does not estimate: there is no projection, sampling or client claim.

Only the current `unlimited_v2` plan is in scope. Free, Plus and the deprecated
paid tiers (`unlimited`, `architect`, `operator`) resolve exactly as before in
both modes. A plan or meter read that fails admits transcription and logs a
warning; a missing meter is never evidence the cap was reached.

## Behavior above the cap

The refusal reuses the existing exhausted-allowance contract per surface:

- **Live listen** (`/v4/listen`): a capped session stays connected and keeps
  receiving/archiving audio, but opens no paid provider and holds audio in the
  existing live cap custody sink. A refresh after the next UTC day resumes
  provider work if the day budget allows it.
- **Sync / batch** (`funded_allowance`): denied segments take the existing
  durable hold path; nothing is deleted and no billing path changes.
- **`POST /v1/stt/transcribe`**: the route's existing `402 Transcription
  allowance exhausted` response.

Refusals increment `omi_unlimited_v2_tx_day_cap_blocks_total{plane}` with a
bounded plane label (`live`, `sync`, `batch`, `http`) and are logged once per
admission. Offline decisions also surface as
`omi_stt_cap_dispatch_decisions_total{reason="allowance_exhausted"}`.

Per-process, the day sum is cached for at most 30 seconds per user, so a capped
account can overshoot its cap by at most the traffic in that window. The cache
holds one day per user and is pruned by day and bounded to 4096 entries.

## Readback (post-merge, post-roll)

Read the runtime value on each plane, the same way SCA-1993 read back
`FIRESTORE_READ_LEVERS`:

```bash
# Cloud Run
gcloud run services describe backend --region=us-central1 --project=based-hardware \
  --format='value(spec.template.spec.containers[0].env)' | tr ',' '\n' | grep UNLIMITED_V2_TX_HOURS
gcloud run services describe backend-integration --region=us-central1 --project=based-hardware \
  --format='value(spec.template.spec.containers[0].env)' | tr ',' '\n' | grep UNLIMITED_V2_TX_HOURS

# GKE worker
kubectl -n prod-omi-backend get deploy -l app.kubernetes.io/name=batch-pipeline-worker \
  -o jsonpath='{range .items[*].spec.template.spec.containers[*].env[*]}{.name}={.value}{"\n"}{end}' \
  | grep UNLIMITED_V2_TX_HOURS
```

Expected on all three: `UNLIMITED_V2_TX_HOURS_CAP_ENABLED=false` and
`UNLIMITED_V2_TX_HOURS_CAP_HOURS=8`.

## Activation and rollback

Activation is out of scope for SCA-2096 and needs the goal owner's approval.
When approved, set `UNLIMITED_V2_TX_HOURS_CAP_ENABLED=true` on the planes that
serve transcription. Rollback is setting it back to `false`: no data migration,
no held audio discarded, no billing state to unwind.

## Limits

- A user-day is the UTC day the seconds are recorded (processing day), matching
  `unit_cost_user_day`; a backfill of older capture still counts against the day
  it is transcribed.
- The cap bounds transcription, not capture: audio receipt, archiving and
  offline upload acceptance are unchanged.
- Held audio above the cap competes for the following day's budget; it is never
  transcribed outside the cap.
