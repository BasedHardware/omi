# Two empty recognizers can close a held batch unit

Under the empty-ASR safety net, a unit whose VAD found speech stays
`failed_held` when recovery returns no words, even after both recovery
recognizers answered. Nothing automatic follows that hold. The upload that
carried the unit keeps reading `processing` with `reason_code: batch_unit_held`,
so the phone keeps every file of that upload and polls again every five minutes.

`BATCH_PIPELINE_TWO_RECOGNIZER_EMPTY_CLOSE_ENABLED` (default off) lets that one
case settle. When Modulate and the second recovery provider both return a
validated empty answer, the unit settles `no_recoverable_speech` with both
recognizer receipts, through the same payload, evidence and settlement fences
that already apply when the safety net is off. Projection, the upload status
and the conversation list already treat that outcome as an empty result, so no
client change is needed.

Unchanged: a provider error, a refusal, a missing receipt or words from either
recognizer keep the unit held. Language-guarded units keep their own
sub-threshold rule. The single-recognizer padded-empty path still needs the
safety net off. No provider call, admission, allowance, consent or privacy
rule changes. Units that are already `failed_held` are not revisited.

The [empty-ASR contract](../../listen_pusher_pipeline.mdx) documents the switch.
Rollback: unset it on the CPU recovery roles; later settlements stay held and
completed results stay completed.

Production readback before enabling (2026-11-24, six hours of recovery logs):
406 held settlements with `reason=empty_asr`, about 0.2% of units admitted in
the same period. Of the sampled second-provider calls in that window, 41
returned empty, 24 returned words and 7 failed. The logs do not separate
language-guarded units, so the share this switch would close is at most that
figure.

Readout: `omi_batch_pipeline_recovery_recognizer_outcomes_total` (behind the
existing `BATCH_PIPELINE_CORRECTNESS_METRICS_ENABLED`, no new switch) counts
every committed recovery settlement by Modulate's answer, Soniox's answer, the
held speech our detectors measured (`none`, `under_2s`, `2s_or_more`,
`unmeasured`), the language guard and the result. Both the switch on and off
report the two-empty case: `modulate="empty",soniox="empty"` with
`result="failed_held"` before and `result="no_recoverable_speech"` after.
The recovery role's scrape profile already keeps `omi_batch_pipeline_.*`, so
no deploy change is needed for it to be readable. Until now Modulate's
answer had no counter, and `omi_batch_recovery_second_provider_total` is not
in that keep list.
