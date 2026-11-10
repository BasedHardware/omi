# Worker-flight salvage: an orchestration escape must not void the flight

`event=batch_quarantined reason=worker_failed attempt=5 recovery=held stage=unknown
worker_reason=unclassified` is the ladder's anonymous terminal quarantine. It burned
because the worker's stage pipeline only wraps per-item faults in the typed `fail()`
closure. The orchestration between those boundaries — the left-context bookkeeping
loops, the window packing pass, the decode generator's route recording, and the
observability hooks inside the typed `fail()` closure itself — runs unwrapped, so one
exception there used to propagate out of
`process_batch` entirely. The pump received no results for any unit in the flight:
units that had already settled lost their outcomes and were re-leased for duplicate
GPU work, admission holds were re-leased into ordinary worker-failure attempts, and
every affected unit walked the whole bounded retry ladder evidence-less. With no
diagnosis ever preserved on the job, each unit's ceiling attempt collapsed to the
historical anonymous shape. Because an escape inside a flight is deterministic for the
units it touches, the same units re-crashed on every attempt until the attempt ceiling
quarantined them blind.

Failure-Class: FC-worker-flight-escape-voids-settled-and-held-units-into-anonymous-quarantine

## The stage cursor

`_process` keeps a per-flight `stage_cursor`: for every unit, the deepest typed stage
boundary whose evidence the unit has completed. The cursor advances only at the four
typed boundaries and never inside an exception handler:

- `fetch_decode` — written after a unit decodes and passes the decoded-extent check.
- `vad_windows` — written after the unit's VAD verdict, window cut and language
  barrier decisions have all resolved; silent units (no windows) keep this token.
- `word_clocks` — written once every window cut for the unit has validated its word
  clocks; windows pack across microbatches, so the boundary completes only when the
  unit's own clip count from the shapes record has validated. The left-context prefix
  window is the predecessor's audio and never advances a unit's own threshold.
- `assemble_words` — written when the unit joins the assembly list.

A unit the escape reached before its entry boundary completed has no cursor entry; the
salvage attributes it to `fetch_decode`, the boundary it was entering. No unit of a
salvaged flight is left without a closed stage token.

## The salvage rules

The pipeline `try` gained one `except Exception` arm below a `except FatalGpuError:
raise` arm. Cancellation and other `BaseException` subclasses still propagate; salvage
never swallows them. The rules, in order:

1. A CUDA-fatal escape converts to `FatalGpuError` above the salvage, sets the
   unavailable flag, and restarts the GPU chain exactly as before. The salvage
   rechannels only what the flight reports, never a transition a typed boundary did
   not make.
2. Settled outcomes stand: every emitted result in the results list and every unit
   with a pending persist future is never re-emitted. A unit whose typed `fail()`
   handler itself died mid-way — a raise from the fault-channel hooks inside the
   handler — has neither a result nor a completed diagnosis; the salvage treats it as
   unsettled and re-emits it exactly once, without a second `counts['failed']`
   increment and without a second `on_failure` callback.
3. Held units keep their admission holds: each re-emerges as `HeldWork` carrying its
   recorded hold reason, so a contained escape never re-walks a policy hold as an
   ordinary failure.
4. Each unsettled unit leaves as an ordinary retryable `FailedWork` whose
   `worker_failure` evidence is `{'stage': <cursor>, 'reason': 'unknown'}`. The
   evidence closes at the unit's real position; the reason is the closed `unknown`
   token, never the escape's exception text.
5. The salvage preserves every hook the typed boundary runs: `counts['failed']`
   increments once per salvaged unit, the `on_failure` callback fires with the escape's
   class name (a raising callback warns and never breaks the salvage), and the fault
   channel receives one `event=batch_worker_failed` record per salvaged unit with the
   cursor stage, the `unknown` reason and the static `site=` file:line field. Shadow
   units stay on the shadow channel.
6. The escape itself is logged once per contained flight on the shared
   `event=batch_chain` channel as `outcome=salvaged`, with the closed exception type
   and the salvaged/settled counts. The pump's void line
   (`event=batch_chain outcome=retry`) never fires for a contained group, because the
   group no longer raises.

## What the terminal record gains

Before the salvage, an escaping flight gave the pump an empty result map; every unit's
ladder ended at a quarantine whose diagnosis was empty, and the terminal line read
`stage=unknown worker_reason=unclassified`. After the salvage, the same flight returns
per-unit outcomes, the ladder runs once with evidence riding the ordinary
`worker_failure_evidence` slot, and the eventual terminal record names the real stage:
`stage=vad_windows worker_reason=unknown`, `stage=word_clocks worker_reason=unknown`,
and so on. The anonymous bucket drains into attributed per-stage records an operator
can act on.

Salvaged evidence never demotes: the language-guard redrive predicate, the empty-ladder
recovery predicate and the terminal validation-disposition predicate each require a
typed reason token, and `unknown` is not one. An escape stays booked as the fault it
is, on the ERROR channel, at every logging site.

## What did not change

- The bounded retry ladder, lease fencing, the attempt ceiling, quarantine custody and
  the fenced recovery handoffs are untouched. Salvage evidence rides the ordinary
  evidence slot, which never decides a transition; an ordinary failure still defers.
- Fatal GPU state still restarts the whole chain without an attempt charge.
- Escape sites remain bugs worth fixing. The salvage bounds the blast radius and names
  the fault; it does not retry a poisoned flight inside the same GPU chain.
- The pump's `event=batch_chain outcome=retry` line remains the report for faults that
  still escape a group at settle time; it is simply no longer reachable for an
  orchestration escape from `_process`.

## What salvage never does

- It never captures an exception message, traceback text or any payload into durable
  evidence; the closed vocabularies and the static `site=` field are the whole record.
- It never fabricates a persist outcome: a unit the escape caught before its upload
  settled re-runs on the ladder rather than inventing a stored artifact.
- It never marks the worker unavailable: only the CUDA-fatal conversion does that.
- It never advances a cursor inside an exception handler: the cursor records only
  what a typed boundary actually completed.
