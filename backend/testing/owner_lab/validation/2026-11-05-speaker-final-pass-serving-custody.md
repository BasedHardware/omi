# Serving custody and all-runtime rollback validation (2026-11-05)

Round 10 on `lane/spkfix`, starting from `bb0b40c724db` on
`origin/main` `9ad243c066ac`. All data were synthetic and all checks local.
GCP tier: none. No production/account reads, deployment, push or PR.
Private untracked owner-lab helpers were excluded from staging.

## Findings covered

- Every primary production processing runtime explicitly binds the existing
  `BATCH_FINAL_PASS_ENABLED`: GKE backend-listen/Pusher via the shared ConfigMap,
  Cloud Run backend/sync/sync-backfill/integration via literal env bindings.
  The installed dedicated sync worker inherits that ConfigMap switch too.
  Independent-roster admission rejects a missing runtime flag, disagreement,
  ambiguous literals and chart overrides that defeat the shared map.
- Direct and queued attempts use the same immutable membership obligation and
  atomic terminal counter/receipt. A direct replay claims pending work without
  waiting for its wake; live/closed rows suppress duplicate automatic work while
  still refreshing manual authority. Direct terminal results settle only after
  canonical persistence. Initial direct custody leaves four subsequent claims;
  pending direct replays spend the same cap. Interrupted direct custody has a
  one-hour lease; retries keep their existing 15-minute leases and bounded backoff.
- Tests cover successful direct replay before a queued wake, a wake during the
  direct persistence lease, duplicate direct/callback delivery, failed canonical
  persistence, an ambiguous committed settlement, shared exhaustion, disabled
  controls and fresh manual overlays on a closed obligation. The actual locked
  finalization endpoint fixture verifies settlement follows canonical completion.
- The runbook specifies immediate 100% serving, all-surface rollback/restarts,
  and the [owning T+2h GPU-hours/day record](../../../docs/operational/batch-speaker-serving-readout.md).
  Managed direct/retry results share the existing durable terminal metric name;
  raw/unmanaged invocations retain the original local counter.

## Exact successful commands

Commands below run from `backend/`, through the host's
`omi-heavy run --wait 1800 --no-priority --` admission wrapper.

Focused serving/custody/metrics/deployment contracts: **412 passed**
(the direct suite had eight cases at this point; two additional cases were then
added and the complete ten-case suite rerun below).

```bash
.venv/bin/python -m pytest \
  tests/unit/test_batch_final_pass_runtime.py \
  tests/unit/test_batch_final_pass_direct.py \
  tests/unit/test_batch_final_pass.py \
  tests/unit/test_batch_final_pass_retry.py \
  tests/unit/test_batch_final_pass_outage.py \
  tests/unit/test_batch_final_pass_terminal_metrics.py \
  tests/unit/test_recovery_discard_pipeline.py \
  tests/unit/test_batch_conversation_speakers.py \
  tests/unit/test_conversation_speaker_resolution_stage.py -q
```

Production-shaped reconstruction, lifecycle, bounded resources, transient errors
and privacy regression suites: **758 passed**.

```bash
.venv/bin/python -m pytest \
  tests/unit/test_batch_final_pass_repro.py \
  tests/unit/test_batch_final_pass_lifecycle.py \
  tests/unit/test_batch_final_pass_resources.py \
  tests/unit/test_batch_final_pass_transient.py \
  tests/unit/test_owner_lab_final_pass_repro.py \
  tests/unit/test_final_pass_assignment.py \
  tests/unit/test_final_pass_vad_compaction.py \
  tests/unit/test_sync_final_pass_budget.py \
  tests/unit/test_final_pass_promotion.py \
  tests/unit/test_final_pass_rehome.py \
  tests/unit/test_batch_pipeline_privacy.py \
  tests/unit/test_batch_privacy_conversation_fence.py \
  tests/unit/test_fsr_wq12_batch_privacy.py \
  tests/unit/test_bpp_generation_memo.py \
  tests/unit/test_batch_pipeline_artifacts.py \
  tests/unit/test_batch_cleanup_custody.py \
  tests/unit/test_batch_pipeline_quarantine_recovery.py \
  tests/unit/test_batch_pipeline_speech_redrive_retention.py \
  tests/unit/test_batch_pipeline_leaf_timings.py \
  tests/unit/test_batch_pipeline_boundary_geometry.py -q
```

Worker imports/authenticated pulls and rendered chart: **13 passed** in its own
pytest process (preserving the import-isolation assertion).

```bash
.venv/bin/python -m pytest tests/unit/test_sync_worker_runtime.py -q
```

Final direct-custody suite, including disabled resolver and fresh manual overlay:
**10 passed**.

```bash
.venv/bin/python -m pytest tests/unit/test_batch_final_pass_direct.py -q
```

Hermetic deployment gate: **453 pytest cases passed**, plus runtime-manifest,
workflow/source admission, frame-bucket and MCP contracts. No `--live` option.

```bash
PATH="$PWD/.venv/bin:$PATH" bash scripts/pre-deploy-check.sh
```

Repository formatter, from the repository root: Black with repository settings
(line length 120, no string normalization); all changed Python files formatted.

```bash
scripts/backend-python-format --write \
  backend/database/batch_final_pass_retry.py \
  backend/utils/conversations/final_pass_retry.py \
  backend/utils/conversations/processing_speakers.py \
  backend/utils/conversations/process_conversation.py \
  backend/utils/conversations/speaker_resolution.py \
  backend/scripts/runtime_env_capability_contracts.py \
  backend/scripts/runtime_env_validation/manifest.py \
  backend/tests/unit/test_batch_final_pass_direct.py \
  backend/tests/unit/test_batch_final_pass_runtime.py \
  backend/tests/unit/test_batch_final_pass.py \
  backend/tests/unit/test_recovery_discard_pipeline.py \
  backend/tests/unit/test_sync_worker_runtime.py
```

Repository preflight, from the root (local review metadata; no PR created):

```bash
OMI_PR_BODY_FILE=/Volumes/Ephemeral/scratch/spkfix/round10-pr-body.md make preflight
```

Preflight development runs: the initial inventory drift was regenerated. A
parallel 53-check repeat passed 52 checks but the Firestore query file hit its
300-second wall timeout at 96%. No assertion failure was reported. A serial
repeat retained the same time limits and passed the seven-file Firestore guard
in 209 seconds (the query file took 130 seconds), plus the flag registry and its
fixtures. Its line-count ratchet then found a synthetic GMP merge conflict:
the shared `origin/main` ref had moved after preflight selected `9ad243c066ac`.
The implementation is committed before fetching/rebasing; post-rebase results
will be recorded in the follow-up validation update.

## Practical limits

Live runtime bindings, replacement pods/revision traffic, owner-data acceptance
and the T+2h GPU-hours/day measurement were **not verified**. The readout record
is explicitly unmeasured. No container image was built or deployed. Closure
checks establish source/dependency availability, not an installed release.
