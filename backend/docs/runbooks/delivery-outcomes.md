# Delivery outcome baseline

`omi_delivery_outcome_total{kind,outcome}` counts completed attempts at durable
summary, sync callback and action-item export boundaries. `kind` is one of
`summary`, `sync`, `action_item_export`; `outcome` is `delivered`, `no_op`,
`deferred`, `failed`. Unknown values are rejected before creating label
children. No owner, key, conversation, job, path or provider text is a label.

Summary outcomes emit after the write commits, once across transaction retries.
An unchanged banked summary, discarded output or intentionally waived short-clip
summary is a no-op. A kept minimum with open summary debt and local-only work are
deferred. An empty-output obligation exhausted by the consumer is failed.
The existing first-summary receipt, latency and debt contracts are unchanged.

Sync callback holds, absent/redirected targets, open live targets and fences are
deferred; settled holds and discarded output are no-ops. A persisted visible
result with visible summary is delivered; a kept minimum without confirmed summary
remains deferred. Export counters count one result per item, including
no-integration/already-exported no-ops and device enqueue/lease deferrals.
Device enqueue is not proof of device delivery. Failed attempts can be retried,
so these are attempt counters, not unique deliveries or a billing ledger.

Both GMP profiles keep this family, the People reuse family, billed reads by
caller/origin and the Firestore leader-lease family. The production inventory
was refreshed using `ro-prod` aggregate metric names only; declared metrics
remain distinct from names actually observed. No production account data read.

## Alarm admission

The no-op alarm is **unarmed**; this PR adds no alert rule. Infracost owns the
baseline after the lead deploys. Record the first serving release SHA, traffic
percentages and first visible counter timestamp. For each kind and service,
collect seven full days after both the new release reaches all serving traffic
and its counter is visible before proposing an alarm or threshold. Gaps or
missing scrapes do not count as clean baseline. Compare the no-op fraction
`no_op/(no_op+delivered)` separately by kind and service with minimum-volume,
latency and error guards; choose a sustained six-hour threshold from that baseline. Deferred and
failed attempts remain separate signals. Do not invent a threshold now.

First baseline review is due within three days of deploy; that review records
progress and the earliest eligible alarm date, and cannot waive the seven-day
hold. The rollout lead owns merge/deploy. No production writes or alarm changes
are authorized by this code. Metrics ship on; rollback is a code revert in a
later lead-owned train. This instrumentation itself has no booked savings.
