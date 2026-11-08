# Dark projection hold observability — validation, 2026-11-08

Repository: `BasedHardware/omi`; lane: `lane/backlog-observability`.
Base checked at intake: `d345ddf271f4178fb62b1dde70ee77f67c7d6e3e` (`origin/main`).
No production reads, writes, deployment, or flag enablement were used.
No GCP identity tier was activated. `backend/.venv` already existed (Python 3.11.15).

Behavior and rollback: [projection contract](../../../utils/batch_pipeline/CONTRACT.md#dark-projection-hold-observability-2026-11-08).

## Focused verification

From the lane worktree, using the workspace's `bin/omi-heavy` (the public checkout
has no `bin/omi-heavy`):

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- backend/.venv/bin/python -m pytest \
  backend/tests/unit/test_batch_projection_hold_observability.py \
  backend/tests/unit/test_batch_timeliness_all_time.py -q --durations=5
```

Result: **45 passed**. Slowest call: **0.31 seconds**. Covers all five bounded
hold reasons, disabled behavior, failed commits/replays, single/multipart receipt
write equivalence, strict opt-in in all parser modes, and fake-store all-time
counts without extra document walks. Disabled collection emits no companion
series; enabling adds exactly three unbounded COUNT aggregations per refresh.

## Regression verification

The file-isolated `backend/test.sh` runner exercised these ten files:

- `test_batch_projection_hold_observability.py`
- `test_batch_timeliness_all_time.py`
- `test_batch_pipeline_projection.py`
- `test_batch_pipeline_timeliness.py`
- `test_batch_pipeline_hold_recovery.py`
- `test_batch_projection_source_deleted.py`
- `test_flag_budget.py`
- `test_monitoring_telemetry_contract.py`
- `test_pipeline_sim_poison_head.py`
- `test_batch_jobs_read_origins.py`

All paths are relative to `backend/tests/unit/`. Command:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- env \
  BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/backlog-observability-tests.txt \
  bash backend/test.sh
```

Each of the ten pytest processes reported success, **415 tests passed** in total.
The list file contains one `tests/unit/<filename>` per line, using the names above.
Existing `audioop` deprecation warnings were the only test warnings.
The monitoring inventory tests passed without adding this diagnostic metric to
`metric-inventory.prod.json`; no alert references it. The existing `omi_.*` GMP
scrape keep-list admits the companion metric when enabled.

## Limits

This is hermetic source-level verification. Live Firestore index acceptance,
aggregation cost/latency, log ingestion, production sample counts and deployed
metric ingestion were not verified. No production access or deployment is
included. Both switches remain default OFF.
