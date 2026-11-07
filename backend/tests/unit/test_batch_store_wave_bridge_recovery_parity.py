"""Store-boundary wave-bridge: in-chain recovery and the damper's division of labor.

``FirestoreStore.run`` is the chokepoint where the bounded contention chain
and the per-label storm damper meet. The wave-bridge cap gives the chain a
roughly three-to-six-second backoff window so a chain can land after a
multi-second abort wave; the damper only arms when a chain still exhausts.
This suite pins that division of labor at the store boundary: a wave the
bridged schedule survives commits inside one ``run`` call and never arms the
damper; a wave that outlasts the budget still exhausts, raises, and arms the
label's spacing exactly as before — including the log taxonomy, the label
grammar that keeps the exhaustion attributable, and the damper's own ladder
bounds that cap the wait a storm member ever pays.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import logging
from pathlib import Path
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from config import batch_pipeline as config_batch_pipeline
from database import batch_pipeline_store as storage
from database.batch_pipeline_transaction_labels import (
    current_operation,
    pull_operation,
    require_operation_label,
    shadow_operation,
    store_operation,
)
from database.firestore_transaction_retry import (
    _MAX_DELAY_SECONDS,
    FirestoreContentionExhausted,
)

BACKEND = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# Harnesses
# --------------------------------------------------------------------------


class AbortThenCommitTx:
    """Mimics the SDK transaction: one commit, optional abort, fresh per attempt."""

    _max_attempts = 1
    _read_only = False
    _id = None

    def __init__(self, abort_times=0):
        self.abort_times = abort_times
        self.commits = 0

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = b'synthetic'

    def _commit(self):
        self.commits += 1
        if self.abort_times > 0:
            self.abort_times -= 1
            raise Aborted('synthetic commit contention')
        self._id = None

    def _rollback(self):
        self._id = None


class WaveClient:
    """Client whose transactions abort while the synthetic wave is hot.

    ``hot_commits`` counts the aborts remaining before the wave ends; each
    aborted commit consumes one. A transaction minted after the wave ends
    commits — the store-level analogue of a chain landing after the storm.
    """

    def __init__(self, hot_commits):
        self.hot_commits = hot_commits
        self.minted = 0

    def transaction(self, max_attempts=5):
        self.minted += 1
        tx = AbortThenCommitTx(1 if self.hot_commits > 0 else 0)
        original = tx._commit

        def commit():
            try:
                original()
            except Aborted:
                self.hot_commits -= 1
                raise

        tx._commit = commit
        return tx


class StormClient:
    """Client whose every transaction commit aborts — the storm never ends."""

    def __init__(self):
        self.minted = 0

    def transaction(self, max_attempts=5):
        self.minted += 1
        return AbortThenCommitTx(1)


class DamperClock:
    def __init__(self, now: float = 500.0):
        self.now = now
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def make_damper(**overrides):
    clock = overrides.pop('clock', None) or DamperClock()
    damper = storage._ContentionStormDamper(
        monotonic=overrides.pop('monotonic', clock.monotonic),
        sleeper=overrides.pop('sleeper', clock.sleep),
        random_value=overrides.pop('random_value', lambda: 1.0),
    )
    return damper, clock


def build_store(monkeypatch, damper=None, client=None):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    if client is None:
        client = StormClient()
    return storage.FirestoreStore('batch_pipeline_dev', firestore_client=client, storm_damper=damper)


def deterministic_chain(monkeypatch, sleep=lambda _seconds: None):
    """Inject maximum jitter and no real sleeps into the chain the store runs."""
    actual = storage.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', sleep)
        kwargs.setdefault('random_value', lambda: 1.0)
        return actual(*args, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', factory)


# --------------------------------------------------------------------------
# Section A — a bridged wave commits inside one store.run and never arms the damper
# --------------------------------------------------------------------------


def test_four_abort_wave_commits_on_the_fifth_attempt(monkeypatch):
    deterministic_chain(monkeypatch)
    client = WaveClient(hot_commits=4)  # wave ends exactly when attempt 5 lands
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper, client=client)
    assert store.run(lambda tx: 'result', operation='batch_merge_commit') == 'result'
    assert client.minted == 5


def test_bridged_wave_does_not_arm_the_damper(monkeypatch):
    deterministic_chain(monkeypatch)
    client = WaveClient(hot_commits=4)
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper, client=client)
    store.run(lambda tx: True, operation='batch_merge_commit')
    assert damper.tracked_labels() == 0
    assert clock.sleeps == []  # only the chain's (injected, no-op) sleeps ran


def test_bridged_wave_keeps_the_ladder_clean_for_a_later_storm(monkeypatch):
    deterministic_chain(monkeypatch)
    client = WaveClient(hot_commits=4)
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper, client=client)
    store.run(lambda tx: True, operation='batch_merge_commit')
    # A next entry of the same label waits nothing: no residual window exists.
    waited, generation = damper.consult('batch_merge_commit')
    assert waited == 0.0
    assert generation == 0


def test_bridged_wave_recovery_is_logged_as_recovered(monkeypatch, caplog):
    deterministic_chain(monkeypatch)
    client = WaveClient(hot_commits=4)
    store = build_store(monkeypatch, damper=make_damper()[0], client=client)
    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        store.run(lambda tx: True, operation='batch_recover')
    recovered = [message for message in caplog.messages if 'outcome=recovered' in message]
    assert len(recovered) == 1
    assert 'operation=batch_recover attempt=5/5' in recovered[0]


def test_wave_one_attempt_short_of_the_budget_still_exhausts(monkeypatch):
    deterministic_chain(monkeypatch)
    client = WaveClient(hot_commits=5)  # all five attempts land inside the wave
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper, client=client)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(lambda tx: True, operation='batch_merge_commit')
    assert damper.tracked_labels() == 1


def test_wave_outlasting_the_budget_raises_and_arms_the_label(monkeypatch):
    deterministic_chain(monkeypatch)
    client = WaveClient(hot_commits=99)
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper, client=client)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(lambda tx: True, operation='batch_fail')
    waited, generation = damper.consult('batch_fail')
    assert waited > 0.0
    assert generation == 1
    assert clock.sleeps == [waited]


def test_armed_label_damps_only_its_own_next_entry(monkeypatch):
    deterministic_chain(monkeypatch)
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper, client=StormClient())
    with pytest.raises(FirestoreContentionExhausted):
        store.run(lambda tx: True, operation='batch_fail')
    clock.sleeps.clear()
    with pytest.raises(FirestoreContentionExhausted):
        store.run(lambda tx: True, operation='batch_fail')  # damped entry: consult sleeps the residual
    assert len(clock.sleeps) == 1
    clock.sleeps.clear()
    with pytest.raises(FirestoreContentionExhausted):
        store.run(lambda tx: True, operation='batch_redrive')  # a different label runs undamped
    assert clock.sleeps == []


def test_success_after_an_earlier_storm_clears_the_ladder(monkeypatch):
    deterministic_chain(monkeypatch)
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper, client=StormClient())
    with pytest.raises(FirestoreContentionExhausted):
        store.run(lambda tx: True, operation='batch_fail')
    assert damper.consult('batch_fail')[0] > 0.0
    store._client = WaveClient(hot_commits=0)  # the storm ends; the next entry commits
    assert store.run(lambda tx: 'ok', operation='batch_fail') == 'ok'
    waited, generation = damper.consult('batch_fail')
    assert waited == 0.0
    assert generation == 0


# --------------------------------------------------------------------------
# Section B — the damper's own ladder bounds (unchanged by the wave bridge)
# --------------------------------------------------------------------------


def test_damper_ladder_first_rung_is_quarter_second_at_maximum_jitter():
    damper, clock = make_damper()
    applied = damper.arm('label')
    assert applied == 0.25


@pytest.mark.parametrize('failure,rung', [(1, 0.25), (2, 0.5), (3, 1.0), (4, 2.0), (5, 4.0), (6, 4.0), (9, 4.0)])
def test_damper_ladder_doubles_to_the_cap_and_stays(failure, rung):
    damper, clock = make_damper()
    applied = 0.0
    for _ in range(failure):
        applied = damper.arm('label')
    # arm only records the window; the wait happens on the next entry's consult.
    assert clock.now == 500.0
    assert applied == rung
    waited, _ = damper.consult('label')
    assert clock.now - 500.0 == pytest.approx(waited)
    assert waited == rung


def test_damper_jitter_band_is_half_to_full_rung():
    low, _ = make_damper(random_value=lambda: 0.0)
    high, _ = make_damper(random_value=lambda: 0.999999)
    assert low.arm('x') == 0.125
    assert high.arm('x') < 0.25


def test_damper_cap_equals_the_wave_bridge_cap():
    assert storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS == _MAX_DELAY_SECONDS == 4.0


def test_damper_base_and_steps_are_unchanged():
    assert storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS == 0.25
    assert storage.FirestoreStore.STORM_DAMPER_LADDER_STEPS == 4


def test_success_generation_guard_keeps_a_live_storm_armed():
    damper, clock = make_damper()
    waited, generation = damper.consult('label')
    assert waited == 0.0 and generation == 0
    damper.arm('label')
    # A success observed by the pre-arm generation must not clear the storm.
    damper.note_success('label', generation)
    waited, generation = damper.consult('label')
    assert waited > 0.0
    assert generation == 1


def test_success_of_the_observed_generation_clears_the_ladder():
    damper, clock = make_damper()
    _, generation = damper.consult('label')
    damper.note_success('label', generation)
    waited, generation = damper.consult('label')
    assert waited == 0.0 and generation == 0


def test_arm_never_shortens_an_earlier_window():
    damper, clock = make_damper()
    damper.arm('label')  # armed until 500.25
    clock.now += 0.1
    damper.arm('label')  # second failure: rung 0.5 from 500.1 -> 500.6
    assert clock.monotonic() == pytest.approx(500.1)
    waited, _ = damper.consult('label')
    assert clock.monotonic() == pytest.approx(500.6)


def test_expired_window_consults_as_zero():
    damper, clock = make_damper()
    damper.arm('label')
    clock.now += 10.0
    waited, generation = damper.consult('label')
    assert waited == 0.0
    assert clock.sleeps == []


def test_new_label_beyond_the_cap_runs_undamped():
    damper, clock = make_damper()
    for index in range(storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS):
        damper.arm(f'label_{index}')
    assert damper.tracked_labels() == storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS
    assert damper.arm('one_too_many') == 0.0
    assert damper.tracked_labels() == storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS


def test_consult_returns_the_generation_it_will_commit_under():
    damper, _ = make_damper()
    assert damper.consult('label')[1] == 0
    damper.arm('label')
    assert damper.consult('label')[1] == 1
    damper.arm('label')
    assert damper.consult('label')[1] == 2


# --------------------------------------------------------------------------
# Section C — kill switches keep the pre-damper behavior byte-for-byte
# --------------------------------------------------------------------------


def test_retry_kill_switch_off_runs_a_single_attempt(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    client = StormClient()
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client, storm_damper=make_damper()[0])
    # The SDK wrapper reports the single aborted commit; no budget wrapper runs.
    with pytest.raises(ValueError, match='Failed to commit transaction in 1 attempts'):
        store.run(lambda tx: True, operation='batch_fail')
    assert client.minted == 1


def test_damper_kill_switch_off_skips_consult_and_arm(monkeypatch):
    deterministic_chain(monkeypatch)
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper, client=StormClient())
    with pytest.raises(FirestoreContentionExhausted):
        store.run(lambda tx: True, operation='batch_fail')
    assert clock.sleeps == []
    assert damper.tracked_labels() == 0


def test_both_switches_off_still_raise_exhaustion_from_the_single_attempt(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=StormClient(), storm_damper=make_damper()[0])
    with pytest.raises(ValueError, match='Failed to commit transaction in 1 attempts'):
        store.run(lambda tx: True, operation='batch_fail')


# --------------------------------------------------------------------------
# Section D — the exhaustion log and raise taxonomy at the store boundary
# --------------------------------------------------------------------------


def test_exhausted_raise_message_names_the_label(monkeypatch):
    deterministic_chain(monkeypatch)
    store = build_store(monkeypatch, damper=make_damper()[0], client=StormClient())
    with pytest.raises(FirestoreContentionExhausted) as raised:
        store.run(lambda tx: True, operation='batch_intake_admit')
    assert 'batch_intake_admit' in str(raised.value)


def test_chain_exhaustion_error_line_keeps_the_operation_label(monkeypatch, caplog):
    deterministic_chain(monkeypatch)
    store = build_store(monkeypatch, damper=make_damper()[0], client=StormClient())
    with caplog.at_level(logging.ERROR, logger='database.firestore_transaction_retry'):
        with pytest.raises(FirestoreContentionExhausted):
            store.run(lambda tx: True, operation='batch_merge_hold_release')
    exhausted = [message for message in caplog.messages if 'outcome=exhausted' in message]
    assert exhausted == [
        'firestore_transaction_contention operation=batch_merge_hold_release attempt=5/5 outcome=exhausted'
    ]


def test_damped_entry_logs_the_store_backoff_line(monkeypatch, caplog):
    deterministic_chain(monkeypatch)
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper, client=StormClient())
    with pytest.raises(FirestoreContentionExhausted):
        store.run(lambda tx: True, operation='batch_fail')
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        with pytest.raises(FirestoreContentionExhausted):
            store.run(lambda tx: True, operation='batch_fail')
    backoff = [message for message in caplog.messages if 'event=batch_store_backoff' in message]
    assert len(backoff) == 1
    assert 'operation=batch_fail' in backoff[0]
    assert 'waited_ms=' in backoff[0]


def test_retry_gap_warning_lines_carry_the_label_and_delay(monkeypatch, caplog):
    deterministic_chain(monkeypatch, sleep=lambda _seconds: None)
    store = build_store(monkeypatch, damper=make_damper()[0], client=StormClient())
    with caplog.at_level(logging.WARNING, logger='database.firestore_transaction_retry'):
        with pytest.raises(FirestoreContentionExhausted):
            store.run(lambda tx: True, operation='batch_fail')
    retry_lines = [message for message in caplog.messages if 'outcome=retry' in message]
    assert len(retry_lines) == 4
    assert 'operation=batch_fail attempt=1/5' in retry_lines[0]
    assert 'delay_ms=200' in retry_lines[0]
    # The tail rungs: attempt 4's gap is the grown 1.6s rung; attempt 5 is the
    # cap — it exhausts without another gap line.
    assert 'operation=batch_fail attempt=4/5' in retry_lines[3]
    assert 'delay_ms=1600' in retry_lines[3]


# --------------------------------------------------------------------------
# Section E — the label grammar keeps every exhaustion attributable
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    'label',
    ['batch_fail', 'batch_merge_commit', 'batch_recover', 'batch_redrive', 'batch_gpu_release', 'batch_admit', 'x'],
)
def test_static_labels_are_accepted(label):
    assert require_operation_label(label) == label


def test_composite_pull_label_is_accepted_for_a_real_shard():
    shards = config_batch_pipeline.SCHEDULER_SHARDS
    assert (
        require_operation_label(f'batch_pull shard=scheduler_{shards - 1:02d}')
        == f'batch_pull shard=scheduler_{shards - 1:02d}'
    )


def test_composite_claim_label_is_accepted_for_a_real_shard():
    assert require_operation_label('batch_claim shard=scheduler_00') == 'batch_claim shard=scheduler_00'


@pytest.mark.parametrize(
    'label',
    [
        None,
        '',
        'BATCH_FAIL',
        'batch fail',
        'batch-fail',
        'batch_fail; drop',
        '9batch',
        'batch_pull shard=scheduler_99',
        'batch_pull shard=scheduler_',
        'x' * 65,
    ],
)
def test_unattributable_labels_are_refused(label):
    with pytest.raises(ValueError):
        require_operation_label(label)


def test_max_length_label_is_accepted():
    assert require_operation_label('x' * 64) == 'x' * 64


def test_anonymous_store_run_is_refused_before_the_client_is_touched(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client = Mock()
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client, storm_damper=make_damper()[0])
    with pytest.raises(ValueError):
        store.run(lambda tx: True)
    client.transaction.assert_not_called()


def test_ambient_store_operation_context_labels_the_run(monkeypatch):
    deterministic_chain(monkeypatch)
    damper, _ = make_damper()
    store = build_store(monkeypatch, damper=damper, client=WaveClient(hot_commits=0))
    with store_operation('batch_recover'):
        assert store.run(lambda tx: 'via-context') == 'via-context'
    assert current_operation() is None


def test_explicit_operation_wins_over_the_ambient_context(monkeypatch):
    deterministic_chain(monkeypatch)
    store = build_store(monkeypatch, damper=make_damper()[0], client=WaveClient(hot_commits=0))
    with store_operation('batch_recover'):
        assert store.run(lambda tx: 'explicit', operation='batch_fail') == 'explicit'


def test_store_operation_context_resets_after_an_exception():
    with pytest.raises(RuntimeError):
        with store_operation('batch_recover'):
            raise RuntimeError('body failed')
    assert current_operation() is None


def test_shadow_operation_whitelist_is_unchanged():
    with shadow_operation('offer'):
        assert current_operation() == 'batch_shadow_offer'
    with pytest.raises(ValueError):
        with shadow_operation('not_a_shadow_op'):
            pass


def test_pull_operation_only_allows_claim_and_pull():
    with pull_operation('pull', 'scheduler_03'):
        assert current_operation() == 'batch_pull shard=scheduler_03'
    with pytest.raises(ValueError):
        with pull_operation('claimx', 'scheduler_03'):
            pass
    with pytest.raises(ValueError):
        with pull_operation('pull', 'scheduler_99'):
            pass


def test_nested_store_operation_restores_the_outer_label():
    with store_operation('batch_recover'):
        with store_operation('batch_fail'):
            assert current_operation() == 'batch_fail'
        assert current_operation() == 'batch_recover'
    assert current_operation() is None


# --------------------------------------------------------------------------
# Section F — the chain the store runs is the real wave-bridged budget
# --------------------------------------------------------------------------


def test_store_run_chain_uses_the_documented_default_budget(monkeypatch):
    seen = {}

    actual = storage.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        seen['max_attempts'] = kwargs.get('max_attempts', 5)
        seen['operation_name'] = kwargs['operation_name']
        kwargs.setdefault('sleep', lambda _seconds: None)
        kwargs.setdefault('random_value', lambda: 1.0)
        return actual(*args, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', factory)
    store = build_store(monkeypatch, damper=make_damper()[0], client=StormClient())
    with pytest.raises(FirestoreContentionExhausted):
        store.run(lambda tx: True, operation='batch_fail')
    assert seen['operation_name'] == 'batch_fail'
    assert seen['max_attempts'] == 5


def test_store_run_returns_the_body_result_verbatim(monkeypatch):
    deterministic_chain(monkeypatch)
    payload = {'entry': 'x', 'log_sequence': 1}
    store = build_store(monkeypatch, damper=make_damper()[0], client=WaveClient(hot_commits=2))
    assert store.run(lambda tx: payload, operation='batch_merge_commit') == payload


def test_wave_client_transactions_are_fresh_per_attempt(monkeypatch):
    deterministic_chain(monkeypatch)
    client = WaveClient(hot_commits=2)
    store = build_store(monkeypatch, damper=make_damper()[0], client=client)
    store.run(lambda tx: True, operation='batch_merge_commit')
    assert client.minted == 3  # no same-id replay: a fresh transaction per attempt


def test_namespace_contract_is_unchanged(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    with pytest.raises(ValueError):
        storage.FirestoreStore('other_namespace', firestore_client=Mock())
    storage.FirestoreStore('batch_pipeline_dev', firestore_client=Mock())
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    storage.FirestoreStore('batch_pipeline_prod', firestore_client=Mock())
