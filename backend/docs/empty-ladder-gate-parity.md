# Empty ladder gate parity: one closed disposition predicate for every rung

`event=batch_quarantined reason=worker_failed attempt=1 recovery=held
stage=assemble_words worker_reason=empty_asr` (x681/30m) and its
`no_owned_words` sibling burn on the empty ladder's decision boundaries, and
the ladder answers the same question — "does this empty unit ride the
recovery handoff?" — at two separate places in the GPU worker. The terminal
`RecoveryWork` selection at the assemble_words boundary and the post-retry
hold gate each carried a private copy of the same inline boolean
(`reason == 'empty_asr' and (recovery or safety) or reason in
{'empty_asr', 'no_owned_words'} and (disposition or safety)`). Two private
copies of one closed disposition is a drift class: a future edit to one copy
misroutes units between ladder rungs — held forever with raw custody, retried
blind on byte-identical audio, or terminally quarantined with the recovery
handoff the flags promised — and no suite compared the two boundaries
cell-by-cell across the flag matrix.

Failure-Class: FC-empty-ladder-gate-drift-misroutes-recovery-units-between-hold-retry-and-terminal-rungs

## What changed

- `config/batch_pipeline_empty_asr.py` owns `empty_ladder_handoff(reason, *,
  recovery_enabled, disposition_enabled, safety_enabled)`: the closed
  two-arm disposition as one pure predicate. Flags stay arguments — callers
  read them at the call boundary per the `config/` read-per-call rule — so
  the predicate itself stays environment-free and the full flag matrix is
  testable without environment surgery.
- The GPU worker's terminal `RecoveryWork` selection
  (`diarizer/batch_pipeline.py`, assemble_words fail boundary) and the
  post-retry hold gate (recovered-is-None custody decision) both call the
  shared predicate. The truth table is byte-identical to the inline
  expressions they replace; every existing suite passes unchanged.
- New parity suites pin the predicate's full flag×reason matrix, the
  worker-level behavior of both boundaries across the same matrix, the
  hold-gate custody outcomes (hold vs skipped-oversize settlement vs
  admission-refusal carry), and the scheduler evidence chain the handoff
  feeds (`worker_empty_evidence` tokens, terminal record naming).

## Contracts that do not change

- The safety net dominates: with `BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED`
  on (ship default), both family reasons always ride the handoff.
- Kill-switching the safety net restores the pre-safety answers, exactly as
  the inline expressions evaluated them: `empty_asr` rides when either
  `BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED` or
  `BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED` is on (the reason sits in
  both arms of the historical expression), while `no_owned_words` rides on
  the disposition flag alone. A unit that misses every arm still ends its
  chain through the worker-validation disposition (terminal, fenced
  recovery) or, with that switch off too, the ordinary bounded retry ladder.
- Non-family reasons (`word_clock`, `vad_bounds`, …) never ride the empty
  handoff at any flag combination; they keep their own terminal or ladder
  routes.
- `long_speech_handoff`, `worker_silence_disposition`,
  `worker_validation_disposition` and the cap-admission hold reasons keep
  their own flags and rungs; the shared predicate only replaces the two
  inline copies that were already identical.

## Runbook

- A unit whose terminal record says `worker_reason=empty_asr` must carry
  `job['worker_empty_evidence'] = {'padded_retry': <token>, 'version': 1}`
  with the token the worker's padded retry recorded (`empty`,
  `skipped_oversize`, `skipped_long_speech`). A quarantined empty unit
  without that evidence points at a scheduler write condition regression,
  not at the worker.
- If the terminal `RecoveryWork` population and the post-retry hold
  population ever disagree about the same flag combination, the shared
  predicate's matrix suite fails first; investigate the flag rollout before
  touching either boundary.
