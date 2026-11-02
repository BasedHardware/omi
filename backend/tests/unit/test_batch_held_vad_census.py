"""Every recovery route preserves positive held speech, including lost-result replay."""

from unittest.mock import Mock
from types import SimpleNamespace

import pytest

from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_quarantine_recovery import SilenceDispositionStore
from database.batch_pipeline_speech_redrive import SpeechRedriveStore
from database.batch_pipeline_terminal_empty import TerminalEmptyStore, intent_snapshot
from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row
from tests.unit.test_batch_pipeline_empty_disposition import enable, spent, wav, SERVING_ENV
from tests.unit.test_batch_pipeline_speech_redrive import enabled
from tests.unit.test_batch_pipeline_terminal_empty import terminal_setup, historical
from tests.unit.test_batch_pipeline_shadow import repository, running, row as shadow_row
from utils.batch_pipeline.contracts import ValidationFailureWork
from utils.batch_pipeline.recovery_recognizers import transcribe
from utils.batch_pipeline.recovery_disposition import silence_payload
from utils.batch_pipeline.speech_redrive import redrive_one
from utils.batch_pipeline.shadow_recovery import recover as shadow_recover
from tests.unit.test_batch_language_recovery import guarded


def test_ordinary_cpu_zero_cannot_discharge_worker_speech(setup, monkeypatch, legacy_dependencies):
    client, _, binding, artifacts, _, recovery = setup
    provider = enable(monkeypatch, legacy_dependencies)
    artifacts.fetch_audio.return_value = wav()
    recovery.stt = transcribe
    row(client)['measured_held_vad_speech_seconds'] = 2
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    assert row(client)['measured_held_vad_speech_seconds'] == 2
    assert not row(client).get('result')
    artifacts.persist_recovery_result.assert_not_called()
    provider.assert_not_called()


@pytest.mark.parametrize('prior,expected', [(None, 'reconciled'), (2, 'failed_held')])
def test_ordinary_saved_zero_is_evidence_but_never_erases_speech(
    setup, monkeypatch, legacy_dependencies, prior, expected
):
    client, _, binding, artifacts, _, recovery = setup
    provider = enable(monkeypatch, legacy_dependencies)
    row(client)['measured_held_vad_speech_seconds'] = prior
    job = recovery.protocol.prepare('bad', binding.owner_id, 100)
    assert recovery.protocol.start('bad', job['recovery']['token'], 100, provider='modulate')
    artifacts.find_recovery_result.return_value = 'gs://synthetic/silence'
    artifacts.load_result.return_value = silence_payload(5)
    assert recovery.recover('bad', binding.owner_id) == expected
    assert row(client)['measured_held_vad_speech_seconds'] == (0 if prior is None else prior)
    assert bool(row(client).get('result')) == (expected == 'reconciled')
    artifacts.fetch_audio.assert_not_called()
    provider.assert_not_called()


@pytest.mark.parametrize('operator', [False, True])
@pytest.mark.parametrize('prior,incoming,allowed', [(None, None, False), (None, 0, True), (2, 0, False)])
def test_atomic_silence_fence_covers_ordinary_and_paid_recovery(
    setup, monkeypatch, legacy_dependencies, operator, prior, incoming, allowed
):
    client, store, binding, _, _, recovery = setup
    if operator:
        *_, old = enabled(setup, monkeypatch, legacy_dependencies)
        protocol = SpeechRedriveStore(store, server_flags=SERVING_ENV)
        job = protocol.prepare('bad', binding.owner_id, 'plan', old, 100)
        token = job['speech_redrive']['token']
        assert protocol.start('bad', token, 'plan', 100)
    else:
        enable(monkeypatch, legacy_dependencies)
        protocol = recovery.protocol
        job = protocol.prepare('bad', binding.owner_id, 100)
        token = job['recovery']['token']
        assert protocol.start('bad', token, 100, provider='modulate')
    # This may arrive after the caller loaded its result: the transaction owns the fence.
    row(client)['measured_held_vad_speech_seconds'] = prior
    arguments = ('bad', token, 'plan', 101) if operator else ('bad', token, 101)
    assert (
        protocol.settle(
            *arguments, 'gs://synthetic/silence', outcome='silence', measured_held_vad_speech_seconds=incoming
        )
        is allowed
    )
    assert row(client)['measured_held_vad_speech_seconds'] == (0 if allowed else prior)
    assert bool(row(client).get('result')) is allowed


@pytest.mark.parametrize('race', [False, True])
def test_no_provider_silence_cannot_clear_positive_census(setup, monkeypatch, legacy_dependencies, race):
    client, store, binding, _, _, _ = setup
    enable(monkeypatch, legacy_dependencies)
    old = spent(client)
    protocol = SilenceDispositionStore(store, server_flags=SERVING_ENV)
    if not race:
        row(client)['measured_held_vad_speech_seconds'] = 2
        with pytest.raises(ProjectionBlocked):
            protocol.prepare_silence('bad', binding.owner_id, 'plan', 100)
    else:
        job = protocol.prepare_silence('bad', binding.owner_id, 'plan', 100)
        row(client)['measured_held_vad_speech_seconds'] = 2
        assert not protocol.complete_silence(
            'bad',
            job['silence_disposition']['token'],
            'plan',
            'gs://synthetic/silence',
            101,
            measured_held_vad_speech_seconds=0,
        )
    assert row(client)['measured_held_vad_speech_seconds'] == 2
    assert row(client)['recovery'] == old and not row(client).get('result')


@pytest.mark.parametrize('route', ['silent_only', 'terminal'])
def test_legacy_no_provider_disposition_cannot_bypass_language_guard(setup, monkeypatch, legacy_dependencies, route):
    client, store, binding, *_ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    historical(client)
    row(client)['worker_failure'] = {'stage': 'vad_windows', 'reason': 'unsupported_language'}
    with pytest.raises(ProjectionBlocked):
        if route == 'silent_only':
            SilenceDispositionStore(store, server_flags=SERVING_ENV).prepare_silence(
                'bad', binding.owner_id, 'plan', 100
            )
        else:
            TerminalEmptyStore(store, server_flags=SERVING_ENV).prepare(
                'bad', binding.owner_id, 'plan', intent_snapshot(row(client)), 'silence', True, 100
            )
    assert not row(client).get('result')


@pytest.mark.parametrize('race', [False, True])
def test_terminal_silence_preserves_prior_speech(setup, monkeypatch, legacy_dependencies, race):
    client, store, binding, *_ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    historical(client)
    protocol = TerminalEmptyStore(store, server_flags=SERVING_ENV)
    if not race:
        row(client)['measured_held_vad_speech_seconds'] = 2
        with pytest.raises(ProjectionBlocked):
            protocol.prepare('bad', binding.owner_id, 'plan', intent_snapshot(row(client)), 'silence', True, 100)
    else:
        job = protocol.prepare('bad', binding.owner_id, 'plan', intent_snapshot(row(client)), 'silence', True, 100)
        row(client)['measured_held_vad_speech_seconds'] = 2
        assert not protocol.complete(
            'bad',
            job['terminal_disposition']['token'],
            'plan',
            'gs://synthetic/silence',
            101,
            measured_held_vad_speech_seconds=0,
        )
    assert row(client)['measured_held_vad_speech_seconds'] == 2
    assert not row(client).get('result')


@pytest.mark.parametrize('new,expected', [(0.5, 2), (4, 4)])
def test_terminal_exhaustion_keeps_maximum_measurement(setup, monkeypatch, legacy_dependencies, new, expected):
    client, store, binding, *_ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    historical(client)
    row(client)['measured_held_vad_speech_seconds'] = 2
    protocol = TerminalEmptyStore(store, server_flags=SERVING_ENV)
    job = protocol.prepare(
        'bad', binding.owner_id, 'plan', intent_snapshot(row(client)), 'no_recoverable_speech', True, 100
    )
    assert protocol.complete(
        'bad',
        job['terminal_disposition']['token'],
        'plan',
        'gs://synthetic/exhausted',
        101,
        measured_held_vad_speech_seconds=new,
    )
    assert row(client)['measured_held_vad_speech_seconds'] == expected


@pytest.mark.parametrize('outcome,vad', [('error', 'unknown'), ('empty', 'strict')])
def test_shadow_settlement_never_erases_speech(repository, outcome, vad):
    item = running(repository, duration=20)
    repository.store.run(
        lambda tx: tx.put(
            'shadow_jobs',
            item.segment_id,
            {**tx.get('shadow_jobs', item.segment_id), 'measured_held_vad_speech_seconds': 2},
        )
    )
    repository.finish(item.segment_id, outcome, speech=0, vad=vad)
    final = shadow_row(repository, item.segment_id)
    assert final['speech_seconds'] == final['speech_loss_seconds'] == 2
    if outcome == 'empty':
        assert final['outcome'] == 'failed_held'


def test_shadow_handoff_preserves_an_existing_higher_measurement(repository):
    item = running(repository, duration=20)
    repository.store.run(
        lambda tx: tx.put(
            'shadow_jobs',
            item.segment_id,
            {**tx.get('shadow_jobs', item.segment_id), 'state': 'running', 'measured_held_vad_speech_seconds': 2},
        )
    )
    assert repository.handoff(
        item.segment_id, ValidationFailureWork(item.segment_id, 'vad_windows', 'unsupported_language', 0)
    )
    assert shadow_row(repository, item.segment_id)['measured_held_vad_speech_seconds'] == 2


@pytest.mark.parametrize('prior,expected', [(None, 'reconciled'), (2, 'failed_held')])
def test_paid_saved_zero_never_erases_speech(setup, monkeypatch, legacy_dependencies, prior, expected):
    client, store, binding, artifacts, legacy, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    protocol = SpeechRedriveStore(store, server_flags=SERVING_ENV)
    job = protocol.prepare('bad', binding.owner_id, 'plan', old, 100)
    assert protocol.start('bad', job['speech_redrive']['token'], 'plan', 100)
    row(client)['measured_held_vad_speech_seconds'] = prior
    artifacts.find_recovery_result.return_value = 'gs://synthetic/silence'
    artifacts.load_result.return_value = silence_payload(5)
    assert redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV) == expected
    assert row(client)['measured_held_vad_speech_seconds'] == (0 if prior is None else prior)
    artifacts.fetch_audio.assert_not_called()
    legacy.assert_not_called()
    alternate.assert_not_called()


@pytest.mark.parametrize('outcome', ['silence', 'no_recoverable_speech', 'canary_recovery'])
def test_terminal_routes_cannot_bypass_independent_guard(setup, monkeypatch, legacy_dependencies, outcome):
    client, store, binding, *_ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    historical(client, canary=outcome == 'canary_recovery')
    row(client)['worker_failure'] = {'stage': 'vad_windows', 'reason': 'unsupported_language'}
    with pytest.raises(ProjectionBlocked, match='independent recovery required'):
        TerminalEmptyStore(store, server_flags=SERVING_ENV).prepare(
            'bad', binding.owner_id, 'plan', intent_snapshot(row(client)), outcome, True, 100
        )
    assert not row(client).get('terminal_disposition')


@pytest.mark.parametrize('operator', [False, True])
def test_atomic_exhaustion_cannot_bypass_guard_and_retains_new_evidence(
    setup, monkeypatch, legacy_dependencies, operator
):
    client, store, binding, _, _, _, recovery, old = guarded(
        setup, monkeypatch, legacy_dependencies, automatic=not operator
    )
    row(client)['measured_held_vad_speech_seconds'] = 1
    if operator:
        protocol = SpeechRedriveStore(store, server_flags=SERVING_ENV)
        job = protocol.prepare('bad', binding.owner_id, 'plan', old, 100)
        token = job['speech_redrive']['token']
        assert protocol.start('bad', token, 'plan', 100)
        arguments = ('bad', token, 'plan', 101)
    else:
        protocol = recovery.protocol
        job = protocol.prepare('bad', binding.owner_id, 100)
        token = job['recovery']['token']
        assert protocol.start('bad', token, 100, provider='modulate')
        arguments = ('bad', token, 101)
    assert not protocol.settle(
        *arguments, 'gs://synthetic/exhausted', outcome='no_recoverable_speech', measured_held_vad_speech_seconds=2
    )
    assert row(client)['measured_held_vad_speech_seconds'] == 2
    assert not row(client).get('result')


@pytest.mark.parametrize('route', ['silent_only', 'terminal'])
def test_lost_disposition_owner_cannot_write_vad(setup, monkeypatch, legacy_dependencies, route):
    client, store, binding, *_ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    historical(client)
    if route == 'silent_only':
        protocol = SilenceDispositionStore(store, server_flags=SERVING_ENV)
        job = protocol.prepare_silence('bad', binding.owner_id, 'plan', 100)
        marker = job['silence_disposition']
        row(client)['silence_disposition']['state'] = 'cancelled'
        operation = lambda: protocol.complete_silence(
            'bad', marker['token'], 'plan', 'gs://synthetic/silence', 101, measured_held_vad_speech_seconds=4
        )
    else:
        protocol = TerminalEmptyStore(store, server_flags=SERVING_ENV)
        job = protocol.prepare('bad', binding.owner_id, 'plan', intent_snapshot(row(client)), 'silence', True, 100)
        marker = job['terminal_disposition']
        row(client)['terminal_disposition']['state'] = 'cancelled'
        operation = lambda: protocol.complete(
            'bad', marker['token'], 'plan', 'gs://synthetic/silence', 101, measured_held_vad_speech_seconds=4
        )
    row(client)['measured_held_vad_speech_seconds'] = 2
    assert not operation()
    assert row(client)['measured_held_vad_speech_seconds'] == 2


def test_ordinary_shadow_cpu_zero_stays_held(repository):
    item = running(repository, duration=20)
    repository.store.run(
        lambda tx: tx.put(
            'shadow_jobs',
            item.segment_id,
            {**tx.get('shadow_jobs', item.segment_id), 'measured_held_vad_speech_seconds': 2},
        )
    )
    provider = Mock()
    assert (
        shadow_recover(
            repository,
            SimpleNamespace(fetch_audio=lambda _: b'synthetic'),
            item.segment_id,
            stt=provider,
            second_stt=provider,
            inspect=lambda *a: (b'', 20, []),
        )
        == 'failed_held'
    )
    assert shadow_row(repository, item.segment_id)['speech_loss_seconds'] == 2
    provider.assert_not_called()
