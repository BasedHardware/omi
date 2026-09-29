import asyncio
import json

from config.translation import TranslationProvider
from models.transcript_segment import TranscriptSegment
from tests.unit.translation_test_support import DictTranslationStore, FakeProvider, build_service, translations
from utils.translation_coordinator import TranslationCoordinator
from utils.translation_demand import TranslationDemand
from utils.translation_language import TranslationNeed


def segment():
    return TranscriptSegment(id='s', text='Yến nói chuyện với bác về năm 2025.', is_user=False, start=0, end=2)


def flags(monkeypatch):
    monkeypatch.setenv('TRANSLATION_DEMAND_GATE_ENABLED', 'true')
    monkeypatch.setenv('TRANSLATION_DEMAND_LEASE_V1_ENABLED', 'true')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_GEMINI_ENABLED', 'true')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_UID_ALLOWLIST', 'u')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_UID_DAILY_CHARS', '100000')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_GLOBAL_DAILY_CHARS', '1000000')


def test_hidden_observation_is_uncommitted_then_viewed_reconciles_without_new_text(monkeypatch):
    flags(monkeypatch)
    monkeypatch.setattr(
        'utils.translation_coordinator.classify_translation_need', lambda *args, **kwargs: TranslationNeed.TRANSLATE
    )
    monkeypatch.setattr(
        'utils.translation_coordinator.reserve_translation', lambda *args, **kwargs: (object(), 'admitted')
    )
    monkeypatch.setattr('utils.translation_coordinator.reservation_is_current', lambda *args, **kwargs: True)
    monkeypatch.setattr('utils.translation_coordinator.release_translation', lambda *args, **kwargs: True)
    now = [0.0]
    demand = TranslationDemand(lambda: now[0])
    provider = FakeProvider(TranslationProvider.gemini, [translations(('Yến spoke with the elder about 2025.', 'vi'))])
    service, _ = build_service({TranslationProvider.gemini: provider})
    received = []

    async def callback(*args):
        received.append(args)

    coordinator = TranslationCoordinator('en', service, callback, uid='u', demand=demand)
    coordinator.language_state.source_is_plausible = lambda *args: True
    coordinator.language_state.observe = lambda *args, **kwargs: False

    async def run():
        demand.observe(
            {'foreground': True, 'transcript_visible': False, 'translation_demand_version': 1}, lease_v1_enabled=True
        )
        await coordinator.observe([segment()], [], 'c')
        assert coordinator._segment_states['s'].committed_text == ''
        assert not coordinator._batch_buffer and not provider.calls
        demand.observe(
            {'foreground': True, 'transcript_visible': True, 'translation_demand_version': 1}, lease_v1_enabled=True
        )
        await coordinator.observe([segment()], [], 'c')
        coordinator._cancel_batch_timer()
        await coordinator._flush_batch()
        assert received and received[0][0] == 's'
        assert provider.calls[0]['profile'].policy_version == 'viewed_v1'

    asyncio.run(run())


def test_flag_off_hidden_report_keeps_legacy_provider_and_no_redis_admission(monkeypatch):
    flags(monkeypatch)
    monkeypatch.setenv('TRANSLATION_DEMAND_GATE_ENABLED', 'false')
    monkeypatch.setattr(
        'utils.translation_coordinator.classify_translation_need', lambda *args, **kwargs: TranslationNeed.TRANSLATE
    )

    def forbidden(*args, **kwargs):
        raise AssertionError('Flag-off path must not call Redis admission')

    monkeypatch.setattr('utils.translation_coordinator.reserve_translation', forbidden)
    demand = TranslationDemand(lambda: 0)
    demand.observe({'foreground': True, 'transcript_visible': False}, lease_v1_enabled=True)
    provider = FakeProvider(TranslationProvider.nllb, [translations(('Yến spoke with the elder about 2025.', 'vi'))])
    service, _ = build_service({TranslationProvider.nllb: provider})

    async def callback(*args):
        pass

    coordinator = TranslationCoordinator('en', service, callback, uid='u', demand=demand)
    coordinator.language_state.source_is_plausible = lambda *args: True
    coordinator.language_state.observe = lambda *args, **kwargs: False

    async def run():
        await coordinator.observe([segment()], [], 'c')
        coordinator._cancel_batch_timer()
        await coordinator._flush_batch()
        assert provider.calls[0]['profile'].policy_version == 'legacy'

    asyncio.run(run())


def test_failed_materialization_does_not_commit_translated_prefix(monkeypatch):
    flags(monkeypatch)
    monkeypatch.setattr(
        'utils.translation_coordinator.classify_translation_need', lambda *args, **kwargs: TranslationNeed.TRANSLATE
    )
    monkeypatch.setattr(
        'utils.translation_coordinator.reserve_translation', lambda *args, **kwargs: (object(), 'admitted')
    )
    monkeypatch.setattr('utils.translation_coordinator.reservation_is_current', lambda *args, **kwargs: True)
    monkeypatch.setattr('utils.translation_coordinator.release_translation', lambda *args, **kwargs: True)
    demand = TranslationDemand(lambda: 0)
    demand.observe(
        {'foreground': True, 'transcript_visible': True, 'translation_demand_version': 1}, lease_v1_enabled=True
    )
    provider = FakeProvider(TranslationProvider.gemini, [translations(('Yến spoke with the elder about 2025.', 'vi'))])
    service, _ = build_service({TranslationProvider.gemini: provider})

    async def rejected(*args):
        return False

    coordinator = TranslationCoordinator('en', service, rejected, uid='u', demand=demand)
    coordinator.language_state.source_is_plausible = lambda *args: True
    coordinator.language_state.observe = lambda *args, **kwargs: False

    async def run():
        await coordinator.observe([segment()], [], 'c')
        coordinator._cancel_batch_timer()
        await coordinator._flush_batch()
        assert coordinator._segment_states['s'].committed_text == ''
        assert coordinator._segment_states['s'].assembled_translation is None

    asyncio.run(run())


def test_flag_off_hidden_report_matches_legacy_result_bytes(monkeypatch):
    flags(monkeypatch)
    monkeypatch.setenv('TRANSLATION_DEMAND_GATE_ENABLED', 'false')
    monkeypatch.setattr(
        'utils.translation_coordinator.classify_translation_need', lambda *args, **kwargs: TranslationNeed.TRANSLATE
    )

    async def capture(with_hidden_report):
        store = DictTranslationStore()
        provider = FakeProvider(
            TranslationProvider.nllb, [translations(('Yến spoke with the elder about 2025.', 'vi'))]
        )
        service, _ = build_service({TranslationProvider.nllb: provider}, store=store)
        events = []

        async def callback(*args):
            events.append(args)

        demand = TranslationDemand(lambda: 0) if with_hidden_report else None
        if demand:
            demand.observe({'foreground': True, 'transcript_visible': False}, lease_v1_enabled=True)
        coordinator = TranslationCoordinator('en', service, callback, uid='u', demand=demand)
        coordinator.language_state.source_is_plausible = lambda *args: True
        coordinator.language_state.observe = lambda *args, **kwargs: False
        await coordinator.observe([segment()], [], 'c')
        coordinator._cancel_batch_timer()
        await coordinator._flush_batch()
        return json.dumps(
            {
                'events': events,
                'provider_inputs': [call['contents'] for call in provider.calls],
                'policy': provider.calls[0]['profile'].policy_version,
                'positive_cache': sorted((key[0], key[1], value.text) for key, value in store.values.items()),
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode('utf-8')

    assert asyncio.run(capture(False)) == asyncio.run(capture(True))
