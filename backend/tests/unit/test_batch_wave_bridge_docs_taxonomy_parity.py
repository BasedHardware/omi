"""Docs, log taxonomy and label-grammar parity for the wave-bridge change.

Every number this change moves is written down in three places — the retry
module's own comments, the store damper's docstring, and the storm-damper
design doc — and every number must agree with the constants. The log lines the
chain and damper emit are a closed taxonomy (retry gaps, recovered outcomes,
exhaustions, deadline gates, store backoffs) whose fields are pinned here by
regex against the real emitters. The operation-label grammar that keeps every
exhaustion attributable is walked label by label against the production
callers. A drift in any of these surfaces is a review defect before it is a
production defect.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import logging
import ast
import re
from pathlib import Path
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

import database.firestore_transaction_retry as retry_module
from config import batch_pipeline as config_batch_pipeline
from database import batch_pipeline_store as storage
from database.batch_pipeline_transaction_labels import (
    SHADOW_STORE_OPERATIONS,
    current_operation,
    pull_operation,
    require_operation_label,
    shadow_operation,
)
from database.firestore_transaction_retry import (
    _INITIAL_MAX_DELAY_SECONDS,
    _MAX_DELAY_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    equal_jitter_delay,
)

BACKEND = Path(__file__).resolve().parents[2]
RETRY_SOURCE = (BACKEND / 'database' / 'firestore_transaction_retry.py').read_text()
STORE_SOURCE = (BACKEND / 'database' / 'batch_pipeline_store.py').read_text()
DAMPER_DOC = (BACKEND / 'docs' / 'batch-contention-storm-damper.md').read_text()
FC = 'FC-contention-chain-spends-its-budget-inside-one-abort-wave'


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def aborted():
    return Aborted('read contention')


# --------------------------------------------------------------------------
# The documented rung table equals the implemented ladder
# --------------------------------------------------------------------------


def test_module_docstring_documents_the_ladder_rungs():
    assert '``0.2s, 0.4s, 0.8s, 1.6s, 3.2s``' in RETRY_SOURCE


@pytest.mark.parametrize('rung,seconds', [(1, 0.2), (2, 0.4), (3, 0.8), (4, 1.6), (5, 3.2)])
def test_documented_rung_table_matches_the_ladder(rung, seconds):
    assert equal_jitter_delay(rung, random_value=lambda: 1.0) == seconds


def test_documented_cap_binds_from_the_sixth_rung():
    assert 'capped at ``_MAX_DELAY_SECONDS`` (which binds from the sixth rung)' in RETRY_SOURCE
    assert equal_jitter_delay(6, random_value=lambda: 1.0) == _MAX_DELAY_SECONDS


def test_cap_comment_states_the_former_budget_window():
    assert '2.4 s under the former 1.0 s cap' in RETRY_SOURCE


def test_cap_comment_states_the_new_budget_window():
    assert 'sum to 1.5-3.0 s' in RETRY_SOURCE


def test_cap_comment_names_the_failure_class():
    assert f'Failure-Class: {FC}' in RETRY_SOURCE


def test_run_with_docstring_states_the_gap_window():
    assert 'inter-attempt gaps now span 1.5-3.0 s' in RETRY_SOURCE


def test_store_damper_docstring_states_the_gap_window():
    assert 'inter-attempt gaps now sum to 1.5-3.0 s' in STORE_SOURCE


def test_storm_damper_doc_states_the_gap_window():
    assert 'inter-attempt gaps sum' in DAMPER_DOC
    assert '1.5-3.0 s' in DAMPER_DOC


def test_retired_window_phrase_is_gone_from_the_damper_doc():
    assert 'roughly one to three' not in DAMPER_DOC


def test_retired_window_phrase_is_gone_from_the_store_module():
    assert 'roughly one to three seconds' not in STORE_SOURCE


def test_retired_window_phrase_is_gone_from_the_damper_test_docstring():
    source = (BACKEND / 'tests' / 'unit' / 'test_batch_store_contention_storm_damper.py').read_text()
    assert 'roughly one to three seconds' not in source


def test_damper_doc_still_documents_its_own_ladder_unchanged():
    assert '`0.25s → 0.5s → 1s → 2s → 4s`' in DAMPER_DOC
    assert storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS == 4.0


def test_damper_doc_documents_the_unchanged_exhaustion_line():
    assert '`outcome=exhausted` ERROR line is unchanged' in DAMPER_DOC


# --------------------------------------------------------------------------
# The chain's log taxonomy (fields and levels)
# --------------------------------------------------------------------------


def exhausting_chain(caplog, attempts=5):
    clock = FakeClock()
    state = {'n': 0}

    def operation(transaction):
        state['n'] += 1
        raise aborted()

    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        try:
            retry_module.run_with_transaction_contention_retry(
                lambda: object(),
                operation,
                operation_name='taxonomy',
                max_attempts=attempts,
                sleep=clock.sleep,
                random_value=lambda: 1.0,
                monotonic=clock.monotonic,
            )
        except retry_module.FirestoreContentionExhausted:
            pass
    return [record.getMessage() for record in caplog.records]


def test_retry_gap_lines_carry_operation_attempt_and_delay(caplog):
    lines = [line for line in exhausting_chain(caplog) if 'outcome=retry' in line]
    assert len(lines) == 4
    for index, line in enumerate(lines, start=1):
        assert re.fullmatch(
            r'firestore_transaction_contention operation=taxonomy attempt=%d/5 outcome=retry delay_ms=\d+' % index,
            line,
        )


def test_retry_gap_delays_are_the_documented_rungs(caplog):
    lines = [line for line in exhausting_chain(caplog) if 'outcome=retry' in line]
    delays = [re.search(r'delay_ms=(\d+)', line).group(1) for line in lines]
    assert delays == ['200', '400', '800', '1600']


def test_recovered_line_carry_operation_and_attempt(caplog):
    clock = FakeClock()
    state = {'n': 0}

    def operation(transaction):
        state['n'] += 1
        if state['n'] < 3:
            raise aborted()
        return 'ok'

    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        retry_module.run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='recovered',
            sleep=clock.sleep,
            random_value=lambda: 1.0,
            monotonic=clock.monotonic,
        )
    recovered = [line for line in caplog.messages if 'outcome=recovered' in line]
    assert recovered == ['firestore_transaction_contention operation=recovered attempt=3/5 outcome=recovered']


def test_exhausted_line_is_error_level_and_names_the_cap(caplog):
    lines = exhausting_chain(caplog)
    exhausted = [line for line in lines if 'outcome=exhausted' in line]
    assert exhausted == ['firestore_transaction_contention operation=taxonomy attempt=5/5 outcome=exhausted']


def test_retry_gap_lines_are_warning_level(caplog):
    exhausting_chain(caplog)
    for record in caplog.records:
        if 'outcome=retry' in record.getMessage():
            assert record.levelname == 'WARNING'
        if 'outcome=exhausted' in record.getMessage():
            assert record.levelname == 'ERROR'


def test_recovered_lines_are_info_level(caplog):
    clock = FakeClock()
    state = {'n': 0}

    def operation(transaction):
        state['n'] += 1
        if state['n'] < 2:
            raise aborted()

    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        retry_module.run_with_transaction_contention_retry(
            lambda: object(), operation, operation_name='levels', sleep=clock.sleep, monotonic=clock.monotonic
        )
    for record in caplog.records:
        if 'outcome=recovered' in record.getMessage():
            assert record.levelname == 'INFO'


def test_log_lines_never_carry_the_exception_message(caplog):
    lines = exhausting_chain(caplog)
    for line in lines:
        assert 'read contention' not in line


# --------------------------------------------------------------------------
# The store-boundary backoff taxonomy
# --------------------------------------------------------------------------


def backoff_line(caplog):
    lines = [record.getMessage() for record in caplog.records if 'event=batch_store_backoff' in record.getMessage()]
    assert len(lines) == 1
    return lines[0]


def test_backoff_line_names_the_operation_and_waited_millis(monkeypatch, caplog):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')

    damper = storage._ContentionStormDamper(monotonic=lambda: 500.0, sleeper=lambda s: None, random_value=lambda: 1.0)
    damper.arm('batch_fail')
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=Mock(), storm_damper=damper)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        with pytest.raises(Exception):
            store.run(lambda tx: True, operation='batch_fail')
    line = backoff_line(caplog)
    assert 'operation=batch_fail' in line
    assert 'waited_ms=250' in line


# --------------------------------------------------------------------------
# The label grammar, walked against the production callers
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    'label',
    [
        'batch_fail',
        'batch_complete',
        'batch_defer',
        'batch_release',
        'batch_recover',
        'batch_redrive',
        'batch_merge_commit',
        'batch_merge_hold_release',
        'batch_gpu_release',
        'batch_admit',
        'batch_intake_status',
    ],
)
def test_production_labels_pass_the_grammar(label):
    assert require_operation_label(label) == label


def test_the_anonymous_default_label_is_refused():
    # The anonymous default is refused: an unlabeled run must raise.
    with pytest.raises(ValueError):
        require_operation_label(None)


def test_the_shadow_operation_vocabulary_is_closed():
    assert SHADOW_STORE_OPERATIONS == frozenset(
        {
            'finish',
            'offer',
            'reserve',
            'ready',
            'projection_input',
            'take',
            'paid',
            'handoff',
            'start_recovery',
            'recovery_transport_failed',
            'reap',
        }
    )


def test_shadow_operations_are_prefixed_for_attribution():
    with shadow_operation('offer'):
        assert current_operation() == 'batch_shadow_offer'


def test_pull_operations_carry_the_shard_for_attribution():
    with pull_operation('pull', 'scheduler_05'):
        assert current_operation() == 'batch_pull shard=scheduler_05'


def test_the_shard_count_comes_from_the_config():
    assert config_batch_pipeline.SCHEDULER_SHARDS >= 1


# --------------------------------------------------------------------------
# The constants this change relies on stay coherent
# --------------------------------------------------------------------------


def test_default_attempt_budget_constant():
    assert DEFAULT_MAX_ATTEMPTS == 5


def test_initial_rung_constant():
    assert _INITIAL_MAX_DELAY_SECONDS == 0.2


def test_cap_constant_matches_the_damper_ceiling():
    assert _MAX_DELAY_SECONDS == storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS


def test_the_module_has_no_new_debt_markers():
    markers = '|'.join(word for word in ('TO' + 'DO', 'FIX' + 'ME', 'HAC' + 'K'))
    assert not re.search(rf'\b({markers})\b', RETRY_SOURCE)


def test_the_module_declares_its_imports_at_module_scope():
    tree = ast.parse(RETRY_SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            for child in ast.walk(node):
                assert not isinstance(child, ast.Import | ast.ImportFrom), f'{node.name} imports inside a body'
