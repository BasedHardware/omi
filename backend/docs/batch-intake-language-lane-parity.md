# Intake language lane parity: proven unservable speech never burns a GPU attempt

`event=batch_quarantined reason=worker_failed attempt=1 recovery=held
stage=vad_windows worker_reason=unsupported_language` (x185/30m) and its
diarizer-side twin `event=batch_worker_failed error_class=BatchValidationError
stage=vad_windows` (x188/30m) burn on units the GPU words engine can never
serve: intake froze a language outside Parakeet's set (a confidently detected
`ja`, or an unresolved probe frozen as `und`), admitted the unit to the
compute lane anyway, and the worker's language barrier then raised on the
first attempt. Every such unit paid a full decode, a strict-VAD pass, a
terminal quarantine transaction, and a fenced recovery sweep that re-ran the
same recognition the provider lane runs directly — three error-log lines per
wasted attempt, with fixed segment ids recurring window after window.

Failure-Class: FC-nonaffirmative-language-speech-admitted-to-gpu-barrier-as-guaranteed-failed-attempt

## What changed

- `config/batch_pipeline_language.py` owns the lane decision as two pure
  functions with a closed reason vocabulary. `intake_unit_language_plan`
  decides one unit's serving lane and frozen language from its CPU evidence;
  `intake_request_language_lane` flips the whole request when any unit plan
  demands it. Flags stay arguments, so the full matrix is testable without
  environment surgery.
- The decision rule: an affirmative (Parakeet-safe) decision always keeps the
  compute lane, whatever the strict inspector says. A confidently unsupported
  detected code with strict speech proof flips the lane. An unresolved
  decision (`und`) with strict speech proof flips the lane. Strict silence or
  an unavailable inspector keeps the compute lane — the worker's own strict
  inspector disposes silence with no ASR, and routing unproven speech to a
  paid recognizer would spend recognition on possible silence.
- The flip reuses the existing C8 provider lane verbatim: the request's
  policy and job route stamp `stt_route='provider'`,
  `provider_reason='unsupported_language'`, `provider_service='modulate'`,
  units stage with `requires_compute_admission=False`, and the provider stage
  owns funding, privacy and at-most-once recognition. The worker barrier and
  the guarded recovery vocabulary are untouched — `language_guarded` reads
  the same `unsupported_language` reason from a flipped job, so a flipped
  unit that ever quarantines still drains through the multilingual lane.
- The non-sampled intake decode loop now records each unit's plan before
  staging and finalizes compute admission after the whole bundle is known.
  Unit indexing, staging reservations, freeze lineage
  (`repair_languages`) and the sampled path are unchanged; the sampled path
  already refused unsafe speech whole and keeps doing so.

## What deliberately did not change

The worker barrier, its strict-inspector disposition and the empty ladder
keep today's behavior for any unit that still reaches the GPU — they remain
the safety net for unresolved answers and for rollback. Declared known-
unsupported languages still leave intake for legacy before any custody.
Named-unsupported detection on silent units still quarantines via the
barrier, because flipping silent audio would buy a paid recognizer a unit
with no speech. `record_partial` and native capture admission keep their own
admission paths. The guard kill switch (`STT_PRERECORDED_LANGUAGE_GUARD_ENABLED=false`)
restores freeze-as-input for unresolved answers wholesale.

## Test surface

`tests/unit/test_intake_language_lane_plan_matrix.py` pins the closed
vocabulary and the decision cells; `..._request_and_contract.py` pins the
request-level flip and the provider admission contract it reuses;
`..._full_vocabulary.py` walks every Parakeet-served code and a modulate-only
sample; `..._wiring.py` drives `accept_upload` end to end with synthetic
units and asserts the admitted job row; `test_worker_language_barrier_parity.py`
pins the barrier as the intact safety net; `test_barrier_quarantine_and_recovery_guard.py`
pins the scheduler-side terminal quarantine and the guarded recovery
vocabulary. The flip cells are red on the parent commit; the preserve cells
are green on both.

Failure-Class: FC-nonaffirmative-language-speech-admitted-to-gpu-barrier-as-guaranteed-failed-attempt
