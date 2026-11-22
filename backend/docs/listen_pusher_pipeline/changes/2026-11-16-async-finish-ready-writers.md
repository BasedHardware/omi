# Preserve async finish clocks on ready transitions (2026-11-16)

## Change and reason

SCA-2280 / [PR #25458](https://github.com/BasedHardware/omi/pull/25458)
corrects four writers that could put an async result back on the synchronous
finish page after its clock had been retired. Held-ready settlement, durable
sibling completion, privacy resume and ghost settlement now preserve
`projection_finish_due_at = -1` for pinned async policies. Each sibling uses
its own pinned job policy from the existing transaction read. Missing or
synchronous policies retain a positive clock for classification.

The independent `projection_followup_due_at` still becomes due now, so retiring
the finish hint does not suppress async delivery. Receipt content, privacy and
custody checks, assignment ordering, usage accounting and completion replay
remain unchanged. No new reads, write operations or indexes are introduced.

## Rollout and rollback

This source correction awaits the ordinary Release lane and production
verification. It adds no setting or activation. The existing async-skip switch
defaults on; `BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED=false` restores finish
discovery of negative clocks. Classification retains cap 8 (range 0-16;
0 pauses it). Finish-backoff activation is a separate decision.

See the [async finish runbook](../../runbooks/projection-finish-async-skip.md)
for the clock/index contract, classification budget and rollout acceptance.
There is no new environment, wire or payload contract in this correction.

## Verification and production acceptance

The source change passed 493 affected unit tests, 37 loopback Firestore tests
(one skipped), typechecking and normal repository gates. The unit coverage
includes mixed pinned sibling policies, all four writers, independent follow-up
clocks and completion replay without double charging.

After a source-containing release, compare positive-clock stock drain against
classification throughput, then measure a full hour of finish reads below the
corrected 502,606/hour baseline. The production owners also read both caller
counters, follow-up completions and matched upload-to-transcript p50/p90 against
92/455 seconds. The empty-page read estimate is not a measured saving; no
production latency or cost improvement is claimed by this note.
