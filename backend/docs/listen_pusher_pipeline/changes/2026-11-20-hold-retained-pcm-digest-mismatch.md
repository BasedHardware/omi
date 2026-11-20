# Quarantine recovery holds repeatable retained PCM digest mismatches

A retry could decode the same retained bytes, fail the manifest's PCM digest check,
and return 500 indefinitely. Recovery now re-authorizes and reads only the
mismatched source once more, using the same manifest-pinned generation and digest.
If the confirmation matches, recovery continues. A second mismatch refuses the
input before transcription; the SHA-256 check is unchanged.

The existing privacy and content fences must accept the prepared recovery intent,
token, and audio binding before recovery commits `failed_held` with
`recovery.refusal.reason=retained_digest_changed`. A committed hold acknowledges
with HTTP 200 and emits the bounded fallback reason once. A duplicate delivery
acknowledges the existing hold without fetching audio again. No artifacts are
rewritten or deleted, and the missing-input and invalid-manifest paths are unchanged.

Recovery discovery and preparation exclude `failed_held`; held stock, expiry,
and ordered projection keep their existing classification. Nightly and intake-status
automatic redrive skip this refusal. Reviewed operator redrive remains available
under the existing eligibility and custody checks. The fallback counter measures
committed transitions; the batch quality gate reads durable held state.

Recovery now uses admission decoder semantics for gapped, unframed raw-live WAL,
including the custody manifest's frame table. Until this parity fix, operator
redrive could not recover that cohort because it repeated the same digest refusal.
An unchanged pinned pack now recovers while the generation and SHA-256 fences
remain in force; a repeated mismatch is still durably held.

On by default. Set `BATCH_PIPELINE_RETAINED_DIGEST_HOLD_ENABLED=false` to restore the
legacy single-read, retryable error for new mismatches. Rollback does not clear
existing holds, change retention, or rewrite manifests.

Contract: [retained digest refusal](../../../utils/batch_pipeline/CONTRACT.md#retained_digest_changed-refusal-recovery).
Evidence: [SCA-2974 / PR #25761](https://github.com/BasedHardware/omi/pull/25761),
`tests/unit/test_batch_pipeline_retained_digest_hold.py`, and
`tests/integration/test_recovery_custody_conformance.py`.
