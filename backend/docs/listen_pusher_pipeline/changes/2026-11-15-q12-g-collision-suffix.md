# Preserve colliding phone WAL uploads

Released clients retain same-time audio under `_<timestamp>_uN.bin`. Parse
the timestamp before a single ASCII `u` plus decimal digits, through the same
capture-clock checks. Malformed suffixes and implausible future clocks still
fail with the existing typed refusal.

Remove request-time filename canonicalization: original names and bytes must
reach staging, manifest matching and basename-bound content identity unchanged.
Decoded WAVs and estimated-clock runs retain the collision suffix. Same-time
siblings therefore remain distinct through staging and batch capture decode.
No audio custody rule changes.

The [sync contract](../../listen_pusher_pipeline.mdx) defines the default-on
`SYNC_COLLISION_SUFFIX_ENABLED` kill switch. Rollback sets it off for new
admissions; internal reads continue draining already staged work. Tests cover
suffix grammar, early/future policy, separate storage/content keys, raw manifest
names, batch decoding and coverage derivatives. Production behavior and phone
retry timing are not verified by these hermetic tests.
