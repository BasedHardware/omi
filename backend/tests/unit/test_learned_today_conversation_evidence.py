"""Day attribution for the memory review card reads *all* conversation evidence.

`MemoryDB.conversation_id` is a single scalar that `memory_item_to_memorydb`
overwrites once per conversation-sourced evidence row, so a memory supported by
two conversations keeps only the last one. Matching on that scalar alone dropped
memories genuinely produced by one of the summarised day's conversations.
`MemoryService.retract_conversation_memories` already matches evidence this way.
"""

from datetime import datetime, timedelta, timezone

from models.memories import MemoryCategory, MemoryDB
import utils.memory.learned_today as learned_today
from utils.memory.learned_today import memories_learned_for_summary, select_memories_learned

DAY_START = datetime(2026, 9, 1, 7, 0, tzinfo=timezone.utc)
DAY_END = DAY_START + timedelta(hours=24)


def _evidence(source_id: str, source_type: str = 'conversation') -> dict:
    return {
        'evidence_id': f'ev-{source_id}',
        'source_id': source_id,
        'source_type': source_type,
        'independence_group': source_id,
    }


def _memory(memory_id: str, **overrides) -> MemoryDB:
    payload = {
        'id': memory_id,
        'uid': 'u1',
        'content': f'fact {memory_id}',
        'category': MemoryCategory.interesting,
        'created_at': DAY_START + timedelta(hours=1),
        'updated_at': DAY_START + timedelta(hours=1),
        'capture_confidence': 0.5,
    }
    payload.update(overrides)
    return MemoryDB(**payload)


def _select(memories):
    return select_memories_learned(memories, conversation_ids=['c-today'], window_start=DAY_START, window_end=DAY_END)


def test_evidence_from_a_summarised_conversation_counts_even_when_the_scalar_points_elsewhere():
    merged = _memory(
        'merged',
        conversation_id='c-yesterday',
        evidence=[_evidence('c-yesterday'), _evidence('c-today')],
    )
    assert [ref.memory_id for ref in _select([merged])] == ['merged']


def test_a_memory_with_no_evidence_from_the_day_is_still_excluded():
    other = _memory('other', conversation_id='c-yesterday', evidence=[_evidence('c-yesterday')])
    assert _select([other]) == []


def test_non_conversation_evidence_does_not_attribute_a_memory_to_the_day():
    api = _memory('api', conversation_id=None, evidence=[_evidence('c-today', source_type='developer_api')])
    api.created_at = DAY_START - timedelta(days=3)
    assert _select([api]) == [], 'only conversation evidence attributes a memory to the summarised set'


def test_the_scan_pages_past_a_full_page_and_stops_at_the_first_short_one():
    """`MemoryService.read` orders by updated_at, so a bulk touch can push more
    than one page of older memories in front of the day being summarised."""
    calls = []
    day_memory = _memory('wanted', conversation_id='c-today')

    def reader(uid, *, limit, offset):
        calls.append((limit, offset))
        if offset == 0:
            return [_memory(f'old-{i}', conversation_id='c-old') for i in range(limit)]
        return [day_memory]

    picked = memories_learned_for_summary(
        'u1',
        conversation_ids=['c-today'],
        window_start=DAY_START,
        window_end=DAY_END,
        read_memories=reader,
        scan_limit=4,
    )

    assert [ref.memory_id for ref in picked] == ['wanted']
    assert calls == [(4, 0), (4, 4)], 'a short page ends the scan; the page cap bounds it either way'


def test_a_short_first_page_costs_exactly_one_read():
    calls = []

    def reader(uid, *, limit, offset):
        calls.append((limit, offset))
        return [_memory('m1', conversation_id='c-today')]

    memories_learned_for_summary(
        'u1',
        conversation_ids=['c-today'],
        window_start=DAY_START,
        window_end=DAY_END,
        read_memories=reader,
        scan_limit=50,
    )
    assert calls == [(50, 0)], 'the overwhelming majority of users still pay for one page'


def test_a_failure_reaching_the_memory_stack_costs_the_card_not_the_recap(monkeypatch):
    """The lazy MemoryService import sits on the same fail-open path as the read
    itself; letting it propagate cost the whole daily summary, not just the card."""
    reported = []
    monkeypatch.setattr(learned_today, '_report_read_failure', lambda error: reported.append(type(error).__name__))
    monkeypatch.setitem(__import__('sys').modules, 'utils.memory.memory_service', None)

    assert (
        memories_learned_for_summary('u1', conversation_ids=['c-today'], window_start=DAY_START, window_end=DAY_END)
        == []
    )
    assert reported and reported[0].endswith('Error'), 'the failure is reported, never swallowed'
