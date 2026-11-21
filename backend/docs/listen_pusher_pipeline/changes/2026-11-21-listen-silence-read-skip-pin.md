# Listen silence-read skip pin

[Listen and pusher pipeline contract](../../listen_pusher_pipeline.mdx) · [Silence-read skip runbook](../../runbooks/batch-silence-read-skip.md)

[PR #25994](https://github.com/BasedHardware/omi/pull/25994) pins
`BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED=false` for production backend-listen in
its Helm values and the `gke.backend-listen` production overlay. This preserves
the live value during the SCA-3516 image roll. The pin applies only to listen.
Release's installed dry run at `90139ab691b8` reported nine authorized drift rows
and three reviewed private references.

Keep the listen pin until the sync privacy-read increase in SCA-3610 is explained.
Enable the skip on listen as a separately approved, one-key activation on SCA-3516.
Compare against the pre-activation baseline for T2 lost speech, custody checks,
listen 5xx, and reconnect rate. Post the guard results and serving readback on
SCA-3516.

For a regression after the listen image roll, use `mode=rollback` to restore the
previous Helm revision. To undo a later skip activation, restore `false` in both
listen config sites and verify the serving value and guard recovery. Reverting
#25994 would render `true` for listen, so defer the image roll if the pin is
reverted.
