## Fresh guard cadence and equivalent acceptance counts (SCA-2012)

The November 14 raw GMP evidence recorded sample ages above 120 seconds after
both writers deployed PR #25224. Raw ages alone do not identify query failure
or a scheduling delay. Code inspection and a deterministic stalled-cleanup
test establish a scheduling defect: sampling was inside the general maintenance
pass, and the serving supervisor awaited that whole pass before its next tick.
The test reproduces age 180s while that pass is still occupied. This does not
claim that every production age breach has that one cause.

An independent supervised timer now checks the **same** maintenance lease every
20s and runs bounded count work on the shared DB executor instead of waiting on
the general pass/sync executor. The existing guard lock coalesces overlaps and
limits count starts to once per 60s per process, including opportunistic calls
from maintenance. Followers deactivate the collector. Pump-only instances do
not start this timer. Lease acquisition retains its existing fail-open contract;
this advisory lease is not a new correctness fence. Thread-pool or query failure
can still prevent samples: stale ratios expire, failed pairs clear counts, and
age advances honestly. Scrapes never do IO.

The result-class writer remains exclusively `OrderedMerge.commit_next`;
no result row or routing reader changes. The additional read-only acceptance
reader is `scripts/fresh_guard_cohort.py`: two count aggregations using stored
`fresh_capture == True`, inclusive commit bounds, and the pending subset. It
requires the matching read-only tier and an explicit sample time, emits counts
and bounds without document/content reads, and produces no healthy ratio for
empty or failed queries. It replaces the external `projection_cohort.py` for
this check because fresh_first/capture age does not select the guard's cohort.
Existing declared indexes cover the unchanged shapes; no schema deployment.

`omi_batch_pipeline_fresh_guard_sample_timestamp_seconds` exposes the pre-RPC
window anchor while counts are valid, enabling the independent count command
to select exactly that window. Sample age still starts at pair completion.
The default-on existing kill switch suppresses all guard gauges/queries. New
timer overhead is up to three maintenance-lease checks per minute per serving
replica; count cost is unchanged (roughly one read per 1,000 index entries per
count, minimum two reads per pair). Independent comparisons cost another pair.

Contracts: `utils/batch_pipeline/CONTRACT.md` and
`docs/batch-pipeline-serving.md`. Verification uses synthetic rows only; no live
acceptance or production action is claimed. Release owner must admit the new
image through its train and verify collector retention of the anchor gauge,
then record two equivalent comparisons at least 30 minutes apart within one
percentage point and a complete hour of sample age below 120s. Rollback is an
image revert through that owner, or the existing guard kill switch via controlled
config; no data rollback or projection/provider/hold behavior changes.
