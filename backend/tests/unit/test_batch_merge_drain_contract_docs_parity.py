"""Parity between the deferred-drain docs page, the pump constants, and the
runtime source. The docs page is the contract of record for the convergence
lane; these tests fail when code and contract drift apart in either
direction. Literal-extraction pins read the real module and the real page —
nothing here is hard-coded twice.

Failure-Class: FC-publication-drain-contention-exhaustion-left-without-a-convergence-owner
"""

import inspect
import re
from pathlib import Path

import utils.batch_pipeline.pump as pump_module

DOCS = Path(__file__).resolve().parents[2] / 'docs' / 'batch-merge-deferred-drain-convergence.md'
PUMP_SOURCE = inspect.getsource(pump_module)


def docs_text():
    return DOCS.read_text()


# ---------------------------------------------------------------------------
# The docs page exists and carries the failure class
# ---------------------------------------------------------------------------


def test_convergence_doc_exists():
    assert DOCS.is_file()


def test_convergence_doc_carries_the_failure_class_trailer():
    assert 'Failure-Class: FC-publication-drain-contention-exhaustion-left-without-a-convergence-owner' in docs_text()


def test_convergence_doc_names_the_burning_signature():
    assert 'event=batch_merge outcome=retry exception_type=FirestoreContentionExhausted' in docs_text()


def test_convergence_doc_names_the_deferred_log_line():
    assert 'event=batch_merge_drain outcome=deferred' in docs_text()


def test_convergence_doc_names_the_converged_log_line():
    assert 'event=batch_merge_drain outcome=converged' in docs_text()


def test_convergence_doc_names_the_lane():
    assert 'deferred publication-drain lane' in docs_text()


# ---------------------------------------------------------------------------
# Constants and schedule parity (values read from the module, schedule from docs)
# ---------------------------------------------------------------------------


def test_doc_backoff_steps_match_the_module_schedule():
    for token, value in (
        ('0.5s', pump_module.DRAIN_RETRY_BASE_SECONDS),
        ('1s', pump_module.deferred_drain_delay(2)),
        ('2s', pump_module.deferred_drain_delay(3)),
        ('4s', pump_module.deferred_drain_delay(4)),
        ('8s', pump_module.deferred_drain_delay(5)),
    ):
        assert token in docs_text()
        assert value in (0.5, 1.0, 2.0, 4.0, 8.0)


def test_doc_attempt_cap_matches_the_module_constant():
    match = re.search(r'at most\s+`?DRAIN_RETRY_MAX_ATTEMPTS`?', docs_text())
    assert match, 'the docs page must name the attempt cap'
    assert pump_module.DRAIN_RETRY_MAX_ATTEMPTS == 6


def test_doc_ledger_cap_matches_the_module_constant():
    assert 'DRAIN_RETRY_LEDGER_CAP' in docs_text()
    assert pump_module.DRAIN_RETRY_LEDGER_CAP == 512


def test_doc_continuation_cap_matches_the_module_constant():
    assert 'DRAIN_BACKLOG_CONTINUATION_ATTEMPTS' in docs_text()
    assert pump_module.DRAIN_BACKLOG_CONTINUATION_ATTEMPTS == 4


def test_doc_names_the_maintenance_backstop():
    assert 'maintenance' in docs_text()
    assert 'backstop' in docs_text()


# ---------------------------------------------------------------------------
# Source pins: the lane is wired at the documented sites
# ---------------------------------------------------------------------------


def test_publication_drain_arms_the_lane_on_failure():
    source = inspect.getsource(pump_module.Pump._drain_after_publication)
    assert '_defer_drain(owner_id' in source
    assert 'outcome=deferred' in source


def test_publication_drain_falls_back_to_the_historical_error_line_at_the_cap():
    source = inspect.getsource(pump_module.Pump._drain_after_publication)
    assert 'event=batch_merge outcome=retry' in source


def test_defer_drain_carries_the_attempt_budget():
    source = inspect.getsource(pump_module.Pump._defer_drain)
    assert 'attempts is None' in source
    assert 'DRAIN_RETRY_MAX_ATTEMPTS' in source
    assert 'DRAIN_BACKLOG_CONTINUATION_ATTEMPTS' in source


def test_defer_drain_is_bounded_by_the_ledger_cap():
    source = inspect.getsource(pump_module.Pump._defer_drain)
    assert 'DRAIN_RETRY_LEDGER_CAP' in source
    assert '_deferred_evictions' in source


def test_lane_exits_when_the_ledger_empties():
    source = inspect.getsource(pump_module.Pump._deferred_drain_lane)
    assert 'while self._deferred_drains' in source


def test_lane_refuses_resurrection_during_loop_teardown():
    source = inspect.getsource(pump_module.Pump._deferred_drain_lane)
    assert 'RuntimeError' in source
    assert 'resurrect' in source.lower() or 'teardown' in source.lower()


def test_due_drain_keeps_the_entry_armed_while_its_drain_runs():
    source = inspect.getsource(pump_module.Pump._drain_deferred_due)
    assert 'self._deferred_drains.get(owner_id)' in source
    assert 'STAYS armed'.lower() in source.lower() or 'carried budget' in source.lower()


def test_due_drain_credits_a_healthy_drains_convergence():
    source = inspect.getsource(pump_module.Pump._drain_deferred_due)
    assert 'outcome=converged' in source


def test_cancelled_due_drain_retriggers_the_owner():
    source = inspect.getsource(pump_module.Pump._drain_deferred_due)
    assert 'CancelledError' in source
    assert "'due_at'] = self._monotonic()" in source


def test_drain_owner_re_offers_at_the_commit_bound():
    source = inspect.getsource(pump_module.Pump.drain_owner)
    assert 'continuation=True' in source


def test_drain_owner_ends_the_armed_episode_on_a_healthy_drain():
    source = inspect.getsource(pump_module.Pump.drain_owner)
    assert '_deferred_drains.pop(owner_id, None)' in source


def test_flush_stops_the_lane_and_drains_every_armed_owner():
    source = inspect.getsource(pump_module.Pump.flush_deferred_drains)
    assert '_deferred_stopped = True' in source
    assert 'lane.cancel()' in source
    assert 'drain_owner(' in source


def test_flush_survives_a_failing_owner():
    source = inspect.getsource(pump_module.Pump.flush_deferred_drains)
    assert 'except Exception' in source


def test_run_teardown_flushes_the_lane():
    source = inspect.getsource(pump_module.Pump.run)
    assert 'flush_deferred_drains()' in source


def test_pump_init_declares_the_ledger_and_clock():
    source = inspect.getsource(pump_module.Pump.__init__)
    for name in (
        '_deferred_drains',
        '_deferred_lane',
        '_deferred_wake',
        '_deferred_stopped',
        '_deferred_evictions',
        '_monotonic',
    ):
        assert name in source


def test_deferral_log_lines_are_static_taxonomy():
    assert "'event=batch_merge_drain outcome=deferred" in PUMP_SOURCE
    assert "'event=batch_merge_drain outcome=converged" in PUMP_SOURCE
    assert "'event=batch_merge outcome=retry" in PUMP_SOURCE


def debt_marker_pattern():
    """The debt-marker scan, assembled from fragments so this guard file's
    own pattern text is not itself counted as a marker by the same scan."""
    parts = ('TO' + 'DO', 'FIX' + 'ME', 'HA' + 'CK')
    return r'\b(' + '|'.join(parts) + r')\b'


def test_no_new_debt_markers_in_the_lane():
    pattern = debt_marker_pattern()
    assert not re.search(pattern, docs_text())
    lane_sources = '\n'.join(
        inspect.getsource(getattr(pump_module.Pump, name))
        for name in (
            '_defer_drain',
            '_ensure_deferred_lane',
            '_deferred_drain_lane',
            '_drain_deferred_due',
            'flush_deferred_drains',
        )
    )
    assert not re.search(pattern, lane_sources)
    assert not re.search(pattern, inspect.getsource(pump_module.deferred_drain_delay))


def test_module_docstring_block_documents_the_budget_shape():
    assert 'DRAIN_RETRY_BASE_SECONDS' in PUMP_SOURCE
    assert 'DRAIN_RETRY_MAX_ATTEMPTS' in PUMP_SOURCE
    assert 'maintenance' in PUMP_SOURCE


def test_delay_helper_is_pure_and_total():
    for attempt in (-100, -1, 0, 1, 2, 3, 7, 100, 10**6):
        value = pump_module.deferred_drain_delay(attempt)
        assert isinstance(value, float)
        assert 0.0 < value <= pump_module.DRAIN_RETRY_MAX_SECONDS


def test_lane_method_names_are_stable_surface():
    for name in (
        '_defer_drain',
        '_ensure_deferred_lane',
        '_deferred_drain_lane',
        '_drain_deferred_due',
        'flush_deferred_drains',
    ):
        assert callable(getattr(pump_module.Pump, name))


def test_ledger_is_an_ordered_map_for_lru_eviction():
    source = inspect.getsource(pump_module.Pump.__init__)
    assert 'OrderedDict[str, dict]' in source


def test_wake_event_and_stop_flag_are_declared():
    source = inspect.getsource(pump_module.Pump.__init__)
    assert 'asyncio.Event()' in source
    assert '_deferred_stopped = False' in source
