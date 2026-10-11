"""Visible catch-up spends only on missing or stale materializations."""

import asyncio
from types import SimpleNamespace

from routers.listen import transcripts
from utils.translation_demand import DemandPolicy


def test_viewed_catchup_skips_current_persisted_translation(monkeypatch):
    monkeypatch.setenv('TRANSLATION_DEMAND_GATE_ENABLED', 'true')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_UID_ALLOWLIST', 'u')
    monkeypatch.setenv('TRANSLATION_ONDEMAND_GEMINI_ENABLED', 'true')
    checked = []

    def is_current(uid, conversation, segment, target, policy, source_hint):
        checked.append((uid, segment['id'], target, policy, source_hint))
        return segment['id'] == 'already-current'

    monkeypatch.setattr(transcripts.conversations_db, 'translation_materialization_is_current', is_current)
    observed = []

    class Coordinator:
        realtime_interpreter = False
        target_language = 'en'
        source_language = 'vi'
        _batch_task = None
        demand = SimpleNamespace(snapshot=lambda **kwargs: SimpleNamespace(policy=DemandPolicy.viewed, generation=1))

        def demand_changed(self):
            pass

        async def observe(self, segments, removed, conversation_id):
            observed.extend(segment.id for segment in segments)

    async def get(conversation_id, force_refresh=False):
        return {
            'id': conversation_id,
            'transcript_segments': [
                {'id': 'already-current', 'text': 'Yến nói với bác.', 'start': 0, 'end': 1, 'is_user': False},
                {'id': 'missing', 'text': 'Yến tới năm 2025.', 'start': 1, 'end': 2, 'is_user': False},
            ],
        }

    processor = object.__new__(transcripts.TranscriptProcessor)
    processor.host = SimpleNamespace(
        request=SimpleNamespace(uid='u'), state=SimpleNamespace(current_conversation_id='c')
    )
    processor.cache = SimpleNamespace(get=get)
    processor.translation_coordinator = Coordinator()
    processor._last_translation_demand_generation = -1
    processor._last_translation_demand_conversation = None
    asyncio.run(processor.on_translation_demand_changed())
    assert observed == ['missing']
    assert checked == [
        ('u', 'already-current', 'en', 'viewed_v1', 'vi'),
        ('u', 'missing', 'en', 'viewed_v1', 'vi'),
    ]
