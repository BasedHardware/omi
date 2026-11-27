# Sampled audit of declared-language batch audio

Contract: [batch speech language quality](../../batch-language-quality.md).

**Why.** Batch intake sends a unit with a declared supported language (usually the conversation's
`en` pin, which is the app language) to Parakeet without listening to it. PR #26431 stopped
trusting the pin for users whose live speech shows an unsupported language. Nothing measured how
much pinned audio from everyone else is Mandarin, Hindi or another language Parakeet renders as
Latin phonetics. That includes users who never use live transcription, so they have no profile.

**Change.** `batch_language.resolve_language`, on the batch surface with a declared supported
language, hands the unit's audio to `declared_language_audit.maybe_audit`. A stable 2% hash
sample has its first 30 s sent to the self-hosted language gate on a 2-worker background pool.
At most 4 probes wait at once, and a full pool skips the sample. The verdict is counted in
`omi_batch_pipeline_declared_language_audit_total{declared, heard, heard_class, confident}`.
The returned decision is unchanged: always `declared`.

**Privacy and cost.** The probe goes only to our Parakeet service, which receives the same unit
for ASR. No vendor, no stored audio, no user identifier, no transcript. GPU cost is one `/v2/language`
call per sampled unit, about 0.14 calls/s at today's volume.

**Rollback.** `BATCH_DECLARED_LANGUAGE_AUDIT_ENABLED=false`.

**Readback.** The leak share by declared language is unsupported-and-confident over classified
rows, read from GMP 24 h after serving and posted on the issue.

Evidence: `tests/unit/test_declared_language_audit.py`.
