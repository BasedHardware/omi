# Dark projection hold observability — validation, 2026-11-08

Repository: `BasedHardware/omi`; lane: `lane/backlog-observability`.
Base checked at intake: `d345ddf271f4178fb62b1dde70ee77f67c7d6e3e` (`origin/main`).
No production reads, writes, deployment, or flag enablement were used.
No GCP identity tier was activated. `backend/.venv` already existed (Python 3.11.15).

Behavior and rollback: [projection contract](../../../utils/batch_pipeline/CONTRACT.md#dark-projection-hold-observability-2026-11-08).

## Initial focused verification

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

## Initial regression verification

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


## Review round 1 — companion failure isolation

The optional companion COUNTs now run after every legacy sample read succeeds.
Each aggregation failure logs only its leg and exception type and omits that
leg. Successful legs still publish. The exporter clears previous companion
series before setting the successful observations, so a failed count neither
exports zero nor leaves a previously exported value behind. Epoch gauges,
freshness and sample-success accounting update normally after companion
failures. A legacy query failure keeps the existing error path and runs no
companion COUNTs. OFF runs no companion COUNTs or series updates.

The focused command above was rerun: **53 passed**, slowest call **0.07 seconds**.
New failure-isolation cases took at most **0.05 seconds**. The same ten-file
file-isolated backend subset was rerun: **423 passed**. Added coverage includes
individual and simultaneous companion failures after an earlier successful
sample, exact equality of all legacy gauge/counter series with the disabled
baseline, no companion operations when OFF, and unchanged legacy-failure
behavior with the companion switch either ON or OFF.

Both switches remain default OFF. No production access, deployment or PR
creation is included.

## Review round 2 — sibling receipt replay

`write_receipt` now returns a sibling hold logging signal only when the summary
state or projection hint transitions into held state. It uses the prior values
already read inside the transaction, so an already-ready acknowledgment that
rewrites the same held summary is silent. Transaction retry attempts read the
current committed state; logging remains after the successful commit. Receipt
updates and OFF-path writes remain unchanged; no reads or deduplication markers
were added.

Regression coverage calls `ready` twice against the same sibling receipt and
checks exactly one hold line when ON, zero when OFF, identical ready receipts,
and unchanged durable contents on replay. Separate cases verify the first
transition logs once when either or both summary state and hint change.

The same focused command passed **58 tests**, slowest call **0.26 seconds**.
The same ten-file file-isolated backend subset passed **428 tests**. Both ran
through the workspace `bin/omi-heavy` from this lane. Only the existing `audioop`
deprecation warning appeared. Live concurrent Firestore transactions and log
ingestion were not exercised; tests use the strict transactional fake store.
