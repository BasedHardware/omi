# Synced and late F join safety and cost guards

[PR #24828](https://github.com/BasedHardware/omi/pull/24828) applies the existing F processing-visibility predicate to the incoming conversation before naming or Jev. Unknown or excluded metadata keeps control placement.

F-only timeline queries read at most two documents and require a complete window; a full window keeps control placement. Each transcript names at most two distinct people. Redirects, more than three owner members, or recovered members requiring reconciliation also keep control placement. The close rechecks its budget inside a single-attempt transaction. A sync attach decision attempts F once across all three placement retries.

The worst-case extra synchronous F work, including its close and optimization-off rereads, is 26 document reads and one Jev call per decision (previously 24 reads). The two additional ownership reads check the unplaced candidate's owner link after `uncertain` and immediately before Jev. A placement found after `uncertain` declines before settlement; a placement found during settlement keeps control placement without asking Jev. Already-placed retries still exit before recorded candidate queries, selected-owner reads or boundary evaluation. Non-close outcomes are bounded by 15 reads (previously 13). Ordinary placement, recovery and background composition keep their existing work. Live joins and all rollout/kill switches retain their behavior. Guards and read/call accounting live in `backend/tests/unit/test_episode_f_join.py`.

These ownership snapshots narrow the concurrent-attach window; they do not guarantee cross-request at-most-once Jev calls. An attach can still commit after the final snapshot. The existing post-Jev membership recheck remains.

The People-reader inventory is re-audited for the capped predecessor and name-only candidate reader. Both scopes are read-only; no People or generation writer changes.
