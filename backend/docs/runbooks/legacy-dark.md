# Legacy dark: retiring legacy sync without a deploy

Contract (h) of the legacy-retire swarm. Code: `utils/sync/legacy_dark.py`. Switch: `rollout_cohorts/_ramp.envs.<env>.legacy_sync`, read through `utils.rollout.runtime_percent.legacy_sync_mode()` (30s TTL, last-known-good on read errors).

## Modes

| Mode | Upload admission | Sequencer | In flight |
|---|---|---|---|
| `on` | today | today | today |
| `draining` | no new legacy job: `admit_or_legacy` admits batch, `legacy_fresh.admit` is skipped, intake never falls back to legacy (BYOK and unsupported languages go to `provider_stt`) | dispatches only already-accepted `sync_backfill_pending` entries; registers no new owner | running legacy tasks finish; `sr-` rows on the old binding drain |
| `dark` | as `draining` | sweep and wake return 200 `legacy_dark` without claiming or dispatching; the sweep still runs enrichment repair (`reprocess.sweep`) and `summary_debt_repair.tick` until C4 moves them to `enrichment-maintenance` (lead ruling 10-19) | none (entry precondition) |

Any failure to read the mode serves `on`. During the soak the legacy image, queues and scheduler job are untouched, so `on` is always the safe direction.

## Preconditions

- **`on` → `draining`:** batch percent 100 at a clean fleet gate, C8 `provider_stt` live, cap-hold rehome live (or S12: cap enforcement held at its current cohort), parity gate PASS, the enrichment queue switch (C3) complete, **and the ladder v1 usage budget is debited for batch-admitted cap-hold units** (Subscription session ruling 10-19; lane 6 owns it). `ramp_set.py` refuses to leave `on` until each id in `DRAINING_PRECONDITIONS` (`scripts/rollout/ramp_controller.py`) is confirmed with `--precondition-met <id>`.
- **`draining` → `dark`:** the drain census reads zero twice, at least 10 minutes apart:

  ```bash
  source ~/.local/bin/gcp-agent-env.sh ro-prod        # ro-dev for staging
  cd backend && .venv/bin/python -m scripts.legacy_dark.drain_census --env prod --confirm
  ```

  It gates on `sync_backfill_pending`, sequencer active owners, `sync_redrive_required`, `stt_cap_holds` (upper bound), the depth of `sync-jobs`, `sync-jobs-fresh`, `sync-backfill` and `sync-backfill-fresh`, and `increase(omi_legacy_sync_admissions_total[30m])`. Any unavailable read blocks. Inline (non-Cloud-Tasks) legacy jobs have no aggregate source; the 30-minute zero-admission window plus the 10-minute confirmation bounds them. `--with-ledger` adds informational ledger counts where a collection-group index exists (prod has none).

## Transitions

Only the lead writes `legacy_sync`, under David's merge/deploy authorization; the ramp controller never does.

```bash
source ~/.local/bin/gcp-agent-env.sh prod-operator
cd backend
.venv/bin/python scripts/rollout/ramp_set.py --env prod --show          # note "revision"
.venv/bin/python scripts/rollout/ramp_set.py --env prod --legacy-sync draining \
  --precondition-met cap_hold_ladder_debit --actor lead --reason draining --expected-revision <rev> --apply
.venv/bin/python scripts/rollout/ramp_set.py --env prod --legacy-sync dark \
  --actor lead --reason dark --expected-revision <rev> --apply
.venv/bin/python scripts/rollout/ramp_set.py --env prod --legacy-sync on \
  --actor lead --reason rollback --expected-revision <rev> --apply      # rollback, from either state
```

Without `--apply` each command is a dry run. A revision conflict exits 3: re-read with `--show` and retry.

Each write is a CAS on `_ramp.revision` with a history row. The change takes effect within 30s plus the in-flight request; nothing is redeployed. Record each transition in the run dir STATE.md with the census output.

## The double-processing fence

Content already claimed in `sync_content_ledger` by legacy is never re-admitted to batch and never sent to legacy admission in `draining`/`dark` (`fence_decision`):

| Ledger row | `draining` / `dark` answer | Metric reason |
|---|---|---|
| completed (valid result) | 202 `completed` with the cached segment count, no job | `legacy_completed` |
| cap hold `held` | 202 `completed` with the ledger job id, no job; the status poll answers a valid hold as completed after the Redis TTL (`completed_status`) | `legacy_held` |
| processing, fresh, Redis owner job present (or unknown) | 409 `sync_content_in_progress` with the legacy job id (the shipped "follow the owner" response, lead ruling 10-19); the running legacy task finishes it | `legacy_active` (`legacy_active_in_dark` pages in `dark`) |
| retryable, stale or untimestamped claim, Redis owner job gone (the `claim_sync_content` check), invalid completion | batch adopts it when the intake supports the ledger takeover; otherwise 409 retry-later, client keeps the audio | `legacy_stranded_adopted` / `legacy_stranded` |
| repeat-failure pause active | 409 with `Retry-After` = the pause remaining, never adopted | `legacy_capped` |

An epoch-less backfill task in `draining`/`dark` never runs beside a live sequencer owner for the same uid: if the sequencer already holds the job and its sweep still dispatches (`draining`) the task is acked (`sequencer_owns_job`); while another job is the uid's active owner it answers 409 so the queue retries (`sequencer_owner_active`).

Never 503 (invariant 2). `omi_legacy_dark_ack_total{reason}` counts every fenced answer; `omi_legacy_sync_admissions_total{reason}` must stay flat outside `on`, and a non-`on` admission logs `event=legacy_dark action=legacy_admission outcome=invariant_violation`.

## Signals

- `omi_legacy_sync_mode{mode}`: the mode each process last served (1 for the active mode).
- `omi_legacy_sync_mode_read_total{source}`: reads that fell back to `on` (`absent`, `error`, `malformed`). Non-zero during `draining`/`dark` means some processes are serving legacy.
- `omi_legacy_sync_admissions_total{reason}`, `omi_legacy_dark_ack_total{reason}` as above.

## 12h soak and the auto-proceed criteria

Lane 5's `soak_check.py` runs every 30 minutes for 12 hours from the `dark` write, so there are 24 reads. Lost-recording accounting starts at `draining`, not `dark`.

**Deletion is pre-authorized (David, 2026-10-19 08:15Z).** If **every** read below is green for the whole 12h window, the deletion PRs (including the named C10 `.github/actions/sync-backfill-lifecycle` edit) merge and deploy with no separate `go`.

**Any red or unavailable read means hold and escalate** to the lead, and the lead to David. A hold does not restart the soak by itself: the lead decides between reverting `legacy_sync` to `on` and re-running the 12h window. Prometheus queries run against prod Managed Prometheus (`ro-prod`); `<T_dark>` is the `dark` write time from the `_ramp` history.

| # | Gate | Concrete check (every 30-minute read) | Green when |
|---|---|---|---|
| 1 | **Zero legacy traffic** | `sum(increase(omi_legacy_sync_admissions_total[30m]))` | `0` |
| 1b | | `drain_census --env prod` (it gates on pending, sequencer owners, redrive, cap holds and the four queue depths) | verdict `ZERO` |
| 1c | | `sum(omi_legacy_sync_mode{mode="dark"}) == count(omi_legacy_sync_mode{mode="dark"})` and `sum(increase(omi_legacy_sync_mode_read_total{source=~"error\|malformed"}[30m]))` | every process serves `dark`; `0` fallbacks |
| 1d | | `sum(increase(omi_legacy_dark_ack_total{reason=~"legacy_active_in_dark\|admission_refused"}[30m]))` | `0` |
| 2 | **Outcome SLOs held** | `fleet_gate.sh <T_dark> 20 30 100` (the workspace gate at 100%) | exit 0 (`GATE_PASS`) |
| 2b | | first-summary dispatch: outbox `first_pending_at` → dispatch, the gate's `first_summary_*` tokens | 0 dispatches over 121s |
| 2c | | task targets: `sum(increase(omi_task_unexpected_total[30m]))` plus Cloud Run 5xx/429/503 on `/v2/enrichment/run`, `/v2/batch-pipeline/*` and `/v2/audio-merge-jobs/run` | `0` |
| 2d | | upload 2xx rate per `app_build` on `/v2/sync-local-files` (Cloud Run request logs, `ro-prod` aggregates) against the 24h before `draining` | every build with ≥ 50 uploads within 1 pp |
| 2e | | `max(omi:reason_unknown_ratio:rate30m)` | < 0.02 |
| 3 | **No stuck cohort over 1h** | fleet gate `stuck_job_over_30m` and `obligation_over_15m` | `0` (stricter than 1h) |
| 3b | | oldest unfinished batch unit and oldest `provider_stt` unit (gate aggregate JSON, `oldest_*_age`) | < 3600s |
| 3c | | per-cohort upload 2xx rate (2d) failing for 2 consecutive reads | never (a cohort red for ≥ 1h is red) |
| 4 | **Parity clean** | `soak_check.py` check 5: every `content_id` accepted since `draining` has a projection receipt or a terminal disposition; no `content_id` has both a legacy job and a batch unit | `0` lost, `0` doubled |
| 4b | | BYOK and non-Parakeet uploads: `provider_stt` completions versus admissions (or a census of zero traffic) | all completed or in flight under 1h |
| 4c | | cap-hold redrives served by batch (or S12: cap enforcement still at its pre-dark cohort with `stt_cap_holds` = 0 new) | true |
| 4d | | the last `parity_gate.py --surface prod-shadow` (rows 3–6) from the 100% hold | PASS |
| 5 | **Cost on track** | `backend-sync-backfill` and `backend-sync` legacy-worker billable instance time (`run.googleapis.com/container/billable_instance_time`), last 6h against the 6h before `draining` | ≤ 10% of the pre-draining 6h |
| 5b | | batch GPU nodes (`kubectl` node count on the batch pool, copied KUBECONFIG and explicit context) | ≤ 4 (the 10-19 approval) |
| 5c | | vendor STT spend from vendor usage (Soniox, Deepgram, Modulate), lane 13's receipt, last 12h against the pre-dark 12h | ≤ 1.10× |

**Preconditions for auto-proceed** (all are checked before the first merge; any failure is a hold):

- C4 is merged and serving: `enrichment-maintenance` runs `/v2/enrichment/sweep`, so C10 can delete the old sweep route.
- C3 is complete: no new `sr-` row binds `/v2/sync-jobs/run`.
- The deletion PRs are green against current main, and the C1 ratchet rows for C10 and C11 are at zero (the C11 neutral cap-hold module excepted).

## After the soak: deletion

1. All 24 soak reads are green and the preconditions hold. Record the gate table with each read's values in the run dir STATE.md.
2. **Lead action on `prod-operator`:** capture the live queue configs. This needs `cloudtasks.queues.get`, which `ro-prod` lacks. Commit the spec to the run dir before anything is deleted:

   ```bash
   source ~/.local/bin/gcp-agent-env.sh prod-operator
   cd backend && .venv/bin/python -m scripts.legacy_dark.legacy_queues capture --env prod --spec <run-dir>/legacy-queues.prod.json
   ```

3. Merge the deletion PRs in order C6, C9, C10, C11. Run the train, approve the index run, and verify the release identity (`OMI_BACKEND_RELEASE_SHA` and the absence of the deleted routes).
4. Delete the queues, the `sync-backfill-uid-sequencer` job and the `backend-sync-backfill` service (lead, scripted).
5. Lane 13 books the saving from billing once billed instance-hours fall.

**Rollback after deletion:** redeploy the previous image, then

```bash
.venv/bin/python -m scripts.legacy_dark.legacy_queues recreate --env prod --spec <run-dir>/legacy-queues.prod.json          # dry run
.venv/bin/python -m scripts.legacy_dark.legacy_queues recreate --env prod --spec <run-dir>/legacy-queues.prod.json --apply
.venv/bin/python -m scripts.legacy_dark.legacy_queues verify --env prod --spec <run-dir>/legacy-queues.prod.json
python3 scripts/scheduler_reconcile.py --environment prod --project based-hardware --apply --jobs sync-backfill-uid-sequencer   # from the previous image's tree
```

and set `legacy_sync` back to `on`. Rehearsed on staging at M2 (`--env staging`, queues `staging-*`).
