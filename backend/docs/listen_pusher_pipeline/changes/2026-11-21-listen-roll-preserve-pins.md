# Listen roll pins: privacy writer, packing and backfill cap preserve live behaviour

[Listen and pusher pipeline contract](../../listen_pusher_pipeline.mdx)

backend-listen served image `44d0a4f` (18 Nov) while main's listen values would have switched three
behaviours on at the next roll (SCA-3516). The prod listen overlay and chart now pin each by effect:

- `BATCH_ACCOUNT_PRIVACY_WRITER_ENABLED=false`: `44d0a4f` has no account privacy writer; on a current
  image the kill switch defaults on. A first activation on listen is a custody decision (David).
- `BATCH_PIPELINE_PACKING_SAMPLE_RATE=0`: `44d0a4f` has no packing observation; 0 disables sampling.
- `UNLIMITED_V2_BACKFILL_HOURS_CAP_ENABLED=false`: `44d0a4f` runs the cap off. Listen admits sync
  backfill uploads too, so listen stays uncapped exactly as today while Cloud Run stays capped.

Rotation stays `off`; its 180/300-second bounds are read only when rotation is enabled.

Follow-up after the roll: turn the backfill cap on for listen (David 2026-11-18, support-packet
decision 13) in its own config change and remove the validator exception. Verify with the listen
roll's SERVING readback and the first-hour 5xx comparison on SCA-3516. Rollback: revert the PR.
