# Sampled audit of declared-language batch audio

Contract: [batch speech language quality](../../batch-language-quality.md).

**Why.** Batch intake sends a unit with a declared supported language (usually the conversation's
`en` pin, which is the app language) to Parakeet without listening to it. PR #26431 stopped
trusting the pin for users whose live speech shows an unsupported language. Nothing measured how
much pinned audio from everyone else is Mandarin, Hindi or another language Parakeet renders as
Latin phonetics. That includes users who never use live transcription, so they have no profile.

**Change.** `batch_language.resolve_language`, on the batch surface with a declared supported
language and serving intake's guard, hands the unit to `declared_language_audit.maybe_audit`.
A stable 2% sample:
- runs on the bounded `declared_language_audit` executor;
- re-runs serving's privacy authorization and consent check, then a read-only funding check that records no admission telemetry (unfunded and BYOK-only owners skip as `not_funded`);
- skips probes that are mostly silence;
- is classified on its first 30 s by the self-hosted gate when configured, else by the Modulate
  language-ID probe (at most 60 per process per hour);
- is counted in `omi_batch_pipeline_declared_language_audit_total`.

The returned decision is unchanged: always `declared`.

**Production today.** The self-hosted gate is not configured on the batch hosts
(`STT_GPU_FLEET_OFF=true`, `HOSTED_LID_API_URL` empty), so the vendor probe classifies.

**Cost and reads.**
- Vendor: 30 s per sample at $0.01 per sample-hour, capped at 60 per process per hour, so at most
  $0.005/h per process. At today's volume, about 12k samples/day is about $1/day.
- Firestore: the fresh authorization costs a few reads per sample, under 60k reads/day.

**Privacy.** Modulate already serves live STT and language-ID for Omi audio. Each sample passes
serving's own privacy, consent and funding check first. No audio is stored, and no user identifier
or transcript is recorded.

**Rollback.** `BATCH_DECLARED_LANGUAGE_AUDIT_ENABLED=false`.

**Readback.** The leak share by declared language, all rows and confident-only, read from GMP 24 h
after serving and posted on SCA-4940.

Evidence: `tests/unit/test_declared_language_audit.py`.
