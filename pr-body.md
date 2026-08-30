## What changed and why

Registry-only lifecycle change: adds one failure class, `FC-decoded-outcome-discarded-before-canonical-record`. No product code.

The class names a shape found four times in the desktop voice lane during a root-cause investigation of production push-to-talk quality (`omi-knowledge-base` → `projects/ptt-improvement/`): a boundary decodes an outcome signal, the signal is then dropped, and the record downstream consumers treat as canonical asserts an outcome nothing witnessed.

The four instances, all independently verified against `origin/main`:

- `persistTurnDirectlyToKernel` accepted `interrupted: Bool` and never read it, so cut-off voice turns were journaled as completed answers.
- `ToolResponse.isError` was decoded off the wire and read by nothing on the chat or voice execution path, so failed backend writes reached the model as successes.
- A realtime tool authorized without a transcript ran from a synthetic instruction that was then journaled as the user's own words.
- Committed PTT turns reported `peak`/`rms`/`turnAudioSeconds` of literal `0` while rejected turns reported real values, putting admitted and rejected audio on different scales.

What makes it a class rather than four bugs is the shared prevention: make the record's outcome a total function of the decoded signal instead of a value callers supply — require the signal in the writing funnel's signature so omitting it cannot compile, derive the stored status inside that funnel, and represent unknown explicitly rather than substituting a confident default.

`evidence_prs` is `[]` and `canonical_prevention_artifact` names the two files that will host the guard surface — the persist funnel whose signature makes the signal mandatory, and the lifecycle recorder that derives its own verdict — and the instance-fix PR may extend that list, which the protocol permits. Split per the failure-class protocol, which forbids an instance-fix PR from introducing a definition.

## Product invariants affected

None. No product code, tests, or workflows change.

## How it was verified

- `./scripts/failure-class validate --pr-body-file pr-body.md --base origin/main --head HEAD` — passes.
- `make preflight` — passes.

## Tests

None. The failure-class CLI's own hermetic tests are the schema authority and are unchanged.

## Failure class (fixes)

Failure-Class: none
