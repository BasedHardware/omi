# Malformed staged input clock cannot disable retention protection

Review-desk #25010 at `bba96faece6b` is confirmed: a present malformed
`audio_staged_at` previously excluded a held row from both expiry streams and
its staging-age sample. It now falls back to the older admission clock. An
enqueue stream row is excluded only when its replacement clock is valid;
the replacement stream excludes malformed clocks. Query shapes, indexes,
page limits, cadence, flags and the 30-day privacy ceiling stay intact.

The existing exporter counts malformed clock observations with
`omi_batch_staged_input_clock_invalid_total`. A valid admission fallback remains
visible to the 21-day warning and day-29 terminal. Neither usable clock means
no input-expiring terminal and an invalid-clock observation. An age sample
observing such a row marks its staging-age leg incomplete through the existing
scan-blind warning. Counts describe
observations in completed bounded age samples and held pages, not unique rows
or a fleet census. The existing name page also counts absent clocks, which
age-ordered queries cannot discover;
failed scans use the existing sample-error/staleness path.

Contract: [held staging input expiry](../../listen_pusher_pipeline.mdx#held-staging-input-expiry).
Tests cover malformed values across both held legs, exactly one urgency
candidate per row, age/counter export, two invalid clocks and valid restages.
No audio, Firestore, GCS, production config or deployment write was performed.
