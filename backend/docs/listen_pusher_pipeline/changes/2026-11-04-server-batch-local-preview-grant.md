# Grant local preview before the server-batch-only early return

Server-batch-only listen sessions now run the existing local-preview admission
before returning from STT initialization, so eligible phones receive the grant
in `ready` and `mobile_batch_admission`. Refused declarers remain eligible for
visible restore: exclusion checks the granted `local_preview_batch` state rather
than the request declaration. Existing cohort, dwell and safety gates still apply.

The no-engine fallback remains one-way: a revoked grant cannot be re-admitted,
and owned batch captures retain the visible-only restore path. Batch ownership,
cloud-live suppression and existing flag defaults are unchanged.

Regression coverage exercises grants and refusals, renewal, visible dwell,
provider audio delivery and transcript callbacks alongside no-engine revocation.
See the [listen contract](../../listen_pusher_pipeline.mdx) and
[PR #24508](https://github.com/BasedHardware/omi/pull/24508).
