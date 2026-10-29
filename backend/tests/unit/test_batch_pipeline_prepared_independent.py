"""Sealed operator take-over of prepared guarded epoch-1 intents above the 60s bound."""

from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import wave
from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row
from tests.unit.test_batch_pipeline_speech_redrive import enabled
from tests.unit.test_batch_pipeline_empty_disposition import SERVING_ENV
from config.batch_language_recovery import MAX_AUDIO_SECONDS, allowed as independent_allowed
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from utils.batch_pipeline.contracts import vad_receipt
from utils.batch_pipeline.recovery_recognizers import transcribe
from utils.batch_pipeline.speech_redrive import prepared_independent_one

WORDS = [{'text': 'Synthetic.', 'timestamp': [1, 2], 'speaker': 'SPEAKER_00'}]
AFTER, CUTOFF = 50.0, 200.0


def wav_seconds(seconds):
    out = io.BytesIO()
    with wave.open(out, 'wb') as handle:
        handle.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        handle.writeframes(b'\0' * int(seconds * 32000))
    return out.getvalue()


def prepared_setup(setup, monkeypatch, legacy_dependencies, *, duration=75.0, speech=0.0):
    """One sealed unit: guarded, epoch-1 prepared, above the runtime 60s bound."""
    client, store, binding, artifacts, legacy, alternate, _ = enabled(setup, monkeypatch, legacy_dependencies)
    job = row(client)
    job.update(
        duration_seconds=duration,
        quarantined_at=100,
        worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'},
        recovery_state='prepared',
        recovery={'token': 'c' * 32, 'epoch': 1, 'privacy_generation': 0, 'prepared_at': 90},
    )
    if speech:
        job['worker_vad_receipt'] = vad_receipt(job['audio_uri'], int(duration * 16000), speech)
    artifacts.fetch_audio.return_value = wav_seconds(duration)
    _, vad, *_ = legacy_dependencies
    monkeypatch.setattr(vad, 'offline_pcm_speech_segments', lambda _: [])
    from utils.stt import soniox_batch

    soniox = Mock(return_value=(WORDS, 'vi'))
    monkeypatch.setattr(soniox_batch, 'transcribe', soniox)
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-only-key')
    monkeypatch.setattr('utils.batch_pipeline.speech_redrive.sync_allowed', lambda *args, **kwargs: True)
    return client, store, binding, artifacts, legacy, alternate, soniox


def load_operator():
    path = Path(__file__).parents[2] / 'scripts'
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    spec = importlib.util.spec_from_file_location('prepared_speech_operator', path / 'batch_pipeline_speech_redrive.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_bound_is_unchanged_and_cannot_be_raised(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS', '190')
    assert MAX_AUDIO_SECONDS == 60.0
    assert independent_allowed(60.0)
    assert not independent_allowed(60.02)
    assert not independent_allowed(75.0)


def duration_limited_unit(setup, monkeypatch, legacy_dependencies):
    """The post-#23795 shape: the runtime refusal-settled >60s prepared guarded unit."""
    client, store, binding, artifacts, legacy, alternate, soniox = prepared_setup(
        setup, monkeypatch, legacy_dependencies, speech=30.0
    )
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS', '190')
    recovery = setup[-1]
    recovery.stt = transcribe
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    job = row(client)
    assert job['recovery_state'] == 'failed_held' and not job.get('result')
    assert not job['recovery'].get('recognizers') and not job['recovery'].get('started_at')
    assert job['recovery']['refusal']['reason'] == 'independent_duration_limit'
    legacy.assert_not_called()
    alternate.assert_not_called()
    soniox.assert_not_called()
    return client, store, binding, artifacts, legacy, alternate, soniox


def test_runtime_duration_limit_still_settles_without_a_provider_call(setup, monkeypatch, legacy_dependencies):
    """#23795 identity: an impossible >60s unit terminally holds with a refusal, even with the flag on and env 190."""
    duration_limited_unit(setup, monkeypatch, legacy_dependencies)


def test_duration_limited_refusal_reopens_through_the_takeover(setup, monkeypatch, legacy_dependencies):
    """A #23795-refused unit is still sealed-plan eligible and recovers via Soniox."""
    client, store, binding, artifacts, legacy, alternate, soniox = duration_limited_unit(
        setup, monkeypatch, legacy_dependencies
    )
    module = load_operator()
    assert module.prepared_eligible(row(client), AFTER, CUTOFF, 190.0)
    assert (
        prepared_independent_one(
            store, artifacts, 'bad', binding.owner_id, 190.0, server_flags=SERVING_ENV, clock=lambda: 200
        )
        == 'recovered'
    )
    job = row(client)
    assert job['recovery_state'] == 'recovered' and job['result']['outcome'] == 'success'
    # The refusal is gone; the take-over spent the same epoch-1 intent and its
    # settle recorded a fresh settled_at.
    assert 'refusal' not in job['recovery']
    assert job['recovery']['provider'] == 'modulate' and job['recovery']['started_at'] == 200
    assert job['recovery']['recognizers']['soniox']['outcome'] == 'words'
    alternate.assert_not_called()
    soniox.assert_called_once()


def test_start_duration_limited_fences_everything_but_the_refusal_shape(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, *_ = duration_limited_unit(setup, monkeypatch, legacy_dependencies)
    token = row(client)['recovery']['token']
    protocol = RecoveryStore(store)
    assert not protocol.start_duration_limited(
        'bad', 'd' * 32, 200, audio_uri='gs://synthetic/audio', audio_seconds=75.0
    )
    assert not protocol.start_duration_limited('bad', token, 200, audio_uri='gs://other/audio', audio_seconds=75.0)
    assert not protocol.start_duration_limited('bad', token, 200, audio_uri='gs://synthetic/audio', audio_seconds=59.0)
    # A spent intent (real failure, no refusal) never reopens.
    row(client)['recovery'].pop('refusal')
    row(client)['recovery']['failure'] = {'stage': 'response_validation', 'reason': 'empty_asr'}
    assert not protocol.start_duration_limited('bad', token, 200, audio_uri='gs://synthetic/audio', audio_seconds=75.0)
    assert row(client)['recovery_state'] == 'failed_held'


def test_takeover_recovers_words_with_worker_vad_evidence(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, legacy, alternate, soniox = prepared_setup(
        setup, monkeypatch, legacy_dependencies, speech=30.0
    )
    frozen = deepcopy(row(client)['recovery'])
    assert (
        prepared_independent_one(
            store, artifacts, 'bad', binding.owner_id, 190.0, server_flags=SERVING_ENV, clock=lambda: 100
        )
        == 'recovered'
    )
    job = row(client)
    assert job['recovery_state'] == 'recovered' and job['state'] == 'result_ready' and job['merge_pending']
    assert job['result']['outcome'] == 'success'
    # The EXISTING epoch-1 intent was spent: same token, no new marker.
    assert job['recovery']['token'] == frozen['token'] and job['recovery']['epoch'] == 1
    assert job['recovery']['provider'] == 'modulate' and job['recovery']['started_at'] == 100
    assert not job.get('speech_redrive')
    receipt = job['recovery']['recognizers']['soniox']
    assert receipt['outcome'] == 'words' and receipt['word_count'] == 1
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert payload['words_provider'] == 'soniox' and payload['speech_seconds'] == 30.0
    assert payload['speech_spans_source'] == 'worker_vad_word_clocks'
    assert soniox.call_count == 1 and soniox.call_args.args[1] == 75.0
    alternate.assert_not_called()
    assert (
        prepared_independent_one(
            store, artifacts, 'bad', binding.owner_id, 190.0, server_flags=SERVING_ENV, clock=lambda: 101
        )
        == 'already_applied'
    )
    soniox.assert_called_once()


def test_takeover_empty_answer_settles_failed_held_without_modulate_receipt(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, legacy, alternate, soniox = prepared_setup(
        setup, monkeypatch, legacy_dependencies
    )
    soniox.return_value = ([], 'vi')
    for _ in range(2):
        assert (
            prepared_independent_one(
                store, artifacts, 'bad', binding.owner_id, 190.0, server_flags=SERVING_ENV, clock=lambda: 100
            )
            == 'failed_held'
        )
    job = row(client)
    assert job['recovery_state'] == 'failed_held' and not job.get('result')
    assert job['recovery']['failure'] == {'stage': 'response_validation', 'reason': 'empty_asr'}
    # The unattempted Modulate side is never fabricated into a receipt.
    assert set(job['recovery']['recognizers']) == {'soniox'}
    assert job['recovery']['recognizers']['soniox'] == {
        'provider': 'soniox',
        'outcome': 'empty',
        'word_count': 0,
        'vad_speech_seconds': 0.0,
    }
    alternate.assert_not_called()
    soniox.assert_called_once()


def test_takeover_provider_error_settles_failed_held(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, alternate, soniox = prepared_setup(setup, monkeypatch, legacy_dependencies)
    soniox.side_effect = TimeoutError('PRIVATE_SENTINEL')
    assert (
        prepared_independent_one(
            store, artifacts, 'bad', binding.owner_id, 190.0, server_flags=SERVING_ENV, clock=lambda: 100
        )
        == 'failed_held'
    )
    job = row(client)
    assert job['recovery']['failure'] == {'stage': 'provider', 'reason': 'provider_failed'}
    assert job['recovery']['recognizers']['soniox']['outcome'] == 'error'
    assert not job.get('result')


def test_takeover_only_admits_the_scoped_bound(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, alternate, soniox = prepared_setup(setup, monkeypatch, legacy_dependencies)
    assert (
        prepared_independent_one(
            store, artifacts, 'bad', binding.owner_id, 70.0, server_flags=SERVING_ENV, clock=lambda: 100
        )
        == 'independent_budget_held'
    )
    assert row(client)['recovery_state'] == 'prepared' and not row(client)['recovery'].get('recognizers')
    soniox.assert_not_called()
    alternate.assert_not_called()


def test_takeover_refuses_units_inside_the_runtime_bound(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, alternate, soniox = prepared_setup(
        setup, monkeypatch, legacy_dependencies, duration=59.0
    )
    assert (
        prepared_independent_one(
            store, artifacts, 'bad', binding.owner_id, 190.0, server_flags=SERVING_ENV, clock=lambda: 100
        )
        == 'independent_budget_held'
    )
    assert row(client)['recovery_state'] == 'prepared'
    soniox.assert_not_called()
    alternate.assert_not_called()


def test_takeover_rechecks_owner_allowance_like_the_runtime(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, alternate, soniox = prepared_setup(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setattr('utils.batch_pipeline.speech_redrive.sync_allowed', lambda *args, **kwargs: False)
    assert (
        prepared_independent_one(
            store, artifacts, 'bad', binding.owner_id, 190.0, server_flags=SERVING_ENV, clock=lambda: 100
        )
        == 'allowance_held'
    )
    assert row(client)['recovery_state'] == 'prepared' and not row(client)['recovery'].get('recognizers')
    soniox.assert_not_called()
    alternate.assert_not_called()


def test_takeover_never_restarts_a_running_intent(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, alternate, soniox = prepared_setup(setup, monkeypatch, legacy_dependencies)
    assert RecoveryStore(store).start('bad', row(client)['recovery']['token'], 99, provider='modulate')
    assert (
        prepared_independent_one(
            store, artifacts, 'bad', binding.owner_id, 190.0, server_flags=SERVING_ENV, clock=lambda: 100
        )
        == 'running_held'
    )
    assert row(client)['recovery_state'] == 'running'
    soniox.assert_not_called()
    alternate.assert_not_called()


def test_uncertain_takeover_reconciles_only_the_artifact(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, alternate, soniox = prepared_setup(
        setup, monkeypatch, legacy_dependencies, speech=30.0
    )
    artifacts.persist_recovery_result.side_effect = RuntimeError('PRIVATE_SENTINEL')
    with pytest.raises(RuntimeError):
        prepared_independent_one(
            store, artifacts, 'bad', binding.owner_id, 190.0, server_flags=SERVING_ENV, clock=lambda: 100
        )
    assert row(client)['recovery_state'] == 'running'
    assert (
        prepared_independent_one(
            store, artifacts, 'bad', binding.owner_id, 190.0, server_flags=SERVING_ENV, clock=lambda: 101
        )
        == 'running_held'
    )
    artifacts.persist_recovery_result.side_effect = None
    artifacts.find_recovery_result.return_value = 'gs://synthetic/reconciled'
    artifacts.load_result.return_value = artifacts.persist_recovery_result.call_args.args[1]
    assert (
        prepared_independent_one(
            store, artifacts, 'bad', binding.owner_id, 190.0, server_flags=SERVING_ENV, clock=lambda: 102
        )
        == 'reconciled'
    )
    assert row(client)['recovery_state'] == 'recovered'
    soniox.assert_called_once()
    alternate.assert_not_called()


@pytest.mark.parametrize(
    'change',
    [
        'none',
        'duration_limited',
        'duration_at_bound',
        'duration_above_scoped',
        'not_guarded',
        'failed_held',
        'running',
        'receipt_present',
        'result',
        'marker',
        'window',
        'epoch',
        'started',
        'spent_failure',
    ],
)
def test_prepared_selection_fence(setup, monkeypatch, legacy_dependencies, change):
    client, *_ = prepared_setup(setup, monkeypatch, legacy_dependencies)
    module = load_operator()
    job = row(client)
    bound = 190.0
    if change == 'duration_at_bound':
        job['duration_seconds'] = 60.0
    elif change == 'duration_above_scoped':
        bound = 70.0
    elif change == 'not_guarded':
        job.pop('worker_failure')
    elif change == 'failed_held':
        job['recovery_state'] = 'failed_held'
    elif change == 'running':
        job['recovery_state'] = 'running'
    elif change == 'receipt_present':
        job['recovery']['recognizers'] = {
            'soniox': {'provider': 'soniox', 'outcome': 'refused', 'word_count': None, 'vad_speech_seconds': 0.0}
        }
    elif change == 'result':
        job['result'] = {'outcome': 'success'}
    elif change == 'marker':
        job['speech_redrive'] = {'state': 'failed_held'}
    elif change == 'window':
        job['quarantined_at'] = 10
    elif change == 'epoch':
        job['recovery']['epoch'] = 2
    elif change == 'started':
        job['recovery']['started_at'] = 95
    elif change == 'duration_limited':
        # The #23795 refusal settlement stays eligible for the sealed plan.
        job['recovery_state'] = 'failed_held'
        job['recovery'].update(
            settled_at=100,
            refusal={'reason': 'independent_duration_limit', 'max_audio_seconds': 60.0, 'audio_seconds': 75.0},
        )
    elif change == 'spent_failure':
        # A settled failure without the refusal is spent, not reopenable.
        job['recovery_state'] = 'failed_held'
        job['recovery'].update(settled_at=100, failure={'stage': 'response_validation', 'reason': 'empty_asr'})
    assert module.prepared_eligible(job, AFTER, CUTOFF, bound) is (change in {'none', 'duration_limited'})


def test_prepared_fingerprint_freezes_the_intent_across_spend(setup, monkeypatch, legacy_dependencies):
    client, *_ = prepared_setup(setup, monkeypatch, legacy_dependencies)
    module = load_operator()
    job = row(client)
    before = module.fingerprint(job, prepared=True)
    # The #23795 refusal settlement appends only settled_at/refusal.
    job['recovery_state'] = 'failed_held'
    job['recovery'].update(
        settled_at=100,
        refusal={'reason': 'independent_duration_limit', 'max_audio_seconds': 60.0, 'audio_seconds': 75.0},
    )
    assert module.fingerprint(job, prepared=True) == before
    # start()/settle()/receipts only append fields to the frozen intent.
    job['recovery'].pop('refusal', None)
    job['recovery'].update(provider='modulate', started_at=100)
    job['recovery']['recognizers'] = {
        'soniox': {'provider': 'soniox', 'outcome': 'empty', 'word_count': 0, 'vad_speech_seconds': 0.0}
    }
    job['recovery'].update(settled_at=101, failure={'stage': 'response_validation', 'reason': 'empty_asr'})
    assert module.fingerprint(job, prepared=True) == before
    job['recovery']['token'] = 'd' * 32
    assert module.fingerprint(job, prepared=True) != before


def test_checked_prepared_revalidates_the_seal(setup, monkeypatch, legacy_dependencies):
    client, store, binding, *_ = prepared_setup(setup, monkeypatch, legacy_dependencies)
    module = load_operator()
    transaction = client.transaction
    monkeypatch.setattr(client, 'transaction', lambda **kwargs: transaction())
    key = module.fingerprint(row(client), prepared=True)
    assert (
        module.checked_prepared(store, 'bad', binding.owner_id, key, AFTER, CUTOFF, 190.0)['recovery_state']
        == 'prepared'
    )
    with pytest.raises(module.held.Refused):
        module.checked_prepared(store, 'bad', binding.owner_id, '0' * 64, AFTER, CUTOFF, 190.0)
    # A foreign state (never prepared by this seal) is a cohort change.
    row(client)['recovery_state'] = 'held'
    with pytest.raises(module.held.Refused):
        module.checked_prepared(store, 'bad', binding.owner_id, key, AFTER, CUTOFF, 190.0)
    # A unit this plan spent replays through the frozen intent token.
    row(client)['recovery_state'] = 'failed_held'
    row(client)['recovery'].update(
        started_at=100, settled_at=101, failure={'stage': 'response_validation', 'reason': 'empty_asr'}
    )
    assert (
        module.checked_prepared(store, 'bad', binding.owner_id, key, AFTER, CUTOFF, 190.0)['recovery_state']
        == 'failed_held'
    )


def test_prepared_budget_enforces_the_granted_cap():
    module = load_operator()
    total, estimated = module.prepared_budget([60.02, 181.02], 3.0)
    assert total == pytest.approx(241.04)
    assert estimated == pytest.approx(241.04 / 3600 * 0.10)
    with pytest.raises(module.held.Refused):
        module.prepared_budget([181.02] * 18, 0.04)
    # An infinite "cap" is not a cap; NaN never satisfies the estimate either.
    with pytest.raises(module.held.Refused):
        module.prepared_budget([75.0], float('inf'))
    with pytest.raises(module.held.Refused):
        module.prepared_budget([75.0], float('nan'))


def test_paid_digest_binds_prepared_scope_and_keeps_legacy_digests_stable():
    module = load_operator()
    legacy = hashlib.sha256(
        json.dumps(
            {
                'operation': module.OPERATION,
                'provider': 'modulate',
                'census_sha256': 'census',
                'speech_count': 18,
                'paid_epoch': 2,
                'silent': False,
            },
            sort_keys=True,
            separators=(',', ':'),
        ).encode()
    ).hexdigest()
    assert module.paid_digest('census', 18, 2) == legacy
    prepared = module.paid_digest('census', 18, 1, prepared=True, max_seconds=190.0, usd_cap=3.0)
    assert prepared != module.paid_digest('census', 18, 1, prepared=True, max_seconds=180.0, usd_cap=3.0)
    assert prepared != module.paid_digest('census', 18, 1, prepared=True, max_seconds=190.0, usd_cap=2.9)
    assert prepared != module.paid_digest('census', 18, 2)


def test_prepared_dry_run_is_read_only_and_downloads_no_audio(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, legacy, alternate, soniox = prepared_setup(
        setup, monkeypatch, legacy_dependencies
    )
    module = load_operator()
    transaction = client.transaction
    seen = []

    def readonly(**kwargs):
        seen.append(kwargs)
        return transaction()

    monkeypatch.setattr(client, 'transaction', readonly)
    before = deepcopy(client.rows)
    key = module.fingerprint(row(client), prepared=True)
    assert (
        module.inspect_unit(store, artifacts, 'bad', binding.owner_id, key, False, False, True, AFTER, CUTOFF, 190.0)
        == 'speech'
    )
    assert seen and all(item == {'read_only': True} for item in seen)
    assert client.rows == before
    artifacts.fetch_audio.assert_not_called()
    artifacts.persist_recovery_result.assert_not_called()
    legacy.assert_not_called()
    alternate.assert_not_called()
    soniox.assert_not_called()
