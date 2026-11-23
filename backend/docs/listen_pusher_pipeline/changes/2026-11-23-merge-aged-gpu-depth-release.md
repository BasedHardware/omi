# Aged GPU catch-up release at the merge depth cap

When projection stopped advancing, GPU catch-up rows at the merge depth cap
could remain pending indefinitely. The ordered merge now permits one GPU-route
catch-up row whose ready age is at least six hours to pass the cap. Legacy rows
without `ready_at` use `enqueued_at`, and the metrics distinguish those clocks.
Provider rows and recovered-release rows remain excluded.

The release is guarded by the default-on
`BATCH_PIPELINE_MERGE_AGED_GPU_RELEASE_ENABLED` ops kill switch. Set it to
`false` to stop this release path while preserving the ordinary depth hold.
Each release writes a 60-second cooldown and the current projection watermark
atomically with the result. No second aged row for that owner may pass until
the projection watermark advances, so a stalled projection cannot accumulate
an unbounded aged-release backlog.

The refusal-age histogram now has bounded worker-release, namespace and
`age_source` labels. Successful aged releases increment
`omi_batch_pipeline_gpu_aged_releases_total` and observe
`omi_batch_pipeline_gpu_aged_release_age_seconds`.

Contract: `backend/docs/batch-pipeline-serving.md`, “Fresh-first merge and GPU
priority”. Regression coverage: `backend/tests/unit/test_batch_pipeline_merge_fresh_first.py`.
