# Backfill dispatch and worker capacity

Train 1 configuration, 2026-10-15. Source settings are a proposed release, not a claim of applied production state.

The owner is `.github/actions/sync-backfill-lifecycle/action.yml`: worker revision `--max-instances=40`, service `--max=40`, concurrency **6**, 2 vCPU, **8 GiB**, min 3; both queue create/update branches use **90 concurrent dispatches / 15 dispatches per second**, retry backoff5–60s. Nominal peak240 worker slots leaves substantial headroom at the first90-slot step. Require the reviewed worker revision and service cap ready before increasing dispatch. Mixed revisions must stay below the lower usable capacity.

The previous60/10 queue and 18-instance limits are the rollback baseline. Keep per-UID sequencing, GPU admission and final-pass budgets unchanged. `SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM` is false when absent, false in dev and true in the prod sync/worker config. It retires only Redis-absent work while holding its job lock, rechecking the unbound exact content claim and owner in a Firestore transaction. It never deletes audio or marks success. Each normal claim retires at most 50 heads; the bounded sweep uses one pending retirement per UID per pass (plus its dispatching-owner retirement), avoiding a100×50 scheduler amplification. A dispatching owner may retire before its dispatch retry deadline; a running/bound owner cannot. Observe `sync_backfill_expired_retired_total{source=~"pending|dispatching"}` and `event=sync_backfill_expired_retired` separately from transcription completions.

Hold 90/ 15 at least 15 min. Later operator steps135/20,180/25 and200/25 are conditional and require a follow-up config train; this action intentionally persists only90/ 15. Require no GPU OOM/fatal, live STT p95<3s and <10% regression, no sustained Cloud Run429/5xx or memory pressure, no Firestore resource exhaustion/persistence contention, and no Redis eviction/rejected connections. Redis CPU/memory/command latency must be observable before advancing. Stop on ownership overlap or nonterminal ACK. Track durable completed content, queue age, expired retirement and client re-upload separately; registry shrink is not recovered transcription.

Rollback queue first:

```bash
gcloud tasks queues update sync-backfill --project=based-hardware --location=us-central1 --max-concurrent-dispatches=60 --max-dispatches-per-second=10 --min-backoff=5s --max-backoff=60s
```

Keep the larger fleet until in-flight requests drain, then restore revision max18 and service max18 through the normal release/config path, retaining concurrency 6 / 8 GiB. Set `SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM=false` on both production sync services through the manifest/release path to restore the original claim/dispatch behavior. Turning it off cannot undo retired rows; retained client WALs re-upload through existing 404 recovery. Do not resurrect Redis jobs from registry payloads or treat missing Redis as proof that local audio is lost.

No concurrency>6, memory reduction, GPU admission change, final-pass budget increase or minimum-instance reduction is part of Train 1. Historic packing/cost proposals are preserved in Git history and the dated measurements in `sync-cloudrun-rightsizing.md`.
