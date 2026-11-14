# Long-speech empty units: the language skip answers the handoff boundary, not a private flag expression

Failure-Class: FC-long-speech-skip-flag-posture-drifts-from-the-handoff-boundary

## The production family this closes

The batch GPU worker owns one decision per speech-bearing empty unit whose
intake recorded a language Parakeet lacks (`unknown`, `multi`, or a raw
supported variant outside the model's set): skip the padded Parakeet retry
entirely and hand the unit straight to the fenced quarantine-recovery lane.
Repadding cannot make a fixed-language recognizer transcribe a language it
does not have — that is the documented TDT start-state mechanism the
empty ladder exists around — so the second forward is a guaranteed-doomed
paid GPU pass. The staging measurement that built the skip found 104 of 109
quarantined empties with at least 5 seconds of worker-VAD speech were
Vietnamese; every one of them paid the retry before recovery.

The skip armed through a private flag expression,
`empty_asr_recovery_enabled() or empty_asr_disposition_enabled()`, while the
boundary it hands into — the assemble_words custody decision that appends
`RecoveryWork` — answers `empty_ladder_handoff(...)`, the predicate whose
own docstring warns that "any drift between them misroutes a unit to the
wrong ladder rung (held forever, retried blind on byte-identical audio, or
terminally quarantined with the recovery handoff it was entitled to)".
Under today's shipping posture the two boundaries disagreed: the recovery
and disposition lanes are dark by default and the ship-on safety net
(`BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED`, default on) is what arms
the handoff. The private expression cannot see the safety net, so the skip
stayed disarmed exactly when the handoff it feeds was armed: every
long-speech empty unit ran the doomed padded forward and then landed in the
same `RecoveryWork` custody with the weaker `padded_retry: 'empty'`
evidence instead of the lane's dedicated
`{'padded_retry': 'skipped_long_speech', 'version': 1}` arm (the bounded
two-provider empty-evidence reuse). The misrouting is the exact class the
predicate extraction was extracted to kill — the third flag-reading site
that never joined it.

## What changed

- `long_speech_handoff` consults `empty_ladder_handoff` — the same
  predicate, flag arguments and safety-dominance the assemble_words
  boundary answers with — instead of its inline
  `(recovery_enabled or disposition_enabled)` expression
  (`diarizer/batch_pipeline.py`). The worker call site passes the
  boundary's own computed posture (`safety_enabled=safety`, which carries
  the words-provider gate), so the skip arms exactly when the custody it
  produces is accepted and can never drift again.
- The skip keeps every other gate byte for byte: the reason must be
  `empty_asr` (a `no_owned_words` unit may be in its language), the
  recorded language must be a string outside `PARAKEET_LANGUAGES`, the
  measured worker-VAD speech must clear `LONG_SPEECH_HANDOFF_SECONDS`, and
  the `BATCH_PIPELINE_LONG_SPEECH_HANDOFF_ENABLED` kill switch (unset is
  on) still dominates.
- With the safety net off, the predicate answer equals the old private
  expression for every flag combination — the ship-off drill posture is
  byte-identical. The only posture that moves is the shipping one: the
  skip arms, the doomed forward disappears, and the durable evidence
  upgrades to the lane's `skipped_long_speech` arm.

## What deliberately did not change

- The empty ladder's other boundaries, the recovery lane's evidence
  contracts, the scheduler's terminal demotion families and the
  awaiting-fenced-recovery warning are untouched. The rechannelled units
  already rode the `RecoveryWork` custody under the safety net; only the
  doomed GPU pass between the first empty verdict and that custody is
  removed.
- Units whose recorded language Parakeet supports (`language_class`
  supported and in `PARAKEET_LANGUAGES`) keep the padded retry — the
  retry can recover those. Units with no recorded intake language keep
  the retry when their class is unsupported, exactly as the docstring
  promised before this change.
- The barrier that refuses unsupported languages before any forward is
  untouched; the skip serves the units that pass it with an empty first
  pass (recorded supported variants outside the model's raw set, and the
  guard-switch drills).

## Rollback

Set `BATCH_PIPELINE_LONG_SPEECH_HANDOFF_ENABLED=false` to restore the
padded retry for every long-speech unit, or
`BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED=false` (the ship-off drill)
to restore the historical flag expression byte for byte — with the safety
net off the new predicate answer equals the old private expression at
every combination, so either switch returns today's behavior exactly.
