# Legacy sync multilingual audio is transcribed by Soniox first (SCA-4917)

Contract: [Soniox first for legacy sync multilingual audio](../../listen_pusher_pipeline.mdx#soniox-first-for-legacy-sync-multilingual-audio).

**Why.** Legacy sync hands Velma every file its language check does not send to Parakeet:
unknown or code-switched audio, and languages Parakeet cannot transcribe. On the owner's
code-switched Mandarin/English evening (SCA-4810 lab, 2026-11-26), Velma returned English or no
Chinese on every blind-labelled clip (0/9 picks); Soniox was picked 5/9 and scored best on
automatic agreement over 293 VAD units. Public per-language tables (FLEURS) put Soniox at or near
the top on Mandarin, Japanese, Korean, Hindi and Arabic; Velma publishes English-only accuracy.

**Change.** Inside a legacy sync attempt, a Modulate-selected file with language `multi` (or a
non-European language Soniox accepts as a hint) runs Soniox first. Any Soniox failure falls back
to Velma on the same audio. Legacy sync passes `multi` for every user not in single-language mode, so in practice every
Velma-bound file goes to Soniox first, including low-confidence English (where code-switched speech
lands); `en` and `es`/`fr`/`de`/`it`/`pt`/`nl` keep Velma first only when that language reaches the
provider (single-language users). Voice
messages, push-to-talk, shadow scoring, batch recovery, held-piece recovery and prompt
verification are unchanged. Files over 300 s stay on Velma (Soniox's sync client has a 120 s
deadline), and each process runs at most 8 Soniox-first calls at once; a full process uses Velma
without waiting. This bounds the create rate against Soniox's 2,000 stored-transcription cap.

**Cost.** List rate card (`config/rate_card_v2.json`): Soniox 0.12, Velma 0.06 USD per audio hour.
Production Velma batch audio was 1,056 h in the 24 h to 2026-11-27T02:38Z (sum of 10-minute
increases of `omi_prerecorded_vendor_audio_seconds_total{provider=modulate,endpoint=stt,outcome=ok}`),
which also includes batch-pipeline vendor overflow that this change does not touch. The upper
bound is therefore about +$63/day at the rate card if every such hour moved; the readback measures
the real share.

**Rollback.** `STT_PRERECORDED_SONIOX_MULTILINGUAL_ENABLED=false`.

**Readback.** After serving: `omi_prerecorded_vendor_audio_seconds_total{provider=soniox,endpoint=stt}`
per day (served and error), the `outcome=fallback` log rate by `kind`, and, for the owner account,
that a code-switched conversation's legacy segments come from `stt-async-v6` with Chinese text.

Evidence: `tests/unit/test_prerecorded_soniox_multilingual.py`, plus the existing pre-recorded
failover and Modulate suites.
