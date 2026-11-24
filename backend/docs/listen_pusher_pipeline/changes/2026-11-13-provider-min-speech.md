# Provider-route units under 2 s of speech skip the vendor (2026-11-13)

## Why

David, 2026-11-13: process user recordings economically; skipping very short ones is fine.

A provider-route batch unit is billed for its whole capture span — about 31 s — even when strict VAD
found a second of speech. On 2026-11-13 a production sample (ro-prod, metadata only) of 2,966 settled
`result_ready` provider units showed:

- 1,345 had no speech and already skipped the vendor;
- of the remaining billed audio, units with **under 2 s** of measured speech were **26%** (20% under 1 s);
- provider STT runs at about $155–190/day, so those units cost about **$40–50/day** plus the same share
  of the provider backlog still to drain.

Vendors often return nothing for these units anyway: most 11-02 `empty_asr` quarantines were exactly
these sub-2 s units, so the paid call bought a word or two at most.

Contract: [batch worker GPU skips](../../listen_pusher_pipeline.mdx#batch-worker-gpu-skips-speech-only-diarization-short-single-speaker)
is the analogous "short speech does not justify paid work" rule on the GPU route;
[funded transcription cap](../../listen_pusher_pipeline.mdx#funded-transcription-cap) owns the
allowance ordering this change leaves untouched (see below). Env var and default are catalogued in
`backend/docs/feature-flag-registry.md`; no wire or payload field changes.

## What changed

`BATCH_VENDOR_MIN_SPEECH_SECONDS` (default `2`, range `0`–`10`; malformed or out-of-range keeps `2`)
sets the strict-VAD speech below which a provider-route unit is answered as local silence with **no
vendor call**. `0` restores the earlier rule — only a unit with no speech spans at all skipped the
vendor.

- `config/batch_pipeline_vendor_failover.py`: `min_speech_seconds()`.
- `utils/batch_pipeline/provider_stt.py`: `_skips_vendor(inspected)` is decided once in `_prepare`,
  carried on `_Call.skip_vendor`, and used by the health arm, the intent's `vendor_skipped`,
  `_call_sync` and `_call_async`. The skip reuses the existing local-silence path end to end:
  `silence_payload`, outcome `silence`, `audio_seconds=0`, normal settle and merge.
- The intent keeps `measured_vad_speech_seconds > 0` beside `vendor_skipped: true`, so a short-speech
  skip stays distinguishable from true silence.
- New counter `omi_batch_pipeline_vendor_short_speech_skipped_audio_seconds_total{provider}` counts the
  unbilled audio on all three settle paths: the direct call, the abandoned-intent silence reconcile,
  and the saved-result reconcile.
- The flag registry, `flag_budget.json` and the rendered registry doc are updated.

Merge, projection, custody, privacy fences and the settle protocol are unchanged. No new state.

## Intentional content loss

Up to 2 s of strict-VAD speech per unit is not transcribed: a word or two at most in a ~31 s span.
Units at or above 2.0 s still call the vendor. The measurement is the same strict-VAD span set the
pipeline already used to skip pure silence and to record held speech.

## Rollback

Set `BATCH_VENDOR_MIN_SPEECH_SECONDS=0` on `backend-integration` (where the provider stage serves).
New units fall back to the no-spans-only rule. Units already skipped keep their silence result — the
result is a normal committed silence, and nothing needs undoing.

## What to watch

- `omi_batch_pipeline_vendor_short_speech_skipped_audio_seconds_total` ≈ 26% of billed provider audio.
- `omi_batch_pipeline_vendor_attempt_audio_seconds_total{outcome="ok"}` falls by that share.
- Silence share of provider results rises from about 43% to about 55% of units.
- Must stay flat: provider settle rate and merge commit rate.

## Not in this change

- The GPU route: GPU cost is fixed node time (mostly idle), so skipping there saves nothing.
- Age-based skipping of old backlog: measured separately and reported to David.
- The provider merge fix (#25187, separate owner); this branch is rebased on it.
- Moving VAD ahead of allowance in `_prepare`. A unit held for allowance is deferred before the skip
  applies; that ordering already applies to true silence and is unchanged here.
