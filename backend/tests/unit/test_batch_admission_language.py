"""New-custody language exclusion; existing receipts and the kill path stay intact."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from config.batch_pipeline_language import admission_language_exclusion_enabled, batch_admission_language
from config.policy import BatchUnitPolicy
from database.batch_pipeline_intake import admit
from tests.unit.test_batch_language_eligibility import admitted, upload
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import intake
from utils.sync import final_pass_rehome


@pytest.fixture(autouse=True)
def defaults(monkeypatch):
    monkeypatch.delenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', raising=False)
    monkeypatch.delenv('STT_PRERECORDED_LANGUAGE_GUARD_ENABLED', raising=False)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['on', 'draining', 'dark'])
@pytest.mark.parametrize('language', [None, '', 'multi', 'auto', 'und', 'unknown', 'xx', 'ja', 'vi'])
@pytest.mark.parametrize('user_language', ['multi', 'auto', 'en'])
async def test_multilingual_unknown_or_unsupported_conversation_never_enters_custody(
    monkeypatch, mode, language, user_language
):
    writer = Mock(side_effect=AssertionError('excluded upload wrote batch custody'))
    monkeypatch.setattr(intake, 'admit', writer)
    response, staged, probe = await upload(
        monkeypatch, user_language=user_language, conversation_language=language, mode=mode
    )
    assert response is None and not staged and not probe.called
    writer.assert_not_called()


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
@pytest.mark.parametrize('mode', ['on', 'draining', 'dark'])
@pytest.mark.parametrize('single', [False, True])
@pytest.mark.parametrize('user,conversation', [('ja', None), ('en', 'vi'), ('multi', 'ko-KR')])
@pytest.mark.parametrize('inherit', ['true', 'false'])
async def test_effective_unsupported_code_excluded_even_when_old_eligibility_is_off(
    monkeypatch, mode, single, user, conversation, inherit
):
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_INHERITANCE_ENABLED', inherit)
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', 'false')
    response, staged, probe = await upload(
        monkeypatch, user_language=user, conversation_language=conversation, single=single, mode=mode
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
    response, staged, probe = await upload(
        monkeypatch, user_language='multi', conversation_language='ja', owner='legacy_final_pass_v1', mode='dark'
    )
    assert response is None and not staged and not probe.called
    rehome.assert_not_called()


@pytest.mark.parametrize('user', ['en', 'multi', 'auto', None])
def test_non_single_language_preferences_require_supported_conversation(user):
    assert batch_admission_language({'language': user}, {}) == (None, 'unknown_multilingual_conversation')
