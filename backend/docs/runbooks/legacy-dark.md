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

- **`on` → `draining`:** batch percent 100 at a clean fleet gate, C8 `provider_stt` live, cap-hold rehome live (or S12: cap enforcement held at its current cohort), parity gate PASS, the enrichment queue switch (C3) complete, **and the ladder v1 usage budget is debited for batch-admitted cap-hold units** (Subscription session ruling 10-19; lane 6 owns it)., **and onthway's operator minimal-mode redrives (#22503) are finished or moved to the batch redrive path** (lead ruling 10-20 05:17Z: `draining` stops new sequencer registration, which minimal redrive needs, and C11 deletes it). **C8 provider-STT is live in prod** (`provider_stt_live`: the provider-stt queue, `PROVIDER_STT_TASKS_*` env and the enrichment maintenance job, which also sweeps the provider-stt outbox; M3 review), **and conversations still owned by `legacy_final_pass_v1` with no live legacy job are re-homed to batch** (`legacy_final_pass_rehomed`; lead ruling 10-21 b209a5). `ramp_set.py` refuses to leave `on` until each id in `DRAINING_PRECONDITIONS` (`scripts/rollout/ramp_controller.py`) is confirmed with `--precondition-met <id>`.

  The re-home sweep is the evidence for `legacy_final_pass_rehomed`. It needs the `conversations.record_lane_owner` collection-group field index (`scripts/reconcile_firestore_indexes.py --provision-missing`, as the M2 staging cycle did for the ledger index; provision it well before the flip, the group index builds over every conversation). The gate is confirmed on leaving `on` when the re-home mechanism (#23129) serves on every revision and the dry run has sized the stock; the sweep is **applied in `draining`**, at least 5 minutes after the flip (`--apply` refuses `on` and the grace: at `on` it cannot serialize with live legacy admission), and repeated until `CLEAR` before `dark`:

  ```bash
  source ~/.local/bin/gcp-agent-env.sh ro-prod        # at on: dry run, counts only
  cd backend && .venv/bin/python -m scripts.legacy_dark.final_pass_rehome --env prod
  source ~/.local/bin/gcp-agent-env.sh prod-operator  # in draining, >= 5 min after the flip; keep the receipt
  .venv/bin/python -m scripts.legacy_dark.final_pass_rehome --env prod --apply --output <run-dir>/final-pass-rehome.json
  ```

  A conversation the sweep holds (an active legacy ledger claim, a retryable legacy row, or any legacy ledger row created in the last 10 minutes for its uid; the probe is read fresh per conversation) is re-homed later by its next upload, from the exact Redis pending index (`utils/sync/final_pass_rehome.py`). A `--limit` run reports `PARTIAL`, never `CLEAR`.
- **`draining` → `dark`:** the re-home sweep reads `CLEAR`, and the drain census reads zero twice, at least 10 minutes apart:

  ```bash
  source ~/.local/bin/gcp-agent-env.sh ro-prod        # ro-dev for staging
  cd backend && .venv/bin/python -m scripts.legacy_dark.drain_census --env prod --confirm
  ```

  It gates on `sync_backfill_pending`, sequencer active owners, `sync_redrive_required`, `stt_cap_holds` (upper bound), the depth of `sync-jobs`, `sync-jobs-fresh`, `sync-backfill` and `sync-backfill-fresh`, and `increase(omi_legacy_sync_admissions_total[30m])`. Any unavailable read blocks. Inline (non-Cloud-Tasks) legacy jobs have no aggregate source; the 30-minute zero-admission window plus the 10-minute confirmation bounds them. A stranded `sr-` enrichment backlog on a legacy queue (C3's pre-switch rows still bound to `sync_handler`) is non-blocking for `dark` entry only when the enrichment route is switched (`ENRICHMENT_ROUTE=enrichment_queue`) AND the backlog's cause is external, as on staging, where the LLM gateway is blackholed (lead ruling 10-20). Every legacy count must still read zero, including non-`sr-` tasks (operator count of task names). Prod's gateway works, so prod's pre-switch backlog drains and the plain census applies. `--with-ledger` adds informational ledger counts where a collection-group index exists (prod has none).

## Transitions

Only the lead writes `legacy_sync`, under David's merge/deploy authorization; the ramp controller never does.

```bash
source ~/.local/bin/gcp-agent-env.sh prod-operator
cd backend
.venv/bin/python scripts/rollout/ramp_set.py --env prod --show          # note "revision"
.venv/bin/python scripts/rollout/ramp_set.py --env prod --legacy-sync draining \
  --precondition-met cap_hold_ladder_debit --precondition-met minimal_redrive_finished \
  --precondition-met provider_stt_live --precondition-met legacy_final_pass_rehomed --actor lead --reason draining --expected-revision <rev> --apply
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

A conversation whose `record_lane_owner` is `legacy_final_pass_v1` (a durable route owner, not a ledger row) is re-homed in `draining`/`dark` by its next upload, in both the router route and batch intake, once the ramp document is at least 5 minutes old (`FLIP_GRACE_SECONDS`): a request that read `on` just before the flip can still create a legacy job after it, visible to the live-job probe only once created, and the router re-reads a mode older than `ADMISSION_REVALIDATE_SECONDS` (60s) before creating any legacy job, so with the 30s ramp cache no stale `on` creates one later than 90s after the flip. With no live legacy job for the uid (the Redis pending index) its owner moves to `batch_sync_v1` by the same revision-fenced CAS every owner transition uses, and the upload is admitted to batch intake, which keeps its privacy, binding and predecessor fences (`legacy_final_pass_rehomed`). While a legacy job is live for the uid, inside the grace, or when the CAS is lost to a concurrent claim, the upload gets the in-progress 409 (`legacy_active`) and the client retries; `promote_final_pass_if_current` refuses a batch-owned conversation, so a final pass still running cannot promote over batch's work. Outside `on` no new `legacy_final_pass_v1` owner is created: the shadow final pass neither claims nor starts for an unowned conversation, and an ownerless upload for a narrowed uid takes `batch_sync_v1`. The pre-flip stock is cleared by the sweep above, applied in `draining`.

An epoch-less backfill task in `draining`/`dark` never runs beside a live sequencer owner for the same uid: if the sequencer already holds the job and its sweep still dispatches (`draining`) the task is acked (`sequencer_owns_job`); while another job is the uid's active owner it answers 409 so the queue retries (`sequencer_owner_active`).

Never 503 (invariant 2). `omi_legacy_dark_ack_total{reason}` counts every fenced answer; `omi_legacy_sync_admissions_total{reason}` must stay flat outside `on`, and a non-`on` admission logs `event=legacy_dark action=legacy_admission outcome=invariant_violation`.

## Signals

- `omi_legacy_sync_mode{mode}`: the mode each process last served (1 for the active mode).
- `omi_legacy_sync_mode_read_total{source}`: reads that fell back to `on` (`absent`, `error`, `malformed`). Non-zero during `draining`/`dark` means some processes are serving legacy.
- `omi_legacy_sync_admissions_total{reason}`, `omi_legacy_dark_ack_total{reason}` as above.

## Evidence-based soak (6h floor) and the auto-proceed criteria

The soak is evidence-based with a 6h floor (David, 2026-10-20), replacing the 12h clock. Lane 5's `soak_check.py` runs every 30 minutes from the `dark` write with `--history-dir <run-dir>/soak-reads` (one directory per `dark` write). Each read is kept, and the last line, `SOAK_WINDOW_<STATUS> <reason>`, judges the whole window. Lost-recording accounting starts at `draining`, not `dark`.

```bash
cd backend && .venv/bin/python scripts/parity/soak_check.py --env prod \
  --draining-since <T_draining> --dark-since <T_dark> --collect \
  --fleet-output fleet.txt --evidence soak_evidence.json \
  --history-dir <run-dir>/soak-reads --output soak_report.json
```

`fleet.txt` is `fleet_gate.sh <T_dark> 20 30 100` (T0 is `dark`, so its `completed` count is the window's), and `soak_evidence.json` carries the `lost_recordings` census taken at the same read (`scripts.legacy_dark.lost_recordings --since <T_draining>`, no `--until`).

The window passes (`SOAK_WINDOW_PASS`, exit 0) only when **all** of these hold:

1. **Elapsed:** the last read is at least 6h after `dark` (`MIN_SOAK_SECONDS`).
2. **Every read green for the whole window:** every read since `dark` is `SOAK_PASS` (all ten checks, including check 5, zero lost recordings), with no gap over 45 minutes between `dark`, consecutive reads and now.
3. **Final census:** the last read's check 5 census is fresh (its `until` is within the census's 1h grace plus 15 minutes of that read), so the zero-lost result covers the window's end, not an earlier read.
4. **The window saw traffic** (`WINDOW_FLOORS`, prod): at least **2,000 batch completions** (the last read's fleet-gate `completed`, counted from `dark`) and at least **1,000 uploads accepted** (the census's `accepted_content_ids` at the last read minus at the first read after `dark`). Staging floors are 20 and 20.

Any FAIL read fails the window (`SOAK_WINDOW_FAIL`, exit 1; `data_loss` when it was check 2 or 5). Anything else short, such as a PENDING read, a gap, a stale census, a floor not reached or an unreadable history, is `SOAK_WINDOW_PENDING` (exit 3), never a pass. A quiet night therefore extends the soak past 6h until the floors are met.

**Deletion is pre-authorized (David, 2026-10-19 08:15Z).** If the window passes and **every** read below is green for the whole window, the deletion PRs (including the named C10 `.github/actions/sync-backfill-lifecycle` edit) merge and deploy with no separate `go`.

**Any red or unavailable read means hold and escalate** to the lead, and the lead to David. A hold does not restart the soak by itself: the lead decides between reverting `legacy_sync` to `on` and re-running the window in a fresh history dir. Prometheus queries run against prod Managed Prometheus (`ro-prod`); `<T_dark>` is the `dark` write time from the `_ramp` history.

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
| 5c | | vendor STT spend from vendor usage (Soniox, Deepgram, Modulate), lane 13's receipt, the window since `dark` against the same length before `draining` | ≤ 1.10× |

**Preconditions for auto-proceed** (all are checked before the first merge; any failure is a hold):

- C4 is merged and serving: `enrichment-maintenance` runs `/v2/enrichment/sweep`, so C10 can delete the old sweep route.
- C3 is complete: no new `sr-` row binds `/v2/sync-jobs/run`.
- The deletion PRs are green against current main, and the C1 ratchet rows for C10 and C11 are at zero (the C11 neutral cap-hold module excepted).

## After the soak: deletion

1. The last read prints `SOAK_WINDOW_PASS`, every gate-table read is green and the preconditions hold. Record the window JSON (`window` in `soak_report.json`) and the gate table with each read's values in the run dir STATE.md.
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
