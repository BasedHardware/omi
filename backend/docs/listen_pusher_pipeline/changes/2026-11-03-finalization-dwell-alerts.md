# Finalization dwell alerts

[Finalization recovery contract](../../listen_finalization_jobs.mdx#reconciliation-and-runbook)
adds blocked-BYOK dwell alerts at 3 days (informational) and 7 days (page),
informational dead-letter stock (>1,000) and oldest-created age (>7 days)
alerts, and an informational daily BYOK abandonment conversion alert (>0).
A dedicated post-commit counter observes conversions; stock reuses projection
shards and age adds one indexed limit(1) query. two-lane-lead owns disposition.
No state transition, retention bound, credential handling, flag or wire contract
changes. The rollout lead owns deploy and monitoring provisioning.

Initiative: [explicit-state latch invariant](https://claude.ai/artifact/7srvSdinev4M8oiSKotRiU).
