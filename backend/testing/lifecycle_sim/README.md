# Lifecycle simulator

This extends `testing.listen_pusher_stack` with direct, bounded production
lifecycle ticks. Firestore runs in Firebase's disposable loopback emulator;
retained synthetic PCM and encrypted artifacts use the stack's local storage
adapter. No provider or GCP access is allowed.

```bash
bash backend/testing/lifecycle_sim/run.sh --keep
```

The existing listen/pusher gauntlet runs these scenarios after its existing
emulator-concurrency tail. The standalone wrapper runs only these scenarios.
Both use the same emulator-owning shell. No CI workflow or budget change is
required. The runner prints `added_wall_seconds` including scenario and child setup.

For helper unit tests, `BACKEND_UNIT_TEST_FILE_LIST` must name a text file
whose single line is `tests/unit/test_lifecycle_sim_unit.py` (relative to
`backend/`), then run `bash backend/test.sh` from the repository root. It is a
list-file input, not a test path or comma-separated list.

The preflight rejects reachable ADC, explicit service-account credentials,
ambient Cloud SDK configuration, real project IDs, and remote emulator
endpoints before constructing the stack. Collection and execution run under
`block_outbound_network`; child environments use the stack's allowlist and
private home/config directories.

`LifecycleSim` is the shared WP-B fixture. It exposes `seed`, `seal`,
`register`, `age`, `sweep`, `recover_nojob`, `drain`, `tick`, `row`, `job`,
and the derived `phase`. Each scenario owns one synthetic capture. Admission,
privacy checks, artifact staging, scheduler leases, ordered merge and
projection are real. `FakeSTT` and `PipelineWorker` replace GPU model leaves;
the summary control uses the existing stack's provider leaves with the real
recovery processing coordinator. This measures lifecycle behavior, not model
quality or live deployment health.

The simulator's local storage subclass adds the artifact stream-upload method
to the existing stack adapter while preserving its create-only and generation
preconditions. Production storage implementations are unchanged.

Pass `stt_profile=STTProfile(exhaustion=(ExhaustionWindow(...),))` to script
vendor errors/empty results/zero capacity on the shared `VirtualClock`.

`age_job_row(DocumentReference, seconds)` shifts existing batch/finalization
job clock fields without changing source audio clocks. `BoundaryFault` fails
one exact seal/register/admit operation once. The instrumented listener also
accepts those boundary names in the existing
`OMI_STACK_RECORDING_LIFECYCLE_FAULT` selector's `phase` field. Production
entrypoints never import the installer.

Known leaks use `xfail(strict=True, raises=LifecycleInvariantError)`: only a
final invariant assertion can satisfy the expected failure. Fixture setup,
transport, proof and worker failures remain red. To verify the actual failing
assertions locally, run `run.sh --keep --runxfail`; that option disables pytest
xfail handling and is never part of the CI runner chain.

Lead ruling `1c8084` (2026-11-04) requires unreproduced leaks to remain green
or explicitly skipped, rather than manufacturing an expected failure.
