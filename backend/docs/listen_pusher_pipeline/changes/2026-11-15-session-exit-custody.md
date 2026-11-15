# 2026-11-15 — Listen session exit custody: one fault line per exit step

## What changed

Every bookkeeping step on the listen session's exit path now owns its
fault through one closed step table (`routers/listen/session_exit.py`).
Before this change, most exit steps ran bare inside `try/finally`
blocks whose `finally` ran but never contained: a fault on the final
usage flush, the lane meter, the demand tail publish, the onboarding or
language summaries, the multi-channel tail, the speaker ordinals, the
idle arm or the buffer clears aborted every later exit step and escaped
the supervision envelope. On the deployed build each escape surfaced as
uvicorn's `Exception in ASGI application` traceback at the
`websockets_impl.py` `run_asgi` frame — the prod error sensor's top
`backend-listen` family. The observed arms (2026-11-14) walk
`_teardown_components -> _flush_usage -> persistence.call` and
`conversations.prepare -> create_new_in_progress_conversation` straight
out to that frame.

## The contract

- `SESSION_EXIT_STEPS` is the closed step table; each row names its
  exit-line outcome token, phase and attempt budget. The final usage
  flush replays (3 attempts) on the teardown family's doubling ladder
  with every wait raised to the stamped storm window (clamped at the
  store damper's 4.0s cap); every other row is report-only.
- A closed contention loss books WARNING — losing the race is not a
  fault; the recovery lane, the session census and the client reconnect
  own the unit. Any other fault keeps ERROR. Lines carry the fault
  class, the losing store label, the sanitized attempt, the armed storm
  window and a static `site=` file:line — never a uid, segment or
  conversation token, and never the exception message.
- Because every row owns its fault, the teardown envelope cannot raise
  an `Exception` past itself: the admission guard's
  `listen session failed before supervision` label becomes truthful,
  and the in-body fault line keeps its text while gaining a static
  `site=` field.
- The pre-session cohort warm in the deletion fence is bounded the same
  way: a rollout-store fault starts the session with cold cohorts
  instead of crashing the ASGI callable.

## Wire / payload impact

None. This is exit-path bookkeeping only: the same close frames, the
same publish calls, the same usage metering. The speaker-ordinal
handoff into the idle arm is preserved (a fault on the ordinal ledger
records the idle arm with no ordinals, exactly the value the
pre-session exits already pass).

## Rollout / rollback

Ships with the backend image; no flag, no migration. Revert is a plain
code revert — the table adds no durable state.

Failure-Class: FC-listen-session-exit-custody-faults-escape-as-asgi-crashes
