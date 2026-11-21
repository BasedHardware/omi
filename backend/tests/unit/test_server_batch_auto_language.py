"""Auto-language capture does not turn profile guesses into recognizer authority."""

from types import SimpleNamespace
import hashlib
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor
import asyncio
import threading

import pytest

from config import server_batch
from diarizer.batch_pipeline_models import stt_language
from tests.unit.test_desktop_batch_only import host, capture
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from utils.batch_pipeline.audio import audio_unit
from utils.batch_pipeline.contracts import ValidationFailureWork
from utils.batch_pipeline import record_language
from utils.stt.batch_language import LanguageDecision
from utils.stt.language_gate import SelfVerdict


@pytest.fixture(autouse=True)
def admission_env(monkeypatch):
    monkeypatch.setenv('HOSTED_PUSHER_API_URL', 'http://pusher.invalid')
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true')
    monkeypatch.setenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', '100')
    monkeypatch.delenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', raising=False)
    monkeypatch.delenv('SERVER_BATCH_ONLY_ENABLED', raising=False)


def mobile(language='auto', expected=('en',)):
    row = capture()
    row.update(client_platform='ios', source='omi', language='multi' if language == 'auto' else language)
    h = host(row)
    h.request.source, h.request.language = 'omi', language
    h.language = row['language']
    h.client_device_context = SimpleNamespace(platform='ios')
    # Real LiveLanguageProfile has no declared primary for an auto sentinel.
    h.language_profile = SimpleNamespace(primary='', expected=expected, source='learned')
    return h, row


@pytest.mark.parametrize('language', ['auto', 'multi', '', None])
def test_auto_is_dark_then_admitted_without_guessing_english(monkeypatch, language):
    h, row = mobile(language)
    h.batch_record_capture = {}  # No previous durable admission can bypass the new percentage.
    assert not server_batch.request_eligible(h)
    assert not server_batch.eligible(row, 'owner', batch_admitted=True)
    monkeypatch.setenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', '100')
    assert server_batch.request_eligible(h)
    assert server_batch.eligible(row, 'owner', batch_admitted=True)
    assert not server_batch.suppress_live(h)  # Custody must be reserved first.
    h.batch_record_capture = row
    assert server_batch.suppress_live(h)


@pytest.mark.parametrize('raw', ['0', '-1', 'invalid', 'nan'])
def test_bad_percent_cannot_admit_auto(monkeypatch, raw):
    monkeypatch.setenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', raw)
    h, row = mobile()
    h.batch_record_capture = {}
    assert not server_batch.request_eligible(h)
    assert not server_batch.eligible(row, 'owner', batch_admitted=True)


@pytest.mark.parametrize('expected', [(), ('en', 'ja'), ('ja',), ('en', 'unknown')])
def test_expected_unsupported_or_missing_languages_keep_live(monkeypatch, expected):
    monkeypatch.setenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', '100')
    h, _ = mobile(expected=expected)
    assert not server_batch.request_eligible(h)
    assert not server_batch.suppress_live(h)


def test_profile_must_be_learned_and_mobile_and_nested(monkeypatch):
    monkeypatch.setenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', '100')
    h, row = mobile()
    h.language_profile.source = 'declared'
    assert not server_batch.request_eligible(h)
    h.language_profile.source = 'learned'
    assert not server_batch.eligible(row, 'owner', batch_admitted=False)
    h.client_device_context.platform = 'macos'
    assert not server_batch.request_eligible(h)


@pytest.mark.parametrize('excluded', ['private', 'byok', 'custom', 'call', 'multi_channel', 'onboarding', 'pusher'])
def test_rulings_apply_even_to_reserved_auto_capture(monkeypatch, excluded):
    monkeypatch.setenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', '100')
    h, _ = mobile()
    if excluded == 'private':
        h.private_cloud_sync_enabled = False
    elif excluded == 'byok':
        h.server_batch_byok = True
    elif excluded == 'custom':
        h.use_custom_stt = True
    elif excluded == 'call':
        h.request.source = 'phone_call'
    elif excluded == 'multi_channel':
        h.is_multi_channel = True
    elif excluded == 'onboarding':
        h.request.onboarding_mode = True
    else:
        h.pusher_enabled = False
    assert not server_batch.request_eligible(h)
    assert not server_batch.suppress_live(h)


def test_owned_auto_survives_percentage_rollback(monkeypatch):
    h, _ = mobile()
    assert server_batch.suppress_live(h)
    monkeypatch.setenv('SERVER_BATCH_ONLY_ENABLED', 'false')
    assert server_batch.suppress_live(h)
    assert not server_batch.request_eligible(h)


def test_continuation_lookup_can_find_prior_owner_after_both_percentages_roll_back(monkeypatch):
    h, row = mobile()
    h.batch_record_capture = None
    monkeypatch.setenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', '0')
    assert not server_batch.request_eligible(h)
    assert server_batch.request_eligible(h, existing_capture=True)
    assert not server_batch.suppress_live(h)  # A lookup permission is never ownership.
    h.batch_record_capture = row
    assert server_batch.suppress_live(h)


def test_missing_query_language_is_not_a_declared_english_route(monkeypatch):
    h, row = mobile()
    h.request.language = h.language = 'en'  # Real endpoint's compatibility default.
    h.request.websocket = SimpleNamespace(query_params={})
    h.language_profile.primary = 'en'
    h.batch_record_capture = None
    assert server_batch.request_language(h) == ''
    assert not server_batch.request_eligible(h)
    monkeypatch.setenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', '100')
    assert server_batch.request_eligible(h)
    assert server_batch.capture_language(h) == 'multi'
    assert h.language == 'en'  # Legacy live provider choice is unchanged.
    assert server_batch.continuation_language(h) is None
    h.batch_record_capture = row
    assert server_batch.suppress_live(h)
    assert server_batch.continuation_language(h, row) == 'multi'
    monkeypatch.setenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', '0')
    monkeypatch.setenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', '0')
    assert server_batch.request_eligible(h, existing_capture=True)
    assert server_batch.suppress_live(h)


def test_auto_percentage_samples_inside_mobile_instead_of_reusing_its_hash(monkeypatch):
    monkeypatch.setenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', '5')
    monkeypatch.setenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', '1')
    mobile_count = joint = auto_outside_mobile = 0
    for index in range(10000):
        owner = f'synthetic-cohort-{index}'
        selected = server_batch.selected(owner, 'ios', 'omi')
        automatic = server_batch.auto_selected(owner, 'ios')
        mobile_count += selected
        joint += selected and automatic
        auto_outside_mobile += automatic and not selected
    assert auto_outside_mobile > 0
    assert 0 < joint < mobile_count * 0.05  # Shared hashing admits 20%, not ~1%.


@pytest.mark.parametrize(
    'change,reason',
    [
        ('private', 'private_sync_off'),
        ('auto', 'language_auto'),
        ('language', 'language_unsupported'),
        ('profile', 'profile_mismatch'),
        ('unowned', 'capture_not_owned'),
        ('phone', 'phone_call'),
    ],
)
def test_suppression_counter_records_actual_closed_decision(monkeypatch, change, reason):
    from utils import metrics

    counter = Mock()
    monkeypatch.setattr(metrics, 'OMI_LISTEN_SERVER_BATCH_SUPPRESSION_TOTAL', counter)
    h = host()
    if change == 'private':
        h.private_cloud_sync_enabled = False
    elif change == 'auto':
        h, _ = mobile()
        h.batch_record_capture = {}
    elif change == 'language':
        h.request.language = h.language = 'ja'
    elif change == 'profile':
        h.language_profile = None
    elif change == 'phone':
        h.request.source = 'phone_call'
    else:
        h.batch_record_capture = {}
    assert not server_batch.suppress_live(h)
    assert counter.labels.call_args.kwargs['decision'] == 'live'
    assert counter.labels.call_args.kwargs['reason'] == reason
    counter.labels.return_value.inc.assert_called_once()


class Allowed:
    def __call__(self):
        return True

    def raise_if_denied(self):
        pass


def classifiers(monkeypatch, *, seconds=65):
    wav = audio_unit(0, b'\x01\x00' * (16000 * seconds)).wav
    work = item(duration=seconds)
    monkeypatch.setattr(
        record_language,
        'inspect_audio',
        lambda *_: (b'\x01\x00' * (16000 * seconds), seconds, [{'start': 0, 'end': seconds}]),
    )
    vendor = Mock(return_value=LanguageDecision('en', 0.99, 'audio_lid', 30))
    own = Mock(return_value=SelfVerdict('en', 0.999, 0.999, min(seconds, 30)))
    monkeypatch.setattr(record_language.batch_language, 'detect', vendor)
    monkeypatch.setattr(record_language.language_gate, 'self_detect', own)
    return work, wav, vendor, own


async def test_every_window_has_two_proofs_and_worker_accepts_frozen_result(monkeypatch):
    work, wav, vendor, own = classifiers(monkeypatch)
    proof = await record_language.classify_wav(work, wav, Allowed())
    assert proof['stt_language_windows'] == 3
    assert vendor.call_count == own.call_count == 3
    assert stt_language(proof, duration_seconds=65) == 'en'
    worker, _, saved, *_ = setup_worker(language_of=lambda _: stt_language(proof, duration_seconds=65))
    assert worker.process_batch([item()])[0].outcome == 'success'
    assert saved


@pytest.mark.parametrize(
    'failure', ['japanese_tail', 'vendor_unavailable', 'self_unsupported', 'low_confidence', 'self_duration']
)
async def test_wrong_or_uncertain_language_never_reaches_parakeet(monkeypatch, failure):
    work, wav, vendor, own = classifiers(monkeypatch)
    if failure == 'japanese_tail':
        vendor.side_effect = [
            LanguageDecision('en', 0.99, 'audio_lid', 30),
            LanguageDecision('ja', 0.99, 'audio_lid', 30),
        ]
    elif failure == 'vendor_unavailable':
        vendor.return_value = LanguageDecision('und', 0, 'unavailable')
    elif failure == 'self_unsupported':
        own.return_value = SelfVerdict('ja', 0.99, 0.01, 30)
    elif failure == 'self_duration':
        own.return_value = SelfVerdict('en', 0.99, 0.999, 5)
    else:
        vendor.return_value = LanguageDecision('en', 0.79, 'audio_lid', 30)
    proof = await record_language.classify_wav(work, wav, Allowed())
    assert stt_language(proof, duration_seconds=65) == 'und'
    worker, recognizer, saved, *_ = setup_worker(language_of=lambda _: stt_language(proof, duration_seconds=65))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'vad_windows', 'unsupported_language')]
    assert not recognizer.calls and not saved


async def test_privacy_denial_cannot_be_downgraded_to_held_success(monkeypatch):
    work, wav, vendor, own = classifiers(monkeypatch)
    denied = Mock(return_value=False)
    denied.raise_if_denied.side_effect = PermissionError('synthetic denial')
    with pytest.raises(PermissionError):
        await record_language.classify_wav(work, wav, denied)
    own.assert_not_called()


async def test_existing_declared_manifest_needs_no_new_io():
    manifest = {'context': {'stt_language': 'en'}}
    artifacts = Mock()
    assert await record_language.prove_manifest(None, artifacts, None, manifest) is manifest
    artifacts.authorize.assert_not_called()


@pytest.mark.parametrize('revoke', [False, True])
async def test_manifest_proof_binds_original_bytes_and_rechecks_privacy(monkeypatch, revoke):
    work, _, _, _ = classifiers(monkeypatch, seconds=2)
    pcm = b'\x01\x00' * 32000
    manifest = {
        'owner_id': work.owner_id,
        'conversation_id': work.conversation_id,
        'capture_at': work.capture_at,
        'context': {'stt_language': 'multi'},
        'references': [
            {
                'start_frame': 0,
                'offset_frame': 0,
                'frames': 32000,
                'path': 'synthetic-source',
                'pcm_sha256': hashlib.sha256(pcm).hexdigest(),
            }
        ],
    }
    monkeypatch.setattr(record_language, 'read_reference', Mock(return_value=pcm))
    monkeypatch.setattr(record_language, 'ServingLanguageProbeGuard', lambda *args, **kwargs: Allowed())
    artifacts = Mock()
    artifacts.key_for_owner.return_value = b'x' * 32
    if revoke:
        artifacts.authorize.side_effect = [None, PermissionError('synthetic revocation')]
        with pytest.raises(PermissionError):
            await record_language.prove_manifest(None, artifacts, work, manifest)
    else:
        result = await record_language.prove_manifest(None, artifacts, work, manifest)
        assert result['context']['stt_language'] == 'en'
        assert result['references'] == manifest['references']
        assert artifacts.authorize.call_count == 2
    assert manifest['context'] == {'stt_language': 'multi'}  # No mutation of the original receipt.


async def test_vad_gaps_are_classified_instead_of_inheriting_first_speech_language(monkeypatch):
    work, wav, vendor, _ = classifiers(monkeypatch, seconds=65)
    monkeypatch.setattr(
        record_language, 'inspect_audio', lambda *_: (b'\x01\x00' * (16000 * 65), 65, [{'start': 0, 'end': 2}])
    )
    vendor.side_effect = [LanguageDecision('en', 0.99, 'audio_lid', 30), LanguageDecision('ja', 0.99, 'audio_lid', 30)]
    assert (await record_language.classify_wav(work, wav, Allowed()))['stt_language'] == 'und'
    assert vendor.call_count == 2


async def test_slow_network_proof_never_occupies_shared_sync_worker(monkeypatch):
    work, wav, vendor, _ = classifiers(monkeypatch, seconds=2)
    started, release = threading.Event(), threading.Event()

    def slow_probe(*args, **kwargs):
        started.set()
        assert release.wait(3)
        return LanguageDecision('en', 0.99, 'audio_lid', 2)

    vendor.side_effect = slow_probe
    with ThreadPoolExecutor(1) as sync, ThreadPoolExecutor(1) as network:
        monkeypatch.setattr(record_language, 'sync_executor', sync)
        monkeypatch.setattr(record_language, 'record_language_executor', network)
        task = asyncio.create_task(record_language.classify_wav(work, wav, Allowed()))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            assert await asyncio.wait_for(record_language.run_blocking(sync, lambda: True), 1)
            assert not task.done()
        finally:
            release.set()
            proof = await task
        assert proof['stt_language'] == 'en'
