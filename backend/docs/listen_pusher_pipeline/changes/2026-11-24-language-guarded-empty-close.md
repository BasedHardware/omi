# Two empty recognizers can close a language-guarded held unit

A language-guarded unit (`worker_failure.reason=unsupported_language`) never
reaches Parakeet. Recovery asks Modulate, then Soniox once if the unit is at
most 60 seconds long. Words from either recover the unit, and two validated
empty answers with less than one VAD frame of speech settle as silence. Every
other outcome stays `failed_held`, including two validated empty answers on a
unit whose VAD found speech. Nothing automatic changes that hold: the nightly
requeue returns the unit to the GPU worker, which refuses the same language
again, and the recovery intent is already spent. The upload that carried the
unit keeps reading `processing` with `reason_code: batch_unit_held`, so the
phone keeps every file of that upload and polls again every five minutes.

`BATCH_PIPELINE_LANGUAGE_GUARDED_EMPTY_CLOSE_ENABLED` (default off) lets that
one case settle. When Modulate and Soniox both return a validated empty answer
for a guarded unit, it settles `no_recoverable_speech` with both recognizer
receipts and the existing language-guard evidence shape. Projection, the upload
status and the conversation list already treat that outcome as an empty
result, so no client change is needed.

It is separate from `BATCH_PIPELINE_TWO_RECOGNIZER_EMPTY_CLOSE_ENABLED`, which
covers unguarded units only, so each population can be enabled and read on its
own. Neither switch opens the other's case.

The settlement fence (`held_result_allowed`) accepts a guarded
`no_recoverable_speech` result only while the switch is on and the job holds
both validated empty receipts. That is the evidence the operator terminal
disposition already requires for a guarded unit. A result persisted while the
switch was on and settled after it was turned off is refused and the unit
stays held.

Unchanged: a provider error, a missing receipt or words from either recognizer
keep the unit held. A guarded unit above the 60-second independent ceiling is
not asked of Soniox, so one empty answer never closes it. The sub-threshold
silence rule, the case of zero strict-VAD spans with earlier measured speech,
provider calls, admission, allowance, consent and privacy rules are untouched.
Units that are already `failed_held` are not revisited.

The [empty-ASR contract](../../listen_pusher_pipeline.mdx) and the
[language recovery runbook](../../runbooks/batch-language-recovery.md) document
the switch. Rollback: unset it on the CPU recovery roles; later settlements
stay held and completed results stay completed.

Production readback before enabling (2026-11-24, job records and batch worker
logs over the last seven days):

- The worker refuses about 0.3% of units as `unsupported_language` with speech
  present. 7.6% of those end held after two validated empty answers.
- Such units are about 0.02% of batch units and about 0.01% of batch audio.
  They are 18% of all held units, and 62% of them have been held for more than
  seven days.
- About 3% of the accounts with recording activity in the week have at least
  one. This share is approximate: the account count and the activity count
  come from different systems.
- Our detectors measured speech in 7% of their audio. Between 82% and 89% of
  these units carry under two seconds of measured speech; 4% to 6% carry five
  seconds or more.
- Of all language-guarded held units, 72% have two empty answers, 10% are held
  on a Soniox failure and 4% were never sent to Soniox. The switch reaches
  only the first group.

Readout: `omi_batch_pipeline_recovery_recognizer_outcomes_total` already
carries `language_guarded`. With the switch off the case reads
`language_guarded="true",modulate="empty",soniox="empty",result="failed_held"`;
with it on the same labels read `result="no_recoverable_speech"`.
`soniox="refused"` on a guarded unit counts the units above the ceiling that
this switch does not reach. No new metric family and no deploy change.
