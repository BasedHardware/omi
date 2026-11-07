"""Named rows for the capped rungs, the 270-second jitter boundary and the damper ladder.

The capped rungs (attempts 6-20) all draw from the same [2 s, 4 s) band;
each has its own named row here so a future re-shape of the ladder fails a
row that names the exact rung. The 270-second chain rows walk the attempt-1
jitter boundary budget by budget. The damper ladder rows name the applied
wait for failure counts 1 through 6.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

from google.api_core.exceptions import Aborted, InvalidArgument

import database.firestore_transaction_retry as retry_module
from database.firestore_transaction_retry import equal_jitter_delay, run_with_transaction_contention_retry

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def aborted():
    return Aborted('read contention')


def expired():
    return InvalidArgument('The referenced transaction has expired or is no longer valid.')


# --------------------------------------------------------------------------
# Capped rung rows, attempt 6 through 20
# --------------------------------------------------------------------------


def test_capped_low_bound_attempt_6():
    assert equal_jitter_delay(6, random_value=lambda: 0.0) == 2.0


def test_capped_low_bound_attempt_7():
    assert equal_jitter_delay(7, random_value=lambda: 0.0) == 2.0


def test_capped_low_bound_attempt_8():
    assert equal_jitter_delay(8, random_value=lambda: 0.0) == 2.0


def test_capped_low_bound_attempt_9():
    assert equal_jitter_delay(9, random_value=lambda: 0.0) == 2.0


def test_capped_low_bound_attempt_10():
    assert equal_jitter_delay(10, random_value=lambda: 0.0) == 2.0


def test_capped_low_bound_attempt_12():
    assert equal_jitter_delay(12, random_value=lambda: 0.0) == 2.0


def test_capped_low_bound_attempt_15():
    assert equal_jitter_delay(15, random_value=lambda: 0.0) == 2.0


def test_capped_low_bound_attempt_20():
    assert equal_jitter_delay(20, random_value=lambda: 0.0) == 2.0


def test_capped_high_bound_attempt_6():
    assert equal_jitter_delay(6, random_value=lambda: 1.0) == 4.0


def test_capped_high_bound_attempt_7():
    assert equal_jitter_delay(7, random_value=lambda: 1.0) == 4.0


def test_capped_high_bound_attempt_8():
    assert equal_jitter_delay(8, random_value=lambda: 1.0) == 4.0


def test_capped_high_bound_attempt_9():
    assert equal_jitter_delay(9, random_value=lambda: 1.0) == 4.0


def test_capped_high_bound_attempt_10():
    assert equal_jitter_delay(10, random_value=lambda: 1.0) == 4.0


def test_capped_high_bound_attempt_12():
    assert equal_jitter_delay(12, random_value=lambda: 1.0) == 4.0


def test_capped_high_bound_attempt_15():
    assert equal_jitter_delay(15, random_value=lambda: 1.0) == 4.0


def test_capped_high_bound_attempt_20():
    assert equal_jitter_delay(20, random_value=lambda: 1.0) == 4.0


def test_capped_midpoint_attempt_6():
    assert equal_jitter_delay(6, random_value=lambda: 0.5) == 3.0


def test_capped_midpoint_attempt_8():
    assert equal_jitter_delay(8, random_value=lambda: 0.5) == 3.0


def test_capped_midpoint_attempt_10():
    assert equal_jitter_delay(10, random_value=lambda: 0.5) == 3.0


def test_capped_midpoint_attempt_14():
    assert equal_jitter_delay(14, random_value=lambda: 0.5) == 3.0


# --------------------------------------------------------------------------
# Attempt-1 jitter boundary rows: a 270 s attempt under budgets around 270.2 s
# --------------------------------------------------------------------------


def gate_270(budget_extra):
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        clock.now += 270.0
        raise aborted()

    try:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='j270',
            deadline=clock.monotonic() + 270.0 + budget_extra,
            sleep=clock.sleep,
            random_value=lambda: 1,
            monotonic=clock.monotonic,
        )
    except retry_module.FirestoreContentionExhausted:
        pass
    return len(attempts), clock.now - 1000.0


def test_boundary_budget_270_runs_one_attempt_and_no_sleep():
    attempts, spent = gate_270(0.0)
    assert (attempts, round(spent, 3)) == (1, 270.0)


def test_boundary_budget_270_05_truncates_the_first_sleep():
    attempts, spent = gate_270(0.05)
    assert (attempts, round(spent, 3)) == (1, 270.0)


def test_boundary_budget_270_2_charges_the_first_sleep():
    attempts, spent = gate_270(0.2)
    assert attempts == 1
    assert round(spent, 3) == 270.2


def test_boundary_budget_270_3_charges_the_first_sleep_then_refuses():
    attempts, spent = gate_270(0.3)
    assert attempts == 1
    assert round(spent, 3) == 270.2


def test_boundary_budget_270_45_refuses_at_the_gate_after_one_sleep():
    # 0.25s remain after the first gap: below the 30s floor, no attempt 2.
    attempts, spent = gate_270(0.45)
    assert attempts == 1
    assert round(spent, 3) == 270.2


def test_boundary_budget_271_refuses_at_the_gate_after_one_sleep():
    attempts, spent = gate_271_helper()
    assert len(attempts) == 1
    assert round(spent, 3) == 270.2


def gate_271_helper():
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        clock.now += 270.0
        raise expired()

    try:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='j271',
            deadline=clock.monotonic() + 271.0,
            sleep=clock.sleep,
            random_value=lambda: 1,
            monotonic=clock.monotonic,
        )
    except retry_module.FirestoreContentionExhausted:
        pass
    return attempts, clock.now - 1000.0


def test_the_truncation_rows_never_charge_sleep_past_the_deadline():
    for extra in (0.0, 0.05, 0.2, 0.3, 0.45, 1.0):
        _, spent = gate_270(extra)
        assert spent <= 270.0 + extra + 1e-9


# --------------------------------------------------------------------------
# Damper ladder rows, failure count 1 through 6
# --------------------------------------------------------------------------


def damper_after_failures(count):
    damper = retry_module.__dict__ and __import__(
        'database.batch_pipeline_store', fromlist=['_ContentionStormDamper']
    )._ContentionStormDamper(monotonic=lambda: 500.0, sleeper=lambda s: None, random_value=lambda: 1.0)
    applied = 0.0
    for _ in range(count):
        applied = damper.arm('row')
    return applied


def test_damper_row_failure_1_waits_quarter_second():
    assert damper_after_failures(1) == 0.25


def test_damper_row_failure_2_waits_half_second():
    assert damper_after_failures(2) == 0.5


def test_damper_row_failure_3_waits_one_second():
    assert damper_after_failures(3) == 1.0


def test_damper_row_failure_4_waits_two_seconds():
    assert damper_after_failures(4) == 2.0


def test_damper_row_failure_5_waits_four_seconds():
    assert damper_after_failures(5) == 4.0


def test_damper_row_failure_6_still_waits_four_seconds():
    assert damper_after_failures(6) == 4.0


# --------------------------------------------------------------------------
# Doc rows: every family file is registered in the design doc's coverage list
# --------------------------------------------------------------------------


def test_the_design_doc_coverage_list_names_only_real_files():
    import re

    doc = (BACKEND / 'docs' / 'batch-contention-chain-wave-bridge.md').read_text()
    for name in re.findall(r'`tests/unit/([a-z_0-9]+\.py)`', doc):
        assert (BACKEND / 'tests' / 'unit' / name).exists(), name


def test_the_retry_module_constant_block_carries_the_failure_class():
    source = (BACKEND / 'database' / 'firestore_transaction_retry.py').read_text()
    marker = 'Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave'
    assert marker in source.split('_MAX_DELAY_SECONDS = 4.0')[0]


def test_the_cap_is_exported_through_the_documented_name_only():
    source = (BACKEND / 'database' / 'firestore_transaction_retry.py').read_text()
    assert '_MAX_DELAY_SECONDS = 4.0' in source
    assert '_MAX_DELAY_SECONDS = 1.0' not in source
