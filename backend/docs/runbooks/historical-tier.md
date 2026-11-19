# Historical processing tier (T1+)

These are David's 2026-11-18 decisions 12-15 (omi-workspace
`data/run-2026-11-18-support-packet/decisions.md`). Sync backfill and batch
audio more than 72 hours old is stored with a transcript, speakers and a
deterministic title. Its summary is generated only when the owner opens it,
and that run is summary-only. The contract is in
[the pipeline doc](../listen_pusher_pipeline.mdx#historical-processing-tier-t1).

## Switches (ops kill, on unless set off)

| Switch | Off means | Rows already stamped |
|---|---|---|
| `SYNC_HISTORICAL_TIER_ENABLED` | New old-capture rows get full processing again. They then park behind the 72 h enrichment gate and show "Writing notes", which is the pre-T1+ behaviour. | Unchanged |
| `HISTORICAL_SUMMARY_ON_OPEN_ENABLED` | `POST .../summary/open` answers 503 `historical_summary_disabled`, and `summary_on_open` is no longer advertised. | Unchanged; an existing summary still returns 200, and `/reprocess` stays summary-only |
| `HISTORICAL_SUMMARY_VECTOR_ENABLED` | Open-time summaries are not indexed for search. | Unchanged |

The tier boundary is the enrichment age gate itself. `config.historical_tier.min_age_seconds()`
parses `ENRICHMENT_MAX_AGE_HOURS` exactly as `utils/enrichment/age_gate.py` does, so
the two cannot drift, and a gate of 0 means no tier. There is no separate age
setting. Sync stamps a row when it will be past the gate by its latest possible
wake (create time plus `processing_hold.MAX_HOLD_SECONDS` plus one hour), so no
row is enrolled for full processing only to be parked.
`HISTORICAL_SUMMARY_GLOBAL_DAILY_LIMIT` (default 10000, 0 off) caps fleet-wide
generations per rolling day. It fails open when Redis is down.

Rollback is the switches. Each is a runtime env change, with no code change.

## Watch

- `omi_historical_tier_rows_total{producer=sync|batch,outcome=stamped|settled|fenced|not_historical}`:
  `fenced` means a newer append won the hold revision, and that append settles
  the row again.
- `omi_historical_summary_open_total{outcome}` and `omi_historical_summary_latency_seconds`.
  The open rate is generated opens over stamped rows. `existing` is an idempotent
  re-open with no model call. Sustained `empty` or `transient` outcomes are a
  notes-pipeline problem, not a tier problem.
- Log lines `event=historical_summary_open outcome=...` and `event=historical_tier_settle`.

## Rows stuck before T1+ shipped

Rows created before PR 2 carry the provisional title and an armed
`summary_due_at`, but the 72 h age gate parked their enrichment. Home shows them
as "Writing notes" forever. `backend/scripts/historical_tier_operator.py convert`
turns them into historical rows for one owner at a time. It only touches
completed rows on the backfill or batch lane that are past the age gate, have
no summary and no manual edits, and are not owned by a finalization job.

```bash
cd backend
python scripts/historical_tier_operator.py convert --uid <uid>                       # dry run: counts only
python scripts/historical_tier_operator.py convert --uid <uid> --apply \
    --approval-ref <where David's go is recorded> \
    --confirm-production-project based-hardware --receipt-dir <private dir>           # needs David's go
```

The script pages the owner's rows by document ID (`--scan`, default 2000, max
5000 rows read) and stops after `--limit` eligible rows (default 200, max 500),
so rows it keeps never stall a run. It reads classifier fields and presence
checks only, never transcript or summary text. It fences each write on the
row's update time and prints counts, never IDs.

A convert stamps the tier, the no-derived-effects marker,
`summary_blocked_reason='historical_on_open'` and the `historical_minimum`
title provenance, and removes the provisional-title marker and the due time.
It also closes an open sync hold, and retires the row's parked, unleased
enrichment wake the way a completed wake ends.

`--apply` refuses to run without `--approval-ref`. Each apply writes a dated
JSON receipt to `--receipt-dir`: mode, owner hash, approval reference, time,
counts and the written row IDs. The receipt holds row IDs, so keep it with the
private run record, never in Git. Each production apply needs David's explicit
approval for the named owners.

## Clearing the marker

`historical_tier_operator.py clear-marker --uid <uid>` (dry run first; apply has
the same approval reference, confirmation and receipt) removes
`processing_tier`, the no-derived-effects marker and `summary_blocked_reason`
from an owner's historical rows that have no summary yet. With
`--from-receipt <convert receipt>` it clears exactly the rows that convert
wrote, which is how to undo one run. It is not an exact inverse: the title
stays final, the cleared hold and retired wake are not restored, and the row
owes no automatic summary. The owner's Reprocess then runs the full pipeline,
with derived effects. Rows that already have an open-time summary are left alone.
