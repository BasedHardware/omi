# Listen roll pin: silent-unit read skip stays off on listen

[Listen and pusher pipeline contract](../../listen_pusher_pipeline.mdx) ·
[batch silence runbook](../../runbooks/batch-silence-read-skip.md) · [PR #25994](https://github.com/BasedHardware/omi/pull/25994)

[PR #25959](https://github.com/BasedHardware/omi/pull/25959) turned `BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED` on in the
prod source for every role, listen included. Live listen runs it `false`. Release's listen gate refused main on that
tenth row. Shipping ruled on SCA-3516 that the listen roll keeps live behaviour and the skip does not ride it.

#25994 pins the key to `false` for listen at both render sites, the chart value and `gke.backend-listen` in the
prod overlay. Other roles are unchanged:
- `true` on backend, backend-integration, backend-sync and backend-sync-backfill;
- `false` on the projection pump.

The skip's only readers are in `utils/batch_pipeline/projection.py`. Listen serves shared backend routes, so the key
was pinned rather than declared inert.

Follow-up: turning the skip on for listen is its own one-key config change. It needs:
- a scoped go on SCA-3516;
- a guard on T2 lost speech, custody, listen 5xx and reconnect rate;
- a readback.

It also waits until the sync `privacy:read` per 2xx rise after #25959 (SCA-3610) is explained or rolled back.
Rollback of this pin: revert #25994. Listen then renders `true`, and the listen roll must not dispatch in that state.
