# Lifecycle properties (WP-B)

These tests consume `testing.lifecycle_sim` fixtures. Admission, transactions,
worker results, projection and enrichment-outbox writes remain real; only the
existing model/provider and outbound wake leaves are local.

```bash
bash backend/testing/lifecycle_sim/run.sh --keep --extra-test-module testing/lifecycle_properties/test_properties.py
```

Use the workspace heavy-command wrapper and a private test HOME/config/cache,
with ambient Google credentials/projects removed as required by the simulator.
The same hermetic preflight and network block surround both modules' collection
and execution. The existing listen/pusher CI tail explicitly passes this target.
The simulator without the argument still collects its original module only.

The controls assert capturing/sealed shadows, bounded admission/worker ticks,
and a persisted summary reaching settled. They use two expired-admission clock
schedules. The late-result control retains synthetic three-minute audio so a
minimum-content summary waiver cannot explain away the missing title. It runs
finalization before the worker, then requires the actual result commit to
increment a pending durable enrichment outbox with a token and finite due time.
The finalization job may already be completed: the rearm obligation lives in
the outbox. A notification alone is insufficient.

With `RECORD_TOKEN_LEASE_MODE=off` (the default), producer custody retains the
original no-TTL proof (lead2 `9d457c`, owner ruling `7a6181`). An old live
producer without audio must survive recovery ticks and another session's finish;
only its exact finish clears its token. A separate retained-tail case must keep
the token while a fresh proof shows its producer live, then clear it through real
repair only when the scoped producer proof establishes death. The test clocks
advance only simulator/recovery/proof seams. No deadline field, expiration policy
or production SLA is invented. The earlier provisional budget case was retired
when the owner supplied this contract.

Pure fair-use properties live in
`tests/unit/test_lifecycle_ladder_properties.py`: generated quiet-read schedules
after real escalation must preserve unexpired stages and reach the base after
bounded expiry reads. These are green after #24531. Unit wiring controls pin
the default target, explicit forwarding, scoped path refusal and selector.

Local timing evidence and remaining fix ownership are recorded in the workspace
`data/run-2026-11-04-lifecycle-invariants/README.md`. The added module must stay
within the lead's approximately 60-second PR-tail budget. `--runxfail` is for a
local red-reason audit and is not added to the CI invocation.

Part A adds real-Firestore named-exit controls for leased → lapsed → complete
seal, partial finish with hourly coordinator, or late-append reactivation with
upload-revision bump. A 3600s lease requires both quiet deadlines; retained
audio, privacy and transactional state fences remain authoritative.
