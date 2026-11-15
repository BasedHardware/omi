# Dark quiet-check empty exit

P0 freeze exemption: lead2, bus 8c0822. `QUIET_EMPTY_EXIT_ENABLED`
is default off in `config/refactor_modes.py`; false restores prior decisions and
writes. New admission is restricted to exact batch-live ownership, a closed explicit
received-false archive, no pointers/content/tokens/upload failure, a known expired
recording lease and empty retained/raw storage proof. The deletion transaction
rechecks that shape, switch and storage proof. Unowned and other nonparticipants
follow base admission. Where base would retry an undecidable owner/lease forever,
the check retires with a named repair/operator-review exit, leaving the row intact.
There is no quiet attempt/deadline budget; due and dispatch formulas are unchanged.
`listen_quiet_check_empty_exit_total{disposition,mode}` counts would-be exits while
dark and actual decisions when enabled, without identities.

Contract: [server batch custody](../../listen_pusher_pipeline.mdx).
Activation belongs to the lead after staging repair and backlog settlement;
this commit supplies no deployment binding and changes no timer or dispatch.
Rollback: set `QUIET_EMPTY_EXIT_ENABLED=false`.

Review amendment: both FIX-FIRST quiet findings were verified against the original
`5f0405b6b24d` (`conversation_quiet_checks.py:195-219`,
`recording_sessions.py:302-316`). The new branch widened unowned deletion and
rearmed unknown leases without a budget. Regressions cover unowned tokens and
pre-pointer chunks, unknown/invalid leases, markerless ownership and fenced races.

Registry policy after the fresh upstream rebase classifies this default-off gate
as a rollout. Proposed lead2-owned review target: 2026-11-16. Cohorts are dark
validation/staging, a separately approved repair drain, then all serving roles
after staging/backlog acceptance. Protected-row deletions and endless quiet
rearming must stay zero; inspect the disposition counter and orphan stock before
expansion. This plan grants no activation or deployment authority.
