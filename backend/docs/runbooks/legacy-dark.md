# Legacy dark: retiring legacy sync without a deploy

Contract (h) of the legacy-retire swarm. Code: `utils/sync/legacy_dark.py`. Switch: `rollout_cohorts/_ramp.envs.<env>.legacy_sync`, read through `utils.rollout.runtime_percent.legacy_sync_mode()` (30s TTL, last-known-good on read errors).

## Modes

| Mode | Upload admission | Sequencer | In flight |
|---|---|---|---|
| `on` | today | today | today |
| `draining` | no new legacy job: `admit_or_legacy` admits batch, `legacy_fresh.admit` is skipped, intake never falls back to legacy (BYOK and unsupported languages go to `provider_stt`) | dispatches only already-accepted `sync_backfill_pending` entries; registers no new owner | running legacy tasks finish; `sr-` rows on the old binding drain |
| `dark` | as `draining` | sweep and wake return 200 `legacy_dark` without claiming | none (entry precondition) |

Any failure to read the mode serves `on`. During the soak the legacy image, queues and scheduler job are untouched, so `on` is always the safe direction.

## Preconditions

- **`on` → `draining`:** batch percent 100 at a clean fleet gate, C8 `provider_stt` live, cap-hold rehome live (or S12: cap enforcement held at its current cohort), parity gate PASS, the enrichment queue switch (C3) complete.
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
backend/scripts/rollout/ramp_set.py --env prod --legacy-sync draining   # then dark
backend/scripts/rollout/ramp_set.py --env prod --legacy-sync on         # rollback, from either state
```

Each write is a CAS on `_ramp.revision` with a history row. The change takes effect within 30s plus the in-flight request; nothing is redeployed. Record each transition in the run dir STATE.md with the census output.

## The double-processing fence

Content already claimed in `sync_content_ledger` by legacy is never re-admitted to batch and never sent to legacy admission in `draining`/`dark` (`fence_decision`):

| Ledger row | `draining` / `dark` answer | Metric reason |
|---|---|---|
| completed (valid result) | 202 `completed` with the cached segment count, no job | `legacy_completed` |
| cap hold `held` | 202 `completed`, no job | `legacy_held` |
| processing, fresh, owner present | 409 `sync_content_in_progress` with the legacy job id (the shipped "follow the owner" response); the running legacy task finishes it | `legacy_active` (`legacy_active_in_dark` pages in `dark`) |
| retryable, stale, owner missing, invalid completion | batch adopts it when the intake supports the ledger takeover; otherwise 409 retry-later, client keeps the audio | `legacy_stranded_adopted` / `legacy_stranded` |
| repeat-failure pause active | 409 with `Retry-After` = the pause remaining | `legacy_capped` |

Never 503 (invariant 2). `omi_legacy_dark_ack_total{reason}` counts every fenced answer; `omi_legacy_sync_admissions_total{reason}` must stay flat outside `on`, and a non-`on` admission logs `event=legacy_dark action=legacy_admission outcome=invariant_violation`.

## Signals

- `omi_legacy_sync_mode{mode}`: the mode each process last served (1 for the active mode).
- `omi_legacy_sync_mode_read_total{source}`: reads that fell back to `on` (`absent`, `error`, `malformed`). Non-zero during `draining`/`dark` means some processes are serving legacy.
- `omi_legacy_sync_admissions_total{reason}`, `omi_legacy_dark_ack_total{reason}` as above.

## 12h soak

`soak_check.py` (lane 5) runs every 30 minutes; the checks are listed in contract (h). Lost-recording accounting starts at `draining`, not `dark`.

## After the soak: deletion

1. David's `go` on the board.
2. Capture the live queue configs (needs `cloudtasks.queues.get`; `ro-prod` lacks it):

   ```bash
   source ~/.local/bin/gcp-agent-env.sh prod-operator
   cd backend && .venv/bin/python -m scripts.legacy_dark.legacy_queues capture --env prod --spec <run-dir>/legacy-queues.prod.json
   ```

3. Merge the deletion PRs (C6, C9, C10, C11), train, verify the release identity.
4. Delete the queues, the `sync-backfill-uid-sequencer` job and the `backend-sync-backfill` service (lead, scripted).

**Rollback after deletion:** redeploy the previous image, then

```bash
.venv/bin/python -m scripts.legacy_dark.legacy_queues recreate --env prod --spec <run-dir>/legacy-queues.prod.json          # dry run
.venv/bin/python -m scripts.legacy_dark.legacy_queues recreate --env prod --spec <run-dir>/legacy-queues.prod.json --apply
.venv/bin/python -m scripts.legacy_dark.legacy_queues verify --env prod --spec <run-dir>/legacy-queues.prod.json
python3 scripts/scheduler_reconcile.py --environment prod --project based-hardware --apply --jobs sync-backfill-uid-sequencer   # from the previous image's tree
```

and set `legacy_sync` back to `on`. Rehearsed on staging at M2 (`--env staging`, queues `staging-*`).
