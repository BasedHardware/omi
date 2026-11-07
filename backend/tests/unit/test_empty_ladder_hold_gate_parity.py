# Failure-Class: FC-empty-ladder-gate-drift-misroutes-recovery-units-between-hold-retry-and-terminal-rungs
"""The post-retry hold gate: custody, refusal carry, and cap-lane parity.

When the padded recovery recognizer returns no attempt (``None``), the empty
ladder's second boundary decides between keeping raw custody (``HeldWork``,
the unit is re-offered without spending a provider-failure attempt) and
settling the unit through the same recovery handoff the terminal gate
selects. This suite pins that boundary against the cap lane: with compute
admission enforced the hold exists and carries the admission refusal reason;
with the lane off (or for shadow units) the same recognizer outcome settles
through the terminal gate instead. The gate itself reads the shared
``empty_ladder_handoff`` predicate, so every cell here doubles as a
drift-guard against the terminal-gate suite.
"""

from unittest.mock import Mock

import numpy as np
import pytest

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from utils.batch_pipeline.contracts import HeldWork, RecoveryWork, ValidationFailureWork, WorkResult

SAMPLE_RATE = 16000

COMBOS = (
    (True, True, True),
    (True, False, True),
    (False, True, True),
    (False, False, True),
    (True, True, False),
    (True, False, False),
    (False, True, False),
    (False, False, False),
)


def set_flags(monkeypatch, *, safety, recovery, disposition, validation=True, enforce):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', str(safety))
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', str(recovery))
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', str(disposition))
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', str(validation))
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce).lower())


def empty_worker(monkeypatch, flags, *, recover_returns=None, before_dispatch_refuses=False):
    """An empty-ASR unit whose recovery recognizer declines to attempt."""

    set_flags(monkeypatch, **flags)
    provider = Mock()
    provider.transcribe_batch.side_effect = lambda batch: [[] for _ in batch]

    def recover(samples, max_padded_seconds, *, before_dispatch=None, after_dispatch=None):
        if before_dispatch is not None and before_dispatch_refuses:
            if not before_dispatch():
                return None
        return recover_returns

    worker, *_ = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={'parakeet': provider},
        recover_words=recover,
    )
    return worker, provider


ALLOW = lambda ids: {segment_id: None for segment_id in ids}  # noqa: E731


# --- enforced lane: a declined retry keeps raw custody ---------------------------------------


def test_enforced_lane_declined_retry_holds_raw_custody(monkeypatch):
    worker, _ = empty_worker(
        monkeypatch, dict(safety=True, recovery=True, disposition=True, enforce=True), recover_returns=None
    )
    assert worker.process_batch([item('a', 2)], authorize_dispatch=ALLOW) == [HeldWork('a')]


def test_enforced_lane_declined_retry_holds_even_with_every_flag_off(monkeypatch):
    # ``fits_retry`` short-circuits the gate: a fit retry that never ran holds
    # the raw work under every flag state.
    worker, _ = empty_worker(
        monkeypatch, dict(safety=False, recovery=False, disposition=False, enforce=True), recover_returns=None
    )
    assert worker.process_batch([item('a', 2)], authorize_dispatch=ALLOW) == [HeldWork('a')]


def test_declined_retry_hold_carries_no_evidence_token(monkeypatch):
    worker, _ = empty_worker(
        monkeypatch, dict(safety=True, recovery=True, disposition=True, enforce=True), recover_returns=None
    )
    results = worker.process_batch([item('a', 2)], authorize_dispatch=ALLOW)
    assert isinstance(results[0], HeldWork) and results[0].reason == ''


def test_declined_retry_hold_sees_the_raw_unit_when_no_predecessor_exists(monkeypatch):
    seen = {}

    def recover(samples, max_padded_seconds, *, before_dispatch=None, after_dispatch=None):
        seen['len'] = len(samples)
        return None

    set_flags(monkeypatch, safety=True, recovery=True, disposition=True, enforce=True)
    provider = Mock()
    provider.transcribe_batch.side_effect = lambda batch: [[] for _ in batch]
    worker, *_ = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={'parakeet': provider},
        recover_words=recover,
    )
    worker.process_batch([item('a', 2)], authorize_dispatch=ALLOW)
    # No predecessor tail is known to this worker, so the onset trim keeps the
    # whole unit; the padding is the recovery adapter's own concern.
    assert seen['len'] == 2 * SAMPLE_RATE


def test_declined_retry_hold_flags_matrix_keeps_custody(monkeypatch):
    held = 0
    for safety, recovery, disposition in COMBOS:
        worker, _ = empty_worker(
            monkeypatch,
            dict(safety=safety, recovery=recovery, disposition=disposition, enforce=True),
            recover_returns=None,
        )
        results = worker.process_batch([item('a', 2)], authorize_dispatch=ALLOW)
        assert isinstance(results[0], HeldWork), (safety, recovery, disposition)
        held += 1
    assert held == len(COMBOS)


# --- enforced lane: an oversize unit settles through the terminal gate ------------------------


def test_enforced_lane_oversize_settles_through_the_handoff(monkeypatch):
    set_flags(monkeypatch, safety=True, recovery=True, disposition=True, enforce=True)
    provider = Mock()
    provider.transcribe_batch.side_effect = lambda batch: [[] for _ in batch]
    worker, *_ = setup_worker(
        decode=lambda work: np.zeros(int(work.duration_seconds * SAMPLE_RATE), dtype=np.float32),
        vad=lambda _: [(1, 116)],
        words_providers={'parakeet': provider},
        recover_words=Mock(return_value=None),
    )
    results = worker.process_batch([item('a', 117)], authorize_dispatch=ALLOW)
    assert results == [RecoveryWork('a', padded_retry='skipped_oversize', reason='empty_asr')]


def test_enforced_lane_oversize_with_every_flag_off_still_holds_raw_custody(monkeypatch):
    set_flags(monkeypatch, safety=False, recovery=False, disposition=False, enforce=True)
    provider = Mock()
    provider.transcribe_batch.side_effect = lambda batch: [[] for _ in batch]
    worker, *_ = setup_worker(
        decode=lambda work: np.zeros(int(work.duration_seconds * SAMPLE_RATE), dtype=np.float32),
        vad=lambda _: [(1, 116)],
        words_providers={'parakeet': provider},
        recover_words=Mock(return_value=None),
    )
    assert worker.process_batch([item('a', 117)], authorize_dispatch=ALLOW) == [HeldWork('a')]


def test_oversize_retry_runs_on_the_raw_unit_but_its_answer_is_discarded(monkeypatch):
    calls = []

    def recover(samples, max_padded_seconds, *, before_dispatch=None, after_dispatch=None):
        calls.append(len(samples))
        return None

    set_flags(monkeypatch, safety=True, recovery=True, disposition=True, enforce=True)
    provider = Mock()
    provider.transcribe_batch.side_effect = lambda batch: [[] for _ in batch]
    worker, *_ = setup_worker(
        decode=lambda work: np.zeros(int(work.duration_seconds * SAMPLE_RATE), dtype=np.float32),
        vad=lambda _: [(1, 116)],
        words_providers={'parakeet': provider},
        recover_words=recover,
    )
    results = worker.process_batch([item('a', 117)], authorize_dispatch=ALLOW)
    assert calls == [117 * SAMPLE_RATE]  # the recognition did run on the whole raw unit
    # Its answer is discarded: the skipped-oversize token records the run.
    assert results == [RecoveryWork('a', padded_retry='skipped_oversize', reason='empty_asr')]


# --- refusal reasons ride the hold ------------------------------------------------------------


def test_first_gate_refusal_holds_with_the_admission_reason(monkeypatch):
    worker, provider = empty_worker(
        monkeypatch, dict(safety=True, recovery=True, disposition=True, enforce=True), recover_returns=None
    )

    def refuse(ids):
        return {segment_id: 'allowance_exhausted' for segment_id in ids}

    assert worker.process_batch([item('a', 2)], authorize_dispatch=refuse) == [
        HeldWork('a', reason='allowance_exhausted')
    ]
    assert provider.transcribe_batch.call_count == 0


def test_recheck_refusal_holds_with_the_admission_reason(monkeypatch):
    decisions = iter([None, 'allowance_exhausted'])

    def authorize(ids):
        return {segment_id: next(decisions) for segment_id in ids}

    worker, provider = empty_worker(
        monkeypatch,
        dict(safety=True, recovery=True, disposition=True, enforce=True),
        recover_returns=None,
        before_dispatch_refuses=True,
    )
    assert worker.process_batch([item('a', 2)], authorize_dispatch=authorize) == [
        HeldWork('a', reason='allowance_exhausted')
    ]
    assert provider.transcribe_batch.call_count == 1  # the first pass ran; the retry dispatch was refused


def test_raising_authority_is_an_unevaluated_hold_not_a_failure(monkeypatch):
    worker, provider = empty_worker(
        monkeypatch, dict(safety=True, recovery=True, disposition=True, enforce=True), recover_returns=None
    )

    def broken(ids):
        raise RuntimeError('authority unavailable')

    assert worker.process_batch([item('a', 2)], authorize_dispatch=broken) == [HeldWork('a')]
    assert provider.transcribe_batch.call_count == 0


def test_missing_authority_holds_without_spending(monkeypatch):
    worker, provider = empty_worker(
        monkeypatch, dict(safety=True, recovery=True, disposition=True, enforce=True), recover_returns=None
    )
    assert worker.process_batch([item('a', 2)]) == [HeldWork('a')]
    assert provider.transcribe_batch.call_count == 0


# --- unenforced lane: the same recognizer outcome settles through the terminal gate ------------


def test_unenforced_lane_declined_retry_settles_through_the_handoff(monkeypatch):
    worker, _ = empty_worker(
        monkeypatch, dict(safety=True, recovery=True, disposition=True, enforce=False), recover_returns=None
    )
    assert worker.process_batch([item('a', 2)]) == [
        RecoveryWork('a', padded_retry='skipped_oversize', reason='empty_asr')
    ]


def test_unenforced_lane_declined_retry_with_every_flag_off_ends_terminal(monkeypatch):
    worker, _ = empty_worker(
        monkeypatch, dict(safety=False, recovery=False, disposition=False, enforce=False), recover_returns=None
    )
    assert worker.process_batch([item('a', 2)]) == [ValidationFailureWork('a', 'assemble_words', 'empty_asr')]


def test_shadow_units_never_hold_and_settle_through_the_handoff(monkeypatch):
    from dataclasses import replace

    worker, _ = empty_worker(
        monkeypatch, dict(safety=True, recovery=True, disposition=True, enforce=True), recover_returns=None
    )
    assert worker.process_batch([replace(item('a', 2), shadow=True)], authorize_dispatch=ALLOW) == [
        RecoveryWork('a', padded_retry='skipped_oversize', reason='empty_asr')
    ]


# --- a real attempt beats the hold at every flag state ------------------------------------------


def test_recovered_words_publish_on_the_enforced_lane(monkeypatch):
    worker, _ = empty_worker(
        monkeypatch,
        dict(safety=True, recovery=True, disposition=True, enforce=True),
        recover_returns=[{'word': 'recovered', 'timestamp': [0.3, 0.5]}],
    )
    results = worker.process_batch([item('a', 2)], authorize_dispatch=ALLOW)
    assert isinstance(results[0], WorkResult)


def test_recovered_empty_still_settles_through_the_handoff_on_the_enforced_lane(monkeypatch):
    worker, _ = empty_worker(
        monkeypatch,
        dict(safety=True, recovery=True, disposition=True, enforce=True),
        recover_returns=[],
    )
    assert worker.process_batch([item('a', 2)], authorize_dispatch=ALLOW) == [
        RecoveryWork('a', padded_retry='empty', padded_retry_empty=True)
    ]


def test_recovered_words_publish_on_the_unenforced_lane(monkeypatch):
    worker, _ = empty_worker(
        monkeypatch,
        dict(safety=False, recovery=True, disposition=False, enforce=False),
        recover_returns=[{'word': 'recovered', 'timestamp': [0.3, 0.5]}],
    )
    assert isinstance(worker.process_batch([item('a', 2)])[0], WorkResult)


# --- lane parity: one recognizer outcome, two custodies, one gate --------------------------------


def test_lane_parity_declined_retry_custody_differs_but_the_gate_does_not(monkeypatch):
    enforced, _ = empty_worker(
        monkeypatch, dict(safety=True, recovery=True, disposition=True, enforce=True), recover_returns=None
    )
    held = enforced.process_batch([item('a', 2)], authorize_dispatch=ALLOW)
    unenforced, _ = empty_worker(
        monkeypatch, dict(safety=True, recovery=True, disposition=True, enforce=False), recover_returns=None
    )
    settled = unenforced.process_batch([item('a', 2)])
    assert isinstance(held[0], HeldWork) and held[0].reason == ''
    assert isinstance(settled[0], RecoveryWork) and settled[0].padded_retry == 'skipped_oversize'


def test_lane_parity_hold_never_switches_to_terminal_for_a_fit_retry(monkeypatch):
    for safety, recovery, disposition in ((True, False, False), (False, True, False), (False, False, True)):
        worker, _ = empty_worker(
            monkeypatch,
            dict(safety=safety, recovery=recovery, disposition=disposition, enforce=True),
            recover_returns=None,
        )
        assert isinstance(worker.process_batch([item('a', 2)], authorize_dispatch=ALLOW)[0], HeldWork)


def test_lane_parity_terminal_settlement_matches_the_shared_predicate(monkeypatch):
    from config.batch_pipeline_empty_asr import empty_ladder_handoff

    for safety, recovery, disposition in COMBOS:
        worker, _ = empty_worker(
            monkeypatch,
            dict(safety=safety, recovery=recovery, disposition=disposition, enforce=False),
            recover_returns=None,
        )
        result = worker.process_batch([item('a', 2)])[0]
        rides = empty_ladder_handoff(
            'empty_asr', recovery_enabled=recovery, disposition_enabled=disposition, safety_enabled=safety
        )
        assert isinstance(result, RecoveryWork) is rides


# --- the remaining kill-switch hold cells ------------------------------------------------------


def test_hold_with_safety_only_keeps_custody(monkeypatch):
    worker, _ = empty_worker(
        monkeypatch, dict(safety=True, recovery=False, disposition=False, enforce=True), recover_returns=None
    )
    assert worker.process_batch([item('a', 2)], authorize_dispatch=ALLOW) == [HeldWork('a')]


def test_hold_with_disposition_only_keeps_custody(monkeypatch):
    worker, _ = empty_worker(
        monkeypatch, dict(safety=False, recovery=False, disposition=True, enforce=True), recover_returns=None
    )
    assert worker.process_batch([item('a', 2)], authorize_dispatch=ALLOW) == [HeldWork('a')]


def test_hold_with_every_switch_off_keeps_custody(monkeypatch):
    worker, _ = empty_worker(
        monkeypatch, dict(safety=False, recovery=False, disposition=False, enforce=True), recover_returns=None
    )
    assert worker.process_batch([item('a', 2)], authorize_dispatch=ALLOW) == [HeldWork('a')]


def test_hold_never_carries_a_padded_token(monkeypatch):
    worker, _ = empty_worker(
        monkeypatch, dict(safety=True, recovery=True, disposition=True, enforce=True), recover_returns=None
    )
    result = worker.process_batch([item('a', 2)], authorize_dispatch=ALLOW)[0]
    assert isinstance(result, HeldWork)
    assert not hasattr(result, 'padded_retry')


def test_recheck_refusal_reason_is_the_exact_admission_token(monkeypatch):
    decisions = iter([None, 'gpu_budget_exhausted'])

    def authorize(ids):
        return {segment_id: next(decisions) for segment_id in ids}

    worker, _ = empty_worker(
        monkeypatch,
        dict(safety=True, recovery=True, disposition=True, enforce=True),
        recover_returns=None,
        before_dispatch_refuses=True,
    )
    assert worker.process_batch([item('a', 2)], authorize_dispatch=authorize) == [
        HeldWork('a', reason='gpu_budget_exhausted')
    ]


def test_first_gate_refusal_preempts_the_padded_retry_entirely(monkeypatch):
    seen = []

    def recover(samples, max_padded_seconds, *, before_dispatch=None, after_dispatch=None):
        seen.append(len(samples))
        return None

    set_flags(monkeypatch, safety=True, recovery=True, disposition=True, enforce=True)
    provider = Mock()
    provider.transcribe_batch.side_effect = lambda batch: [[] for _ in batch]
    worker, *_ = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={'parakeet': provider},
        recover_words=recover,
    )

    def refuse(ids):
        return {segment_id: 'allowance_exhausted' for segment_id in ids}

    assert worker.process_batch([item('a', 2)], authorize_dispatch=refuse) == [
        HeldWork('a', reason='allowance_exhausted')
    ]
    assert seen == []


def test_shadow_hold_units_skip_admission_and_settle_through_the_handoff(monkeypatch):
    from dataclasses import replace

    worker, _ = empty_worker(
        monkeypatch, dict(safety=True, recovery=True, disposition=True, enforce=True), recover_returns=None
    )
    checked = []

    def authorize(ids):
        checked.append(set(ids))
        return {segment_id: 'allowance_exhausted' for segment_id in ids}

    results = worker.process_batch([replace(item('a', 2), shadow=True)], authorize_dispatch=authorize)
    # Shadow units are never admitted, so the refusal never reaches them.
    assert checked == []
    assert results == [RecoveryWork('a', padded_retry='skipped_oversize', reason='empty_asr')]
