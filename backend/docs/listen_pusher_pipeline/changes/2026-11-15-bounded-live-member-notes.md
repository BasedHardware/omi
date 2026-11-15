# Bounded live-member notes

The [member-note ownership contract](../../listen_pusher_pipeline.mdx#home-processing-ownership)
now releases idle episode owners through the existing Home idle-close transaction
and admits one extra member-note attempt after a finalization job is 180 seconds old.
This applies to durable retries, preserves occasion membership, and does not scan
or recompose old episodes when a process starts. The default-on kill switch is
`HOME_LIVE_MEMBER_NOTES_BOUNDED_ENABLED`; off restores the prior live-owner gate.

The revision permit is consumed immediately before notes generation. A process
crash may leave that extra attempt uncertain: it is never automatically purchased
twice. Closing the episode or an explicit user reprocess exits the fallback budget.
The normal 30-minute occasion window precedes job creation; this correction removes
unbounded ownership waiting, not that window. Local regression and contention
evidence is recorded by lane Q12-T in the quality push handoff.
