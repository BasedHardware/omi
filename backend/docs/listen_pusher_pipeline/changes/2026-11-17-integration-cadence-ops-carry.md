# Preserve the admitted integration sweep settings

The integration ops config now carries a 100-row serving sweep every 20 seconds
and a finish classification page limit of 16. These are the values admitted by
the margin-40 lead and applied by Release on 2026-11-16. Declaring them in the
ops config keeps subsequent config trains from treating them as unexplained
live-only settings. The staging integration service mirrors the keys under the
existing prod/staging parity contract.

This changes config source only. A merge does not dispatch a config train,
create a revision, establish a clean guard window or prove monetary savings.
The privacy qualification map is separate and is not changed by this carry.
Normal privacy, custody, funding and provider checks remain in force.

Release retains runtime rollback and must serialize it with config trains.
The admitted inverse is 200 rows / 10 seconds and classification limit 8, using
the current capable artifact. After an inverse, reconcile these source values
before another config-train apply so it cannot silently reapply the forward
settings. Do not invoke an older integration-only canary packet merely because
its controller still expects 200/10; that path needs its own current admission.

The margin-40 lead owns the matched safety and cost readout after the relevant
old revisions cease. Follow the existing
[serving sweep contract](../../batch-pipeline-serving.md) and
[finish classification runbook](../../runbooks/projection-finish-async-skip.md).
No runtime defaults, controller logic or enforcement flags change here.
