# Serving custody and all-runtime rollback validation (2026-11-05)

Round 10 on `lane/spkfix`, starting from `bb0b40c724db` on
`origin/main` `9ad243c066ac`. Final implementation: `c033c7716934`, rebased onto
fetched main `747ccc9ddcd4`. Post-rebase: **1,185 focused cases and all 55
selected manifest/preflight checks passed**. All data were synthetic and all checks local.
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
parallel repeat stopped when the Firestore query file hit its
300-second wall timeout at 96%. Checks stop on the first failure; this was not
52 completed checks. No assertion failure was reported. A serial
repeat retained the same time limits and passed the seven-file Firestore guard
in 209 seconds (the query file took 130 seconds), plus the flag registry and its
fixtures. Its line-count ratchet then found a synthetic GMP merge conflict:
the shared `origin/main` ref had moved after preflight selected `9ad243c066ac`.
The implementation was committed before fetching/rebasing; its post-rebase
results follow. A later deployment-boundary check required classifying the newly
bound existing kill switch as `config` (non-secret). That catalog entry is
included in the final complete 55-check run below.

## Post-rebase gate

Fetched main `747ccc9ddcd4` and rebased all lane commits. The implementation
commit changed from `e4e1e96de8cc` to `c033c7716934`; none was amended or pushed.
Only GMP required conflict resolution. Its keep regex retains main's
`finalization_pair_.*` / `enrichment_summary_repair_.*` families and the branch's
final-pass counters, durable terminal count/freshness, unit-skip counter and
complete agreement/latency/owner-delta histogram families. A read-only regex
comparison retained all 195 previously admitted inventory/probe metric names
from either source plus every final-pass `_bucket`, `_sum`, `_count` suffix.

The exact focused commands above were rerun on the rebased implementation:

| Command group | Post-rebase result |
| --- | --- |
| First nine-file serving/custody command (now including all ten direct tests) | 414 passed |
| Twenty-file reconstruction/lifecycle/resources/privacy command | 758 passed |
| Isolated worker/chart command | 13 passed |
| Total focused cases | 1,185 passed |

After adding the deployment-setting catalog entry, its real validator passed:

```bash
backend/.venv/bin/python .github/scripts/check_deployment_secret_boundary.py \
  --base 747ccc9ddcd4b36caa86ae052084d09152b26982
```

The complete preflight manifest then passed **55 checks**, with no skipped failure.
This uses the same check runner as `make preflight`, retaining all selected
checks and time limits. The base is pinned to the fetched SHA because another
worktree can update the shared `origin/main` ref during validation. `--keep-going`
reports every check instead of cancelling peers at the first failure.

```bash
OMI_CHECKS_JOBS=2 BACKEND_PYTEST_WORKERS=1 OMI_PREFLIGHT_BACKGROUND=0 \
  backend/.venv/bin/python .github/scripts/run_checks.py \
  --lane local --base 747ccc9ddcd4b36caa86ae052084d09152b26982 \
  --keep-going --pr-body-file /Volumes/Ephemeral/scratch/spkfix/round10-pr-body.md
```

Pusher source/dependency closure passed in the preflight. A separate import-graph
assertion confirmed `utils.conversations.final_pass_retry` is reachable in both
role/legacy Pusher images and absent from the GPU batch-pipeline worker closure.
The actual finalization route fixture retains its run lock and checks that direct
speaker settlement follows canonical completion through `process_conversation`.

## Practical limits

Live runtime bindings, replacement pods/revision traffic, owner-data acceptance
and the T+2h GPU-hours/day measurement were **not verified**. The readout record
is explicitly unmeasured. No container image was built or deployed. Closure
checks establish source/dependency availability, not an installed release.
