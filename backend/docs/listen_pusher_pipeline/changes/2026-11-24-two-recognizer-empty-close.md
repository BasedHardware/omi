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
figure. After enabling, compare `event=batch_terminal_empty` with
`event=batch_recovery_failure reason=empty_asr` on the recovery role.
