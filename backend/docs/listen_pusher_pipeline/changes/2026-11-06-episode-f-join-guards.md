# Episode F join safety guards

PR: [#24730](https://github.com/BasedHardware/omi/pull/24730).
The episode lifecycle remains the overlay described in
[the pipeline contract](../../listen_pusher_pipeline.mdx).

Before F Jev receives predecessor speech, its pinned conversation must still be
a retained member with current, owner-scoped processing visibility. Existing
episode visibility predicates reject discarded, duplicate/merged-away and
deleted content; lock, hold, privacy and ownership checks fail closed when
unknown. Ordinary owner-only sharing visibility `private` remains eligible.
An explicitly pinned absent predecessor cannot be replaced by a later attachment.

Killed, inactive, zero-percent and absent-rule/default-zero F cohorts add no arm
field to episode opening payloads. Only admitted F splits use retained-member
close windows; ordinary and flag-off closes retain existing reads and recorded
end behavior. UID bucketing stays stable and zero percent excludes hash zero.

The predecessor tail is selected before naming. Each F settle reads one
predecessor document and at most eight people-name documents, without photo or
people-learning projection reads. It asks Jev once. A moved-on answer rereads the
episode before splitting (author commit `118de9715e`). After a committed F detach,
one owner observation after the retry loop costs at most two document reads.
These safety checks use exact metadata snapshots and never follow episode
redirect chains; redirect ambiguity is reported as an unknown observation.
The maximum is twelve extra document reads and one Jev call for a close, or
twenty-two reads and two calls across the two-attempt CAS sequence. Shared flag
refresh is separate.

An observed detached candidate without a live member owner increments
`omi_episode_boundary_total{outcome="f_orphan"}` and emits a content-free
`event=episode_f_join_orphan outcome=no_live_successor` error log. Unknown reads
emit `f_orphan_check_error` and a separate log. Successful retry recovery is not
an orphan; flag-off and non-split moments make no observation reads.

The runtime ramp remains `episode_f_join`, default dark, with
`EPISODE_F_JOIN_ENABLED=off` as the process kill switch. Lead2 owns deployment
and expansion. Regression coverage lives in `test_episode_f_join.py` and
`test_episode_f_join_guards.py`, including full serialized main opening payload
comparisons and flag-off legacy recorded-end behavior.
