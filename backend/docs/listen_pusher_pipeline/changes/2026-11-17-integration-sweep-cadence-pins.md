# Persist integration sweep cadence and finish classification values

SCA-2283 / David's 2026-11-16 order. The release owner applied these values
to prod backend-integration at 20:54Z; this source change keeps the next deploy
from restoring a different runtime configuration.

Only prod backend-integration declares:

- `BATCH_PIPELINE_SERVING_SWEEP_PAGE_ROWS=100`
- `BATCH_PIPELINE_SERVING_TICK_SECONDS=20`
- `BATCH_PROJECTION_FINISH_CLASSIFY_PAGE_LIMIT=16`

Inverse values are 200 / 10 / 8 respectively. Regenerate the runtime manifest
after changing the overlay and release through the ordinary owner-controlled
lane. There is no deployment in this PR and no saving is claimed.

The [pipeline contract](../../listen_pusher_pipeline.mdx) still owns projection
ordering, privacy, custody and retention. Other services and all
`FIRESTORE_READ_LEVERS` literals remain unchanged. Validation uses runtime
compose freshness, read-lever manifest freshness, the existing renderer and
hermetic pre-deploy contracts, and the normal pre-push checks.
