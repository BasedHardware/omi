# Synced and late F join safety and cost guards

[PR #24828](https://github.com/BasedHardware/omi/pull/24828) applies the existing F processing-visibility predicate to the incoming conversation before naming or Jev. Unknown or excluded metadata keeps control placement.

F-only timeline queries read at most two documents and require a complete window; a full window keeps control placement. Each transcript names at most two distinct people. Redirects, more than three owner members, or recovered members requiring reconciliation also keep control placement. The close rechecks its budget inside a single-attempt transaction. A sync attach decision attempts F once across all three placement retries.

The worst-case extra synchronous F work, including its close and optimization-off rereads, is 24 document reads and one Jev call. Ordinary placement, recovery and background composition keep their existing work. Live joins and all rollout/kill switches retain their behavior. Guards and read/call accounting live in `backend/tests/unit/test_episode_f_join.py`.

The People-reader inventory is re-audited for the capped predecessor and name-only candidate reader. Both scopes are read-only; no People or generation writer changes.
