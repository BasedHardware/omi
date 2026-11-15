# Unsupported-language empty recovery

Unsupported-language provider attempts that exhaust candidates with a validated
empty answer enter quarantine `held`, allowing the serving sweep to run the
existing Modulate-then-one-Soniox recovery. Both route metadata and worker
failure metadata identify guarded jobs. Other terminal worker failures keep
their existing disposition.

The [independent recovery contract](../../listen_pusher_pipeline.mdx) now defaults
`BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED` on. Explicit deployment
overrides still apply. Setting it false restores immediate worker `failed_held`
and prevents new guarded Soniox calls. The hard 60-second bound, HELD_RECOVERY
admission, budget and privacy fences remain. Two empty recognizers retain
measured speech in terminal `failed_held`; there is no automatic retry loop.

Synthetic regressions cover zh worker settlement through the real recovery
sweep query, recovered Soniox words, both-empty termination, the kill switch,
the pending terminal path, and unchanged non-language-guarded empty settlement.
Deploy the backend serving/provider and recovery roles together. Previously
terminal units require a separately authorized operator redrive.
