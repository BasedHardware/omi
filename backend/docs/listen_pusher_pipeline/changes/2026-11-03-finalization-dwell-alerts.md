# Finalization dwell alerts

[Finalization recovery contract](../../listen_finalization_jobs.mdx#reconciliation-and-runbook)
adds blocked-BYOK dwell alerts at 3 days (informational) and 7 days (page),
informational dead-letter stock (>1,000) and time in dead_letter (>7 days)
alerts, and an informational daily BYOK abandonment inventory alert (>0).
Periodic COUNT aggregations cover all-generation terminal stock and committed
BYOK abandonments in the last 24h; a post-commit counter remains best-effort.
Dead-letter age uses terminal_at; blocked-BYOK lacks a status-entry clock and
retains the disclosed created_at proxy. The first deploy will page on the
existing 13-day backlog; on-call only confirms auto-conversion at day 14.
`two-lane-lead` owns disposition.
No state transition, retention bound, credential handling, flag or wire contract
changes. The rollout lead owns deploy and monitoring provisioning.

Initiative: [explicit-state latch invariant](https://claude.ai/artifact/7srvSdinev4M8oiSKotRiU).
