# Operator refusals preserve the paid route

Local audio/budget/funding/provider-configuration checks precede creation or
renewal of speech-redrive intents. Measured speech custody evidence is retained
separately even when preflight refuses. Privacy, ledger and terminal fences still
apply; no held unit is completed or deleted by a refusal.

New operator markers record `paid_state=attempted` on start. Validated words or a
validated empty answer promote that marker to `spent` before artifact persistence
or failure settlement. A caught provider failure permits one explicit invocation
to retry with a new token and preserved failure history. Running/process-loss,
validated-empty, invalid-payload and historical unclassified markers remain held.
This includes prepared epoch-1 take-overs, but does not change automatic recovery.
New CLI approval digests and maximum spend/audio estimates bind both attempts.

Historical refusals have a separate, read-only, exact-ID plan flag. It requires a
recorded complete zero-files vendor usage export for the actual attempt window;
apply is deliberately refused. Validated paid receipts cannot be attested away.
No serving flag, deployment, recovery apply, or historical data change ships with
this source update. See [operator contract](../../listen_pusher_pipeline.mdx#silent-operator-held-unit-redrive)
and [proof format](../../runbooks/paid-attempt-refusal.md).
