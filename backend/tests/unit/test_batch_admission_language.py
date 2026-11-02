"""New-custody language exclusion; existing receipts and the kill path stay intact."""

from copy import deepcopy
import hashlib
import io
from types import SimpleNamespace
import wave
from unittest.mock import Mock

import pytest

from config.batch_pipeline_language import (
    admission_language_exclusion_enabled,
    admission_language_sample_enabled,
    batch_admission_language,
)
from config.policy import BatchUnitPolicy
from database.batch_pipeline_intake import admit
from tests.unit.test_batch_language_eligibility import admitted, upload
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils import funded_processing, stt_cap_dispatch
from utils.batch_pipeline import intake
from utils.batch_pipeline.audio import audio_unit
from utils.batch_pipeline.intake_outcome import IntakeRouteEvidence
from utils.sync import final_pass_rehome


@pytest.fixture(autouse=True)
def defaults(monkeypatch):
    monkeypatch.delenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_ADMISSION_LANGUAGE_SAMPLE_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', raising=False)
    monkeypatch.delenv('STT_PRERECORDED_LANGUAGE_GUARD_ENABLED', raising=False)


@pytest.mark.asyncio
@pytest.mark.parametrize('language', [None, '', 'multi', 'auto', 'und', 'unknown', 'xx', 'ja', 'vi'])
@pytest.mark.parametrize('user_language', ['multi', 'auto', 'en'])
async def test_multilingual_unknown_or_unsupported_conversation_never_enters_custody(
    monkeypatch, language, user_language
):
    # Sampling off is the full exclusion; sampled admission is covered below.
    monkeypatch.setenv('BATCH_ADMISSION_LANGUAGE_SAMPLE_ENABLED', 'false')
    writer = Mock(side_effect=AssertionError('excluded upload wrote batch custody'))
    monkeypatch.setattr(intake, 'admit', writer)
    response, staged, probe = await upload(
        monkeypatch, user_language=user_language, conversation_language=language, mode='on'
    )
    assert response is None and not staged and not probe.called
    writer.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['draining', 'dark'])
@pytest.mark.parametrize(
    'user,conversation,single',
    [
        ('multi', None, False),
        ('multi', 'und', False),
        ('auto', 'xx', False),
        ('en', 'ja', False),
        ('multi', 'vi', False),
        ('ja', None, False),
        ('en', 'vi', True),
        ('multi', 'ko-KR', True),
    ],
)
async def test_excluded_languages_enter_batch_once_owner_legacy_is_retired(
    monkeypatch, mode, user, conversation, single
):
    # Legacy no longer takes new work for this owner, so exclusion would leave the upload with
    # neither lane; it enters batch custody instead (C8's provider route serves it).
    response, staged, _ = await upload(
        monkeypatch, user_language=user, conversation_language=conversation, single=single, mode=mode
    )
    assert admitted(response, staged)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['on', 'draining', 'dark'])
@pytest.mark.parametrize('language,expected', [('en', 'en'), (' EN-us ', 'en'), ('mt', 'mt'), ('uk', 'uk')])
@pytest.mark.parametrize('inherit', ['true', 'false'])
async def test_multilingual_supported_conversation_pins_the_input_language(
    monkeypatch, mode, language, expected, inherit
):
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_INHERITANCE_ENABLED', inherit)
    response, staged, probe = await upload(
        monkeypatch, user_language='multi', conversation_language=language, mode=mode
    )
    assert admitted(response, staged)
    assert probe.call_args.args[0] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['on', 'draining', 'dark'])
async def test_supported_multilingual_upload_commits_real_batch_admission(monkeypatch, mode):
    store = MemoryStore()
    store.namespace = 'batch_pipeline_dev'
    # Synthetic staging has no GCS artifact reservation. Exercise the real
    # ownership, sibling, binding and scheduler transaction after that seam.
    monkeypatch.setattr(intake, 'admit', lambda *a, **k: admit(*a, **{**k, 'require_artifacts': False}))
    response, staged, probe = await upload(
        monkeypatch,
        user_language='multi',
        conversation_language='en',
        mode=mode,
        stop_after_staging=False,
        store=store,
    )
    assert response.status_code == 202 and len(staged) == 1
    assert probe.call_args.args[0] == 'en'
    assert store.rows['content', 'synthetic-owner/new']['dispatch_protocol'] == 'batch_v1'
    job = store.rows['jobs', staged[0].segment_id]
    assert job['projection_binding']['language'] == 'en'
    assert job['policy']['stt_route'] == 'parakeet'


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['on', 'draining', 'dark'])
async def test_single_supported_language_is_unchanged(monkeypatch, mode):
    response, staged, probe = await upload(monkeypatch, user_language='en-US', single=True, mode=mode)
    assert admitted(response, staged)
    assert probe.call_args.args[0] == 'en'


@pytest.mark.asyncio
@pytest.mark.parametrize('single', [False, True])
@pytest.mark.parametrize('user,conversation', [('ja', None), ('en', 'vi'), ('multi', 'ko-KR')])
@pytest.mark.parametrize('inherit', ['true', 'false'])
async def test_effective_unsupported_code_excluded_even_when_old_eligibility_is_off(
    monkeypatch, single, user, conversation, inherit
):
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_INHERITANCE_ENABLED', inherit)
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', 'false')
    response, staged, probe = await upload(
        monkeypatch, user_language=user, conversation_language=conversation, single=single, mode='on'
    )
    assert response is None and not staged and not probe.called


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['on', 'draining', 'dark'])
async def test_supported_conversation_overrides_unsupported_user_preference(monkeypatch, mode):
    response, staged, probe = await upload(
        monkeypatch, user_language='ja', conversation_language='en', single=True, mode=mode
    )
    assert admitted(response, staged)
    assert probe.call_args.args[0] == 'en'


def decision(language, safe, confidence=0.99, evidence='audio_lid'):
    return SimpleNamespace(
        language=language, parakeet_safe=safe, evidence=evidence, confidence=confidence, probe_seconds=6.0
    )


SPEECH = b'synthetic-speech-probe-wav'


def speaking(monkeypatch, *results):
    """Strict-VAD speech probes per unit, in order (default: every unit has speech)."""
    probe = Mock(side_effect=list(results)) if results else Mock(return_value=SPEECH)
    monkeypatch.setattr(intake, '_speech_probe', probe)
    return probe


@pytest.mark.asyncio
@pytest.mark.parametrize('inherit', ['true', 'false'])
@pytest.mark.parametrize('user_language,conversation', [('en', None), ('multi', None), ('es', 'und'), ('en', '')])
async def test_unknown_multilingual_upload_admits_after_a_parakeet_safe_sample(
    monkeypatch, inherit, user_language, conversation
):
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_INHERITANCE_ENABLED', inherit)
    speaking(monkeypatch)
    excluded = Mock()
    monkeypatch.setattr(intake, 'record_admission_exclusion', excluded)
    evidence = IntakeRouteEvidence()
    response, staged, probe = await upload(
        monkeypatch, user_language=user_language, conversation_language=conversation, mode='on', evidence=evidence
    )
    assert admitted(response, staged) and not evidence.language_excluded
    # The declared user language is never pinned: the unit's speech itself is classified, once.
    assert probe.call_count == 1 and probe.call_args.args[:2] == ('multi', SPEECH)
    assert probe.staged_context['stt_language'] == 'en'
    excluded.assert_not_called()


@pytest.mark.asyncio
async def test_silent_leading_unit_waits_unstaged_and_replays_first_after_a_speech_sample(monkeypatch):
    vad = speaking(monkeypatch, None, SPEECH)
    response, staged, probe = await upload(monkeypatch, user_language='en', mode='on', unit_count=2)
    assert admitted(response, staged) and vad.call_count == 2
    # The whole upload was classified first (the speech unit's probe); the silent unit was then
    # staged first, under its own index and its own per-unit LID, never the speech unit's language.
    assert probe.call_args_list[0].args[1] == SPEECH and probe.call_count == 2
    assert probe.call_args_list[1].args[1] != SPEECH
    assert staged[0].segment_id == hashlib.sha256(b'new:0').hexdigest()


async def _upload_all_units(monkeypatch, **kwargs):
    """Stage every unit (admission itself then fails closed); returns staged contexts in order."""
    contexts = []
    original = intake.with_context

    def capture(wav, context):
        contexts.append(context)
        return original(wav, context)

    monkeypatch.setattr(intake, 'with_context', capture)
    monkeypatch.setattr(intake, 'admit', Mock(side_effect=RuntimeError('stop before admission')))
    response, staged, probe = await upload(monkeypatch, mode='on', stop_after_staging=False, **kwargs)
    return response, staged, probe, contexts


@pytest.mark.asyncio
async def test_an_unsafe_later_unit_keeps_the_whole_upload_on_legacy_before_staging(monkeypatch):
    speaking(monkeypatch, SPEECH, SPEECH)
    answers = iter([decision('en', True), decision('ja', False)])
    response, staged, probe, contexts = await _upload_all_units(
        monkeypatch, user_language='en', unit_count=2, decision=lambda *a, **k: next(answers)
    )
    assert response is None and staged == [] and contexts == [] and probe.call_count == 2


@pytest.mark.asyncio
async def test_each_speech_unit_keeps_its_own_language_and_a_silent_unit_never_inherits_one(monkeypatch):
    speaking(monkeypatch, SPEECH, None, SPEECH)
    # Two speech samples in the pre-pass, then the silent unit's own per-unit LID during replay.
    answers = iter([decision('en', True), decision('es', True), decision('und', False, 0.0)])
    response, staged, probe, contexts = await _upload_all_units(
        monkeypatch, user_language='en', unit_count=3, decision=lambda *a, **k: next(answers)
    )
    assert response.status_code == 503 and len(staged) == 3 and probe.call_count == 3
    # The silent unit keeps the unknown-language barrier for any speech the worker VAD finds.
    assert [context['stt_language'] for context in contexts] == ['en', 'und', 'es']


@pytest.mark.asyncio
@pytest.mark.parametrize('single,expected', [(False, intake.SAMPLE_SCAN_SECONDS), (True, 7200.0)])
async def test_sampled_upload_decodes_units_no_longer_than_the_hold_bound(monkeypatch, single, expected):
    speaking(monkeypatch)
    bounds = []

    def decode_for_intake(paths, max_seconds, *args, **kwargs):
        bounds.append(max_seconds)
        yield audio_unit(100, b'\x01\x00' * 16000)

    monkeypatch.setattr(intake, 'decode_for_intake', decode_for_intake)
    monkeypatch.setattr(
        intake, 'provider_config', lambda: SimpleNamespace(pool_kind='dedicated_batch', max_unit_seconds=7200.0)
    )
    response, staged, _ = await upload(monkeypatch, user_language='en', single=single, mode='on')
    assert admitted(response, staged) and bounds == [expected]


@pytest.mark.asyncio
@pytest.mark.parametrize('vad', [[None], [RuntimeError('vad')], [None, None, None]])
async def test_silent_unclassifiable_or_over_bound_upload_keeps_legacy_without_a_probe(monkeypatch, vad):
    monkeypatch.setattr(intake, 'SAMPLE_SCAN_SECONDS', 2)
    speaking(monkeypatch, *vad)
    evidence = IntakeRouteEvidence()
    response, staged, probe = await upload(
        monkeypatch, user_language='en', mode='on', unit_count=len(vad), evidence=evidence
    )
    assert response is None and staged == [] and not probe.called and evidence.language_excluded


@pytest.mark.asyncio
async def test_sample_probe_is_authorized_as_the_unit_it_replays_as(monkeypatch):
    # No conversation id on the upload: the unit's derived chunk conversation must be the one
    # the sample's privacy guard checks, before any audio reaches the vendor.
    speaking(monkeypatch, None, SPEECH)
    guarded = []

    def classify(*args, **kwargs):
        guarded.append(kwargs['before_probe'].item)
        return decision('en', True)

    response, staged, _ = await upload(monkeypatch, user_language='en', mode='on', unit_count=2, decision=classify)
    assert admitted(response, staged)
    sampled_item = guarded[0]
    assert sampled_item.segment_id == hashlib.sha256(b'new:1').hexdigest()
    assert sampled_item.conversation_id and sampled_item.unit_kind == 'capture_span'
    replayed_speech_unit = intake.chunk_identity('synthetic-owner', 'omi', None, False, sampled_item.capture_at)
    assert sampled_item.conversation_id == replayed_speech_unit
    assert sampled_item.capture_at != staged[0].capture_at  # unit 1, not the held unit 0


@pytest.mark.asyncio
async def test_self_lid_sample_does_not_admit(monkeypatch):
    # Worker self-LID evidence is bound to the unit's first 30 s, which a speech sample is not.
    speaking(monkeypatch)
    response, staged, _ = await upload(
        monkeypatch, user_language='en', mode='on', decision=decision('en', True, evidence='self_lid')
    )
    assert response is None and staged == []


def test_speech_probe_concatenates_at_most_thirty_seconds_of_strict_speech(monkeypatch):
    from utils.stt import local_vad

    spans = [{'start': 1.0, 'end': 21.0}, {'start': 30.0, 'end': 50.0}]
    monkeypatch.setattr(local_vad, 'offline_pcm_speech_segments', lambda pcm: spans)
    body = io.BytesIO()
    with wave.open(body, 'wb') as target:
        target.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        target.writeframes(b'\x01\x00' * 16000 * 60)
    with wave.open(io.BytesIO(intake._speech_probe(body.getvalue())), 'rb') as probe:
        assert probe.getnframes() == 30 * 16000
    monkeypatch.setattr(local_vad, 'offline_pcm_speech_segments', lambda pcm: [])
    assert intake._speech_probe(body.getvalue()) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'sample', [decision('ja', False), decision('en', False, 0.4), decision('und', False, 0.0), decision('zh', False)]
)
async def test_unsafe_or_unavailable_sample_keeps_the_upload_on_legacy(monkeypatch, sample):
    speaking(monkeypatch)
    writer = Mock(side_effect=AssertionError('unsafe sample wrote batch custody'))
    excluded = Mock()
    monkeypatch.setattr(intake, 'admit', writer)
    monkeypatch.setattr(intake, 'record_admission_exclusion', excluded)
    evidence = IntakeRouteEvidence()
    response, staged, probe = await upload(
        monkeypatch, user_language='en', mode='on', decision=sample, evidence=evidence
    )
    assert response is None and staged == [] and probe.call_count == 1
    writer.assert_not_called()
    assert excluded.call_args.args[1] == 'unknown_multilingual_conversation'
    # The intake outcome counter (#24283) attributes the legacy landing to the language gate.
    assert evidence.language_excluded and not evidence.heavy_owner_excluded


@pytest.mark.asyncio
async def test_refused_sample_probe_keeps_the_refusal_instead_of_legacy(monkeypatch):
    # Consent revoked during the first unit's LID: the guard's refusal wins over the
    # unsafe-sample legacy route, so the client keeps its audio and retries.
    monkeypatch.setattr(funded_processing, 'consent_allows', lambda *_: False)
    monkeypatch.setattr(stt_cap_dispatch, 'sync_allowed', lambda *a, **k: True)
    speaking(monkeypatch)
    unsafe = decision('und', False, 0.0)

    def refused(*args, **kwargs):
        assert kwargs['before_probe']() is False
        return unsafe

    excluded = Mock()
    monkeypatch.setattr(intake, 'record_admission_exclusion', excluded)
    response, staged, _ = await upload(monkeypatch, user_language='en', mode='on', decision=unsafe)
    assert response is None and excluded.call_count == 1  # control: unrefused unsafe sample → legacy
    excluded.reset_mock()
    response, staged, probe = await upload(monkeypatch, user_language='en', mode='on', decision=refused)
    assert probe.call_count == 1
    assert response is not None and response.status_code == 503 and staged == []
    excluded.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('user,conversation', [('ja', None), ('en', 'vi'), ('multi', 'ko-KR')])
async def test_known_unsupported_language_is_never_sampled(monkeypatch, user, conversation):
    response, staged, probe = await upload(monkeypatch, user_language=user, conversation_language=conversation)
    assert response is None and not staged and not probe.called


@pytest.mark.parametrize('raw,expected', [(None, True), ('true', True), ('garbage', True), ('false', False)])
def test_sample_switch_is_default_on(monkeypatch, raw, expected):
    if raw is not None:
        monkeypatch.setenv('BATCH_ADMISSION_LANGUAGE_SAMPLE_ENABLED', raw)
    assert admission_language_sample_enabled() is expected


@pytest.mark.parametrize('raw', [None, '', 'true', 'TRUE', 'garbage'])
def test_switch_is_default_on(monkeypatch, raw):
    if raw is not None:
        monkeypatch.setenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', raw)
    assert admission_language_exclusion_enabled()


@pytest.mark.asyncio
@pytest.mark.parametrize('raw', ['false', 'False', ' false '])
@pytest.mark.parametrize('mode', ['on', 'draining', 'dark'])
async def test_switch_off_restores_old_multi_input_and_staged_bytes(monkeypatch, raw, mode):
    monkeypatch.setenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', raw)
    assert not admission_language_exclusion_enabled()
    monkeypatch.setattr(intake, 'batch_admission_language', Mock(side_effect=AssertionError('disabled policy read')))
    bodies = []
    original = intake.with_context

    def capture(wav, context):
        body = original(wav, context)
        bodies.append(body)
        return body

    monkeypatch.setattr(intake, 'with_context', capture)
    response, staged, probe = await upload(monkeypatch, user_language='multi', mode=mode)
    assert admitted(response, staged) and probe.call_args.args[0] == 'multi'
    # Equivalent false spellings retain exactly the same authenticated WAV
    # context bytes, not merely the same admission outcome.
    monkeypatch.setenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', 'false')
    other, other_staged, other_probe = await upload(monkeypatch, user_language='multi', mode=mode)
    assert admitted(other, other_staged) and other_probe.call_args.args == probe.call_args.args
    assert other_probe.call_args.kwargs['surface'] == probe.call_args.kwargs['surface'] == 'batch'
    assert len(bodies) == 2 and bodies[0] == bodies[1]


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', ['true', 'false'])
async def test_prior_batch_receipt_is_read_without_reclassification_or_data_writes(monkeypatch, enabled):
    monkeypatch.setenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', enabled)
    store = MemoryStore()
    store.rows['content', 'synthetic-owner/content'] = {'dispatch_protocol': 'batch_v1', 'job_id': 'bp_prior'}
    before = deepcopy(store.rows)
    monkeypatch.setattr(intake, 'FirestoreStore', lambda _: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(intake, 'durable_status', lambda *a: None)
    forbidden = Mock(side_effect=AssertionError('existing batch unit reclassified'))
    monkeypatch.setattr(intake, 'batch_artifact_authorize', forbidden)
    monkeypatch.setattr(intake, 'batch_admission_language', forbidden)
    response = await intake.accept_upload(
        uid='synthetic-owner',
        job_id='retry',
        content_id='content',
        paths=[],
        lane='fresh',
        recording_age_seconds=0,
        source='omi',
        should_lock=False,
        conversation_id=None,
        client_device_id=None,
        client_platform='ios',
        policy=BatchUnitPolicy(batch_enabled=True),
    )
    assert response.status_code == 409 and store.rows == before
    assert b'bp_prior' in response.body
    forbidden.assert_not_called()


@pytest.mark.asyncio
async def test_durable_batch_conversation_owner_keeps_its_route(monkeypatch):
    response, staged, _ = await upload(
        monkeypatch, user_language='ja', conversation_language='ja', owner='batch_sync_v1', mode='dark'
    )
    assert admitted(response, staged)


@pytest.mark.asyncio
async def test_exclusion_precedes_legacy_owner_rehome(monkeypatch):
    rehome = Mock(side_effect=AssertionError('excluded upload changed a durable route'))
    monkeypatch.setattr(final_pass_rehome, 'upload_rehome', rehome)
    # Exclusion applies only while the owner still has legacy (dark admits it: see the retired-owner test).
    response, staged, probe = await upload(
        monkeypatch, user_language='multi', conversation_language='ja', owner='legacy_final_pass_v1', mode='on'
    )
    assert response is None and not staged and not probe.called
    rehome.assert_not_called()


@pytest.mark.parametrize('user', ['en', 'multi', 'auto', None])
def test_non_single_language_preferences_require_supported_conversation(user):
    assert batch_admission_language({'language': user}, {}) == (None, 'unknown_multilingual_conversation')
