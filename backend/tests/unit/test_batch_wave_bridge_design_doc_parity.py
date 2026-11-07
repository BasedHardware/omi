"""The wave-bridge design doc stays aligned with the constants it describes.

`backend/docs/batch-contention-chain-wave-bridge.md` is the review surface for
this change: it names the failure class, the exact rung table, the window
arithmetic, the damper's division of labor and the rollout contract. Each
claim here is checked against the code it describes, so a future budget edit
cannot ship with a stale doc.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import re
from pathlib import Path

from database.batch_pipeline_store import FirestoreStore
from database.firestore_transaction_retry import (
    _INITIAL_MAX_DELAY_SECONDS,
    _MAX_DELAY_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    equal_jitter_delay,
)

BACKEND = Path(__file__).resolve().parents[2]
DOC = (BACKEND / 'docs' / 'batch-contention-chain-wave-bridge.md').read_text()
FC = 'FC-contention-chain-spends-its-budget-inside-one-abort-wave'


def test_the_doc_declares_the_failure_class():
    assert f'Failure-Class: {FC}' in DOC


def test_the_doc_names_the_changed_constant():
    assert '_MAX_DELAY_SECONDS' in DOC
    assert _MAX_DELAY_SECONDS == 4.0


def test_the_doc_states_the_former_and_new_cap():
    assert 'from 1.0 s to 4.0 s' in DOC


def test_the_doc_states_the_former_window_arithmetic():
    assert 'summed to 1.2-2.4 s' in DOC
    gaps = [_INITIAL_MAX_DELAY_SECONDS * (2**k) for k in range(4)]
    assert abs(sum(min(g, 1.0) for g in gaps) - 2.4) < 1e-9  # 0.2+0.4+0.8+1.0


def test_the_doc_states_the_new_window_arithmetic():
    assert 'sum to 1.5-3.0 s' in DOC
    gaps = [equal_jitter_delay(k, random_value=lambda: j) for k in range(1, 5) for j in (0.0, 1.0)]
    assert min(sum(gaps[::2]), sum(gaps[1::2])) == 1.5
    assert max(sum(gaps[::2]), sum(gaps[1::2])) == 3.0


def test_the_doc_states_attempt_five_start_times():
    assert 'up to\n  3.0 s after the first abort' in DOC or '3.0 s after the first abort' in DOC
    assert '2.4 s at maximum jitter' in DOC


def test_the_doc_pins_the_unchanged_early_rungs():
    for rung in ('0.2s', '0.4s', '0.8s'):
        assert rung in DOC
    assert equal_jitter_delay(3, random_value=lambda: 1.0) == 0.8


def test_the_doc_pins_the_grown_fourth_rung():
    assert 'from 1.0 s to 1.6 s' in DOC
    assert equal_jitter_delay(4, random_value=lambda: 1.0) == 1.6


def test_the_doc_describes_the_restored_tail():
    assert '`3.2s, 4.0s, ...`' in DOC
    assert equal_jitter_delay(5, random_value=lambda: 1.0) == 3.2
    assert equal_jitter_delay(6, random_value=lambda: 1.0) == 4.0


def test_the_doc_names_the_storm_damper_ceiling_alignment():
    assert 'STORM_DAMPER_CAP_SECONDS' in DOC
    assert _MAX_DELAY_SECONDS == FirestoreStore.STORM_DAMPER_CAP_SECONDS


def test_the_doc_names_the_division_of_labor():
    assert 'arms the damper' in DOC or 'arming' in DOC
    assert 'damper' in DOC.lower()


def test_the_doc_names_the_deadline_scoped_callers():
    assert 'Deadline-scoped callers' in DOC
    assert 'reserve floor' in DOC


def test_the_doc_states_the_reserve_floor_dominates_the_cap():
    assert '30 s reserve floor' in DOC
    assert 'deadline + one in-flight attempt' in DOC


def test_the_doc_states_the_no_flag_rollout():
    assert 'No flag' in DOC
    assert 'BATCH_PIPELINE_CONTENTION_RETRY_ENABLED' in DOC


def test_the_doc_lists_the_coverage_suites_and_they_exist():
    listed = re.findall(r'`tests/unit/([a-z_0-9]+\.py)`', DOC)
    assert len(listed) >= 8
    for name in listed:
        assert (BACKEND / 'tests' / 'unit' / name).exists(), name


def test_the_doc_names_the_sensor_signature_it_targets():
    assert 'outcome=exhausted' in DOC
    assert 'Loop S' in DOC


def test_the_doc_keeps_the_default_attempt_budget_visible():
    assert 'five attempts' in DOC
    assert DEFAULT_MAX_ATTEMPTS == 5


def test_the_doc_is_listed_in_the_module_cap_comment_family():
    retry_source = (BACKEND / 'database' / 'firestore_transaction_retry.py').read_text()
    assert 'wave-bridge' in retry_source or 'wave bridge' in retry_source
    assert 'wave bridge' in DOC or 'wave-bridge' in DOC
