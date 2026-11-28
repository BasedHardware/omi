# Retained recording debt: shared settlement and retry proof

Test-only follow-through to [#24884](https://github.com/BasedHardware/omi/pull/24884)
and [#24863](https://github.com/BasedHardware/omi/pull/24863), covering target
architecture parity rows PL-487 and PL-482. Serving behavior and configuration
are unchanged.

`backend/scripts/record_dead_letter_emulator_test.py` runs the production
recording drainer and reason-bound requeue against simulator, legacy Firestore
and replacement Postgres. It verifies a full nonrenewing expiry window,
deadline-boundary settlement, malformed deadline refusal, stale-worker and
privacy fences, idempotent requeue, complete custody/policy preservation and
bounded age-based barrier retries. Both kill switches retain their contracts.

The existing emulator-proof runner selects the suite, including for a future
test-only change through its `*_emulator_test.py` workflow trigger. CI requires
the simulator and emulator; complete local qualification additionally requires
`OMI_REQUIRE_STORE_BACKENDS=all`. An unavailable required store fails.

The boolean enqueue-age case exposes a Postgres generated-column cast gap
([#24960](https://github.com/BasedHardware/omi/issues/24960)). Firestore and the
simulator pass. Its strict expected failure accepts only that exact SQL error;
a repair must pass the full invariant and remove the annotation. PL-482 remains
incomplete while this gap exists. No PL-487 case is an expected failure.

Audio admission and the drainer clock are injected. No vendor or storage IO,
production configuration, physical erasure or serving migration is claimed.
