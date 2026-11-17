# Preserve the admitted integration sweep settings

The integration ops config now carries a 100-row serving sweep every 20 seconds
and a finish classification page limit of 16. These are the values admitted by
the margin-40 lead and applied by Release on 2026-11-16. Declaring them in the
ops config keeps subsequent config trains from treating them as unexplained
live-only settings. The staging integration service mirrors the keys under the
existing prod/staging parity contract.
Until a separately authorized staging config train applies the keys, staging
source/live or staging/prod drift reports may still show them as missing. This
source merge is not proof that staging already carries the values.
The staging deploy path replaces the complete environment from its runtime
manifest and does not merge this ops file. A subsequent staging deploy therefore
drops these ops-only keys and restores code defaults (100/20/classification 8)
until a later staging config train reapplies them. This source carry does not
change that deployment path or authorize staging classification 16.

This changes config source only. A merge does not dispatch a config train,
create a revision, establish a clean guard window or prove monetary savings.
The privacy qualification map is separate and is not changed by this carry.
Normal privacy, custody, funding and provider checks remain in force.

Release retains runtime rollback and must serialize it with config trains.
The admitted inverse is 200 rows / 10 seconds and classification limit 8, using
the current capable artifact. After an inverse, reconcile these source values
before another config-train apply so it cannot silently reapply the forward
settings. The `RESTORED_DEFAULTS` constants in
`backend/scripts/runtime_env_canary_ops.py` and
`backend/scripts/integration_canary_controller.py` intentionally retain the old
200/10 inverse. They must not be equated with the 100/20 forward values in the
ops file. Do not invoke that integration-only canary packet without its own
current admission.

Use `backend/scripts/ops/drift_check.py` for the source-aware ops comparison.
The separate manifest-only `check_cloud_run_env_drift.py` report may still list
these ops-only keys as extra live bindings; this carry does not add a static
allowlist or duplicate their ownership in the generated runtime manifest.

The margin-40 lead owns the matched safety and cost readout after the relevant
old revisions cease. Follow the existing
[serving sweep contract](../../batch-pipeline-serving.md) and
[finish classification runbook](../../runbooks/projection-finish-async-skip.md).
No runtime defaults, controller logic or enforcement flags change here.
