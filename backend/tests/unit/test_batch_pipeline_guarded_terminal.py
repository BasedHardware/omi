"""Guarded terminal no-speech requires every recognizer's empty receipt."""

from copy import deepcopy

import pytest

from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row
from tests.unit.test_batch_pipeline_terminal_empty import terminal_setup, historical, load_operator
from tests.unit.test_batch_pipeline_empty_disposition import SERVING_ENV
from config.batch_language_recovery import guarded_exhausted
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_terminal_empty import TerminalEmptyStore, intent_snapshot
from utils.batch_pipeline.recovery_disposition import LANGUAGE_GUARD_EMPTY_EVIDENCE, result_outcome


def receipts(kind='both_empty'):
    both = {
        'modulate': {'provider': 'modulate', 'outcome': 'empty', 'word_count': 0, 'vad_speech_seconds': 1.0},
        'soniox': {'provider': 'soniox', 'outcome': 'empty', 'word_count': 0, 'vad_speech_seconds': 1.0},
    }
    if kind == 'modulate_only':
        both.pop('soniox')
    elif kind == 'soniox_words':
        both['soniox'] = {'provider': 'soniox', 'outcome': 'words', 'word_count': 3, 'vad_speech_seconds': 1.0}
    elif kind == 'soniox_error':
        both['soniox'] = {'provider': 'soniox', 'outcome': 'error', 'word_count': None, 'vad_speech_seconds': 1.0}
    elif kind == 'soniox_refused':
        both['soniox'] = {'provider': 'soniox', 'outcome': 'refused', 'word_count': None, 'vad_speech_seconds': 1.0}
    elif kind == 'modulate_words':
        both['modulate'] = {'provider': 'modulate', 'outcome': 'words', 'word_count': 3, 'vad_speech_seconds': 1.0}
    return {} if kind == 'none' else both


def guarded_setup(setup, monkeypatch, legacy_dependencies, *, kind='both_empty', spans=(0, 5)):
    """A guarded failed_held unit with epoch-1 modulate empty and recorded receipts."""
    client, store, binding, artifacts, legacy, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    job = row(client)
    historical(client)
    job['recovery']['provider'] = 'modulate'
    job['worker_failure'] = {'stage': 'vad_windows', 'reason': 'unsupported_language'}
    if kind != 'none':
        job['recovery']['recognizers'] = receipts(kind)
    monkeypatch.setattr(
        legacy_dependencies[1],
        'offline_pcm_speech_segments',
        lambda _: [{'start': spans[0], 'end': spans[1]}] if spans else [],
    )
    return client, store, binding, artifacts, legacy, alternate


@pytest.mark.parametrize(
    'kind', ['modulate_only', 'none', 'soniox_words', 'soniox_error', 'soniox_refused', 'modulate_words']
)
def test_guarded_exhausted_requires_both_empty_receipts(kind):
    assert guarded_exhausted({'recovery': {'recognizers': receipts()}})
    assert not guarded_exhausted({'recovery': {'recognizers': receipts(kind)}})
    assert not guarded_exhausted({'recovery': {}})
    assert not guarded_exhausted({})


def test_guarded_terminal_settles_no_recoverable_speech_with_recorded_evidence(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, legacy, alternate = guarded_setup(setup, monkeypatch, legacy_dependencies)
    module = load_operator()
    key = module.fingerprint(row(client))
    assert module.inspect_unit(store, artifacts, 'bad', binding.owner_id, key, False) == 'no_recoverable_speech'
    assert (
        module.apply_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            key,
            'no_recoverable_speech',
            'plan',
            False,
            None,
            server_flags=SERVING_ENV,
        )
        == 'completed'
    )
    job = row(client)
    assert job['result']['outcome'] == 'no_recoverable_speech'
    assert job['terminal_disposition']['state'] == 'completed'
    assert job['recovery_state'] == 'recovered' and job['state'] == 'result_ready'
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert result_outcome(payload) == 'no_recoverable_speech'
    assert payload['recognition_evidence'] == LANGUAGE_GUARD_EMPTY_EVIDENCE
    assert (
        module.apply_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            key,
            'no_recoverable_speech',
            'plan',
            False,
            None,
            server_flags=SERVING_ENV,
        )
        == 'already_applied'
    )
    legacy.assert_not_called()
    alternate.assert_not_called()


@pytest.mark.parametrize(
    'kind', ['modulate_only', 'none', 'soniox_words', 'soniox_error', 'soniox_refused', 'modulate_words']
)
def test_guarded_terminal_refuses_without_full_empty_evidence(setup, monkeypatch, legacy_dependencies, kind):
    client, store, binding, artifacts, legacy, alternate = guarded_setup(
        setup, monkeypatch, legacy_dependencies, kind=kind
    )
    module = load_operator()
    key = module.fingerprint(row(client))
    with pytest.raises(module.held.Refused):
        module.inspect_unit(store, artifacts, 'bad', binding.owner_id, key, False)
    with pytest.raises(ProjectionBlocked):
        TerminalEmptyStore(store, server_flags=SERVING_ENV).prepare(
            'bad', binding.owner_id, 'plan', intent_snapshot(row(client)), 'no_recoverable_speech', False, 100
        )
    assert not row(client).get('terminal_disposition')
    legacy.assert_not_called()
    alternate.assert_not_called()


def test_guarded_silence_still_requires_independent_proof(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, alternate = guarded_setup(setup, monkeypatch, legacy_dependencies, spans=())
    module = load_operator()
    key = module.fingerprint(row(client))
    with pytest.raises(module.held.Refused):
        module.inspect_unit(store, artifacts, 'bad', binding.owner_id, key, False)
    alternate.assert_not_called()


def test_guarded_canary_route_still_refused(setup, monkeypatch, legacy_dependencies):
    client, store, binding, *_ = guarded_setup(setup, monkeypatch, legacy_dependencies)
    with pytest.raises(ProjectionBlocked):
        TerminalEmptyStore(store, server_flags=SERVING_ENV).prepare(
            'bad', binding.owner_id, 'plan', intent_snapshot(row(client)), 'canary_recovery', False, 100
        )


def test_guarded_dry_run_is_read_only(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, legacy, alternate = guarded_setup(setup, monkeypatch, legacy_dependencies)
    module = load_operator()
    before = deepcopy(client.rows)
    assert (
        module.inspect_unit(store, artifacts, 'bad', binding.owner_id, module.fingerprint(row(client)), False)
        == 'no_recoverable_speech'
    )
    assert client.rows == before
    artifacts.persist_recovery_result.assert_not_called()
    legacy.assert_not_called()
    alternate.assert_not_called()


def test_runtime_exhausted_guarded_unit_settles_through_the_terminal_plan(setup, monkeypatch, legacy_dependencies):
    """The live path: the runtime records both empty receipts, then the operator plan settles the unit."""
    from tests.unit.test_batch_language_recovery import guarded as runtime_guarded

    monkeypatch.setenv('BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED', 'true')
    client, store, binding, artifacts, modulate, soniox, recovery, _ = runtime_guarded(
        setup, monkeypatch, legacy_dependencies
    )
    transaction = client.transaction
    monkeypatch.setattr(client, 'transaction', lambda **kwargs: transaction())
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    job = row(client)
    assert job['recovery']['recognizers'] == {
        provider: {'provider': provider, 'outcome': 'empty', 'word_count': 0, 'vad_speech_seconds': 1}
        for provider in ('modulate', 'soniox')
    }
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    job['worker_empty_evidence'] = {'padded_retry': 'empty', 'version': 1}
    module = load_operator()
    key = module.fingerprint(job)
    assert module.inspect_unit(store, artifacts, 'bad', binding.owner_id, key, False) == 'no_recoverable_speech'
    assert (
        module.apply_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            key,
            'no_recoverable_speech',
            'plan',
            False,
            None,
            server_flags=SERVING_ENV,
        )
        == 'completed'
    )
    settled = row(client)
    assert settled['result']['outcome'] == 'no_recoverable_speech'
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert payload['recognition_evidence'] == LANGUAGE_GUARD_EMPTY_EVIDENCE
    modulate.assert_called_once()
    soniox.assert_called_once()
