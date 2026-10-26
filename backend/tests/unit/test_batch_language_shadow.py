"""Qualification uses private control tables and never serving jobs or routes."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import batch_pipeline_store as storage
from database.batch_pipeline_language_shadow import LanguageShadowStore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline.contracts import WorkItem, Priority
from utils.batch_pipeline import language_shadow


@pytest.fixture
def repository(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '100')
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_LANGUAGE_ONLY', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_LANGUAGE_PROBES_PER_HOUR', '500')
    monkeypatch.setattr(storage, 'assert_batch_write_allowed', lambda *a, **kw: 3)
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=StrictFirestore())
    return LanguageShadowStore(store, clock=lambda: 7200)


def item(name='one'):
    return WorkItem(
        name,
        'synthetic-owner',
        0,
        'intake:synthetic',
        1,
        Priority.DEEP,
        shadow=True,
        privacy_generation=3,
        conversation_id='synthetic-conversation',
    )


def test_duplicate_and_hour_rollover_never_repeat_an_intent(repository):
    assert repository.reserve(item())
    repository.release(item())
    assert not repository.reserve(item())
    repository.clock = lambda: 10800
    assert not repository.reserve(item())
    assert repository.reserve(item('new-hour'))
    assert repository.store.run(lambda tx: tx.get('jobs', 'one')) == {}
    assert repository.store.run(lambda tx: tx.get('shadow_jobs', 'one')) == {}


def test_hourly_cap_is_shared_by_separate_replicas(repository, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_LANGUAGE_PROBES_PER_HOUR', '2')
    assert repository.reserve(item())
    repository.release(item())
    other = LanguageShadowStore(repository.store, clock=lambda: 7260)
    assert other.reserve(item('two'))
    other.release(item('two'))
    other.clock = lambda: 7320
    assert not other.reserve(item('three'))


def test_two_inflight_slots_and_expiry_bound_work(repository):
    assert repository.reserve(item())
    assert repository.reserve(item('two'))
    assert not repository.reserve(item('three'))
    assert repository.authorize(item())
    repository.clock = lambda: 7321
    assert not repository.authorize(item())
    assert not repository.reserve(item('three'))
    # A deadline revokes new calls, but cannot recycle a decoder/request still
    # running under its original owner. Only its completion frees the slot.
    repository.release(item())
    assert repository.reserve(item('three'))
    # A late release cannot revoke the new occupant of an expired slot.
    repository.release(item())
    assert repository.authorize(item('three'))


def test_fresh_privacy_is_checked_at_reservation_and_before_each_call(repository, monkeypatch):
    check = Mock(return_value=3)
    monkeypatch.setattr(storage, 'assert_batch_write_allowed', check)
    assert repository.reserve(item())
    assert repository.authorize(item())
    assert check.call_args.args[2] == item().owner_id
    assert check.call_args.kwargs == {'conversation_ids': (item().conversation_id,), 'expected_generation': 3}
    assert check.call_count == 2
    check.side_effect = RuntimeError('privacy revoked')
    with pytest.raises(RuntimeError, match='privacy revoked'):
        repository.authorize(item())
    assert not repository.reserve(item('privacy-denied'))


@pytest.mark.parametrize('setting', ['0', '-1', 'bad'])
def test_malformed_or_zero_cap_never_reserves(repository, monkeypatch, setting):
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_LANGUAGE_PROBES_PER_HOUR', setting)
    assert not repository.reserve(item())


def test_lost_commit_response_is_not_permission_to_retry(repository, monkeypatch):
    run = repository.store.run

    def ambiguous(body):
        run(body)
        raise TimeoutError('reply lost after commit')

    monkeypatch.setattr(repository.store, 'run', ambiguous)
    assert not repository.reserve(item())
    monkeypatch.setattr(repository.store, 'run', run)
    assert not repository.reserve(item())


def test_global_kill_switch_stops_authorization(repository, monkeypatch):
    assert repository.reserve(item())
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '0')
    assert not repository.authorize(item())
    assert not repository.reserve(item('two'))


def test_probe_callback_requires_fresh_funding_for_each_external_call(monkeypatch):
    repo = SimpleNamespace(authorize=Mock(return_value=True))
    funded = Mock(side_effect=[True, False])
    monkeypatch.setattr(language_shadow, 'language_only_enabled', lambda: True)
    monkeypatch.setattr(language_shadow, 'sync_allowed', funded)

    def paired(_audio, *, before_call):
        assert before_call()
        assert not before_call()
        return False

    monkeypatch.setattr(language_shadow, 'compare_shadow_pair', paired)
    assert not language_shadow.compare(repo, item(), SimpleNamespace(wav=b'synthetic', duration_seconds=90))
    assert repo.authorize.call_count == 2
    assert funded.call_count == 2
    assert funded.call_args.kwargs == {'lane': 'batch'}
    assert funded.call_args.args[1] == 30


def test_decoder_closes_after_the_first_canonical_unit(monkeypatch):
    closed = []
    first = SimpleNamespace(wav=b'canonical-first')

    def units(paths, *, max_seconds):
        try:
            yield first
            raise AssertionError('qualifier must not decode a second unit')
        finally:
            closed.append(True)

    monkeypatch.setattr(language_shadow, 'decode_units', units)
    monkeypatch.setattr(language_shadow, 'validate_language_probe_paths', lambda _: None)
    assert language_shadow.first_unit(['synthetic']) is first
    assert closed == [True]


def test_large_upload_never_enters_canonical_decode(monkeypatch, tmp_path):
    import struct
    from utils.sync.input_limits import BackfillInputLimitExceeded

    path = tmp_path / 'audio_omi_opus_16000_1_fs1920_1710000000.bin'
    path.write_bytes((struct.pack('<I', 1) + b'\0') * 501)
    decoder = Mock(side_effect=AssertionError('must refuse before expansion'))
    monkeypatch.setattr(language_shadow, 'decode_units', decoder)
    with pytest.raises(BackfillInputLimitExceeded):
        language_shadow.first_unit([str(path)])
    decoder.assert_not_called()


def test_bounded_probe_preserves_the_actual_canonical_first_unit(tmp_path):
    import struct
    from utils.batch_pipeline.capture_decode import decode_units
    from config.batch_pipeline_providers import provider_config

    def bundle(name):
        directory = tmp_path / name
        directory.mkdir()
        paths = []
        for offset in range(2):
            path = directory / f'audio_phonemic_pcm16_16000_1_fs160_{1710000000 + offset}.bin'
            path.write_bytes((struct.pack('<I', 320) + b'\x01\x00' * 160) * 100)
            paths.append(str(path))
        return paths

    expected = list(decode_units(bundle('normal'), max_seconds=provider_config().max_unit_seconds))[0]
    observed = language_shadow.first_unit(bundle('qualification'))
    assert observed.wav == expected.wav
    assert observed.capture_at == expected.capture_at and observed.duration_seconds == expected.duration_seconds


@pytest.mark.asyncio
async def test_language_only_hook_never_enters_the_gpu_shadow(monkeypatch):
    from utils.batch_pipeline import shadow_intake

    offered = []

    async def language_offer(**kw):
        offered.append(kw)

    monkeypatch.setattr(shadow_intake, 'language_only_enabled', lambda: True)
    monkeypatch.setattr(language_shadow, 'offer_upload', language_offer)
    monkeypatch.setattr(shadow_intake, 'repository_for_stage', Mock(side_effect=AssertionError('GPU rendezvous')))
    await shadow_intake.offer_upload(
        uid='synthetic',
        content_id='synthetic',
        paths=[],
        lane='fresh',
        age=0,
        conversation_id=None,
        source='test',
        device_id=None,
        byok=False,
        policy=object(),
    )
    assert len(offered) == 1


@pytest.mark.asyncio
async def test_offer_and_pair_task_only_write_qualification_control_and_remove_private_copies(
    repository, monkeypatch, tmp_path
):
    from utils.batch_pipeline import shadow_intake

    directory = tmp_path / 'private-shadow'

    async def inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    def authorize(_store, _item, *, snapshots):
        snapshots['user'] = {'language': 'en', 'transcription_preferences': {}}
        return SimpleNamespace(generation=3)

    def copies(_paths):
        directory.mkdir()
        (directory / 'owned-copy').write_bytes(b'synthetic-only')
        return str(directory), [str(directory / 'owned-copy')]

    monkeypatch.setattr(language_shadow, 'selected', lambda *_: True)
    monkeypatch.setattr(language_shadow, 'run_blocking', inline)
    monkeypatch.setattr(language_shadow, 'batch_artifact_authorize', authorize)
    monkeypatch.setattr(language_shadow, 'validate_language_probe_paths', lambda _: None)
    monkeypatch.setattr(language_shadow, 'LanguageShadowStore', lambda _store: repository)
    monkeypatch.setattr(shadow_intake, 'repository_for_stage', lambda: SimpleNamespace(store=repository.store))
    monkeypatch.setattr(shadow_intake, 'copy_paths', copies)
    monkeypatch.setattr(language_shadow, 'first_unit', lambda _: SimpleNamespace(wav=b'canonical', duration_seconds=30))
    monkeypatch.setattr(language_shadow, 'sync_allowed', lambda *_a, **_kw: True)

    def compare(_wav, *, before_call):
        assert before_call() and before_call()
        return True

    monkeypatch.setattr(language_shadow, 'compare_shadow_pair', compare)
    await language_shadow.offer_upload(
        uid=item().owner_id,
        content_id='immutable-upload',
        paths=['legacy-owned'],
        conversation_id=item().conversation_id,
        byok=False,
        policy=object(),
    )
    assert not directory.exists()
    assert all(
        path[0] in {'batch_pipeline_dev_shadow_lid_probes', 'batch_pipeline_dev_shadow_lid_spend'}
        for path in repository.store.client.rows
    )
    # The same immutable upload cannot become a second qualification observation.
    await language_shadow.offer_upload(
        uid=item().owner_id,
        content_id='immutable-upload',
        paths=['legacy-owned'],
        conversation_id=item().conversation_id,
        byok=False,
        policy=object(),
    )
    assert not directory.exists()
