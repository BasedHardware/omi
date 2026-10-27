"""Batch eligibility (lead 41e13b, scope 304254): only a KNOWN unsupported language stays on legacy sync.

Not English-only admission: blank, ``multi`` and unknown languages are admitted
exactly as before, and the per-unit worker guard plus recovery are unchanged.
"""

from types import SimpleNamespace
from unittest.mock import Mock

from prometheus_client import REGISTRY
import pytest

from config.batch_pipeline import known_unsupported_batch_language, language_eligibility_enabled
from config.policy import BatchUnitPolicy
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import intake
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.batch_pipeline.audio import audio_unit
from utils.stt import batch_language
from utils.sync.legacy_dark import LegacySyncMode

ROUTE_METRIC = 'omi_batch_pipeline_language_route_total'
EXCLUDED_LABELS = {'surface': 'intake', 'language_class': 'unsupported', 'route': 'multilingual'}


def excluded_count() -> float:
    return REGISTRY.get_sample_value(ROUTE_METRIC, EXCLUDED_LABELS) or 0.0


@pytest.fixture(autouse=True)
def defaults(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', raising=False)
    monkeypatch.delenv('STT_PRERECORDED_LANGUAGE_GUARD_ENABLED', raising=False)


async def upload(monkeypatch, *, user_language, single=False, conversation_language=None, mode='on', owner=None):
    """Run a new sync upload through intake; staging raises so admission stops at custody."""
    staged = []
    probe = Mock(
        return_value=SimpleNamespace(
            language='en', parakeet_safe=True, evidence='audio_lid', confidence=0.99, probe_seconds=6.0
        )
    )
    conversation_id = 'synthetic-conversation' if conversation_language is not None else None

    def authorize(store, seed, snapshots):
        snapshots['user'] = {
            'language': user_language,
            'transcription_preferences': {'single_language_mode': single},
        }
        if conversation_id:
            row = {'language': conversation_language}
            if owner:
                row['record_lane_owner'] = owner
            snapshots['conversations'] = {conversation_id: row}
        return ProtectionContext('standard', 0)

    def stage(work, body):
        staged.append(work)
        raise RuntimeError('stop after synthetic staging')

    def units(*args, **kwargs):
        yield audio_unit(100, b'\x01\x00' * 16000)

    monkeypatch.setattr(intake.legacy_dark, 'current_mode', lambda: LegacySyncMode(mode))
    monkeypatch.setattr(intake, 'FirestoreStore', lambda _: MemoryStore())
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(intake, 'batch_artifact_authorize', authorize)
    monkeypatch.setattr(intake, 'decode_units', units)
    monkeypatch.setattr(intake, 'artifacts_for', lambda _: SimpleNamespace(stage_audio=stage))
    monkeypatch.setattr(batch_language, 'resolve_language', probe)
    response = await intake.accept_upload(
        uid='synthetic-owner',
        job_id='new',
        content_id='new',
        paths=[],
        lane='fresh',
        recording_age_seconds=0,
        source='omi',
        should_lock=False,
        conversation_id=conversation_id,
        client_device_id=None,
        client_platform='ios',
        policy=BatchUnitPolicy(batch_enabled=True, live_record_enabled=False),
    )
    return response, staged, probe


def admitted(response, staged) -> bool:
    # Reaching staging is batch custody; the synthetic staging failure answers 503.
    return response is not None and response.status_code == 503 and len(staged) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('user_language', ['ja', 'zh-CN', 'ko', 'ar', 'hi', 'vi'])
async def test_known_unsupported_user_language_stays_on_legacy_sync(monkeypatch, user_language):
    # Multi-mode is the default for every Modulate-supported language, so it is not
    # a mixed-speech signal; the named language is.
    before = excluded_count()
    response, staged, probe = await upload(monkeypatch, user_language=user_language, single=False)
    assert response is None  # None hands the upload to the existing legacy sync path
    assert staged == [] and not probe.called  # no batch custody, no probe spend
    assert excluded_count() == before + 1


@pytest.mark.asyncio
async def test_known_unsupported_conversation_language_stays_on_legacy_sync(monkeypatch):
    response, staged, _ = await upload(monkeypatch, user_language='en', conversation_language='ja')
    assert response is None and staged == []


@pytest.mark.asyncio
@pytest.mark.parametrize('user_language', ['en', 'en-US', 'es', 'de', 'uk'])
async def test_supported_language_is_still_admitted(monkeypatch, user_language):
    before = excluded_count()
    response, staged, probe = await upload(monkeypatch, user_language=user_language)
    assert admitted(response, staged) and probe.call_count == 1
    assert excluded_count() == before


@pytest.mark.asyncio
@pytest.mark.parametrize('user_language', [None, '', 'multi', 'und', 'unknown', 'auto', 'japanese', 'xx'])
async def test_multi_blank_or_unknown_language_is_still_admitted(monkeypatch, user_language):
    """Plan section 4: multi/blank users are 52-95% of users and must stay in batch."""
    before = excluded_count()
    response, staged, probe = await upload(monkeypatch, user_language=user_language)
    assert admitted(response, staged) and probe.call_count == 1
    assert excluded_count() == before


@pytest.mark.asyncio
async def test_supported_conversation_language_overrides_an_unsupported_user_language(monkeypatch):
    # Same conversation-or-user precedence as resolve_route.
    response, staged, _ = await upload(monkeypatch, user_language='ja', conversation_language='en')
    assert admitted(response, staged)


@pytest.mark.asyncio
@pytest.mark.parametrize('raw', ['false', 'False', ' false '])
async def test_kill_switch_off_restores_batch_admission(monkeypatch, raw):
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', raw)
    assert not language_eligibility_enabled()
    response, staged, probe = await upload(monkeypatch, user_language='ja')
    assert admitted(response, staged) and probe.call_count == 1


@pytest.mark.parametrize('raw', [None, '', 'true', 'TRUE', 'garbage'])
def test_kill_switch_is_on_by_default_and_on_malformed_values(monkeypatch, raw):
    if raw is not None:
        monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', raw)
    assert language_eligibility_enabled()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['draining', 'dark'])
async def test_legacy_draining_or_dark_keeps_the_provider_route(monkeypatch, mode):
    # Legacy cannot take the upload back there; the C8 provider-STT route serves it.
    response, staged, _ = await upload(monkeypatch, user_language='ja', mode=mode)
    assert admitted(response, staged)


@pytest.mark.asyncio
async def test_durable_batch_sync_owner_never_falls_through_to_legacy(monkeypatch):
    # live_upload may claim batch_sync_v1 before intake; that owner is durable (routers/sync.py).
    response, staged, _ = await upload(
        monkeypatch, user_language='ja', conversation_language='ja', owner='batch_sync_v1'
    )
    assert admitted(response, staged)


@pytest.mark.parametrize(
    'language,known',
    [('ja', True), ('ko-KR', True), ('zh_CN', True), ('en', False), ('es', False), ('multi', False)]
    + [(value, False) for value in (None, '', 'auto', 'und', 'unknown', 'japanese', 'xx', 3)],
)
def test_known_unsupported_requires_a_recognized_non_parakeet_code(language, known):
    assert known_unsupported_batch_language(language) is known
