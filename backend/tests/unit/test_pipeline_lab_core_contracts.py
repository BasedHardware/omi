"""Pipeline-lab store contract records: JSON round trips, stage order, stable content keys. Synthetic only."""

import json

import pytest

from testing.pipeline_lab import contracts as c


def _conversation() -> c.ConversationRecord:
    return c.ConversationRecord(
        id='conv-1',
        baseline_id='base-1',
        lane=c.Lane.RECORD.value,
        started_at='2026-01-15T09:00:00Z',
        finished_at='2026-01-15T09:10:00Z',
        language='en',
        segments=[c.Segment(start=0.0, end=1.5, speaker='SPEAKER_00', is_user=True, text='Hello there.')],
        structured=c.Structured(title='Fictional chat', overview='Nothing real.', events=[{'title': 'x'}]),
        action_items=[c.ActionItem.make('Buy milk', due_at='2026-01-16T00:00:00Z')],
        memories=[c.MemoryItem.make('Enjoys tea', category='interesting')],
        notifications=[c.Notification(at='2026-01-15T09:11:00Z', title='T', body='B', trigger='task')],
        llm_call_ids=['llm-1'],
        evaluable=c.Evaluable(boundaries=False, reason='gap before'),
    )


def _all_records() -> list[c.Record]:
    return [
        c.CorpusDay(
            day_id='d1',
            date='2026-01-15',
            timezone='UTC',
            coverage=c.Coverage(
                audio_seconds=10, conversations=1, lanes={'record': 1}, gaps=[c.Gap(start='a', end='b')]
            ),
        ),
        c.AudioIndexEntry(
            conversation_id='conv-1', path='conv-1.m4a', start='s', end='e', codec='aac', sample_rate=16000
        ),
        c.RunRecord(
            run_id='r1',
            day_id='d1',
            ref='main',
            stages={'notes': c.StageRun(status='complete', cache_hits=2)},
            timings={'notes': 1.5},
        ),
        _conversation(),
        c.RunDay(
            daily_summary=c.DailySummary(title='h', highlights=['x']),
            goals=[c.Goal(title='g', progress_before=1.0, progress_after=2.0, target=5.0)],
            memory_delta=c.MemoryDelta(added=['m']),
            notifications=[],
        ),
        c.LlmCall(id='llm-1', at='t', stage='notes', prompt={'messages': []}, output='x', tokens_in=3, usd=0.001),
        c.VendorLogEntry(at='t', vendor='fake', purpose='stt', audio_seconds=3.0),
        c.Decision(at='t', name='NOTES_MODE', mode='serve', source='overlay'),
        c.Verdict(
            id='v1',
            at='t',
            run_id='r1',
            day_id='d1',
            ref='main',
            conversation_id='conv-1',
            item_kind='task',
            item_key='abc',
            mark='good',
        ),
    ]


@pytest.mark.parametrize('record', _all_records(), ids=lambda r: type(r).__name__)
def test_every_record_round_trips_through_json(record):
    text = json.dumps(record.to_json())
    again = type(record).from_json(json.loads(text))
    assert again == record
    assert again.to_json() == record.to_json()


def test_nested_records_decode_to_types():
    conv = c.ConversationRecord.from_json(json.loads(json.dumps(_conversation().to_json())))
    assert isinstance(conv.segments[0], c.Segment)
    assert isinstance(conv.structured, c.Structured)
    assert isinstance(conv.action_items[0], c.ActionItem)
    assert isinstance(conv.evaluable, c.Evaluable)
    run = c.RunRecord.from_json({'run_id': 'r', 'day_id': 'd', 'ref': 'x', 'stages': {'notes': {'status': 'cached'}}})
    assert isinstance(run.stages['notes'], c.StageRun)


def test_unknown_fields_survive_a_round_trip():
    data = _conversation().to_json()
    data['future_field'] = {'added_by': 'another lane'}
    data['segments'][0]['confidence'] = 0.9
    conv = c.ConversationRecord.from_json(data)
    assert conv.extra == {'future_field': {'added_by': 'another lane'}}
    assert conv.to_json()['future_field'] == {'added_by': 'another lane'}
    assert conv.to_json()['segments'][0]['confidence'] == 0.9


def test_conversation_defaults_and_null_structured():
    conv = c.ConversationRecord.from_json({'id': 'x', 'discarded': True, 'structured': None, 'baseline_id': None})
    assert conv.structured is None and conv.discarded and conv.lane == 'unknown'
    assert conv.to_json()['baseline_id'] is None


def test_stage_order_matches_design():
    assert c.STAGES == (
        'ingest',
        'transcribe',
        'boundaries',
        'speakers',
        'discard',
        'notes',
        'memories',
        'tasks',
        'notifications',
        'goals',
        'daily_summary',
        'chat_index',
    )
    assert c.stage_index('notes') < c.stage_index('memories')
    with pytest.raises(ValueError):
        c.stage_index('nope')


def test_item_kinds_match_design():
    assert set(c.ITEM_KINDS) == {
        'summary',
        'task',
        'memory',
        'notification',
        'boundary',
        'speaker',
        'transcript',
        'daily_summary',
    }


def test_content_key_ignores_case_spacing_and_edge_punctuation():
    base = c.task_key('Buy milk')
    assert c.task_key('  buy   MILK. ') == base
    assert c.task_key('Buy\nmilk!') == base
    assert c.task_key('Buy oat milk') != base
    assert c.task_key('version 3.5') != c.task_key('version 35')
    assert len(base) == 16 and int(base, 16) >= 0


def test_content_key_is_namespaced_by_kind_and_pinned():
    assert c.content_key('task', 'Enjoys tea') != c.content_key('memory', 'Enjoys tea')
    # Pin the algorithm: verdicts recorded today must keep matching items tomorrow.
    assert c.memory_key('Enjoys tea') == c.content_key('memory', 'enjoys tea')
    assert c.memory_key('Enjoys tea') == 'e3cf748b6b2e7a01'  # pragma: allowlist secret - pinned synthetic key
    assert c.task_key('Buy milk') == '542fa5593dc887fa'  # pragma: allowlist secret - pinned synthetic key
    with pytest.raises(ValueError):
        c.content_key('nope', 'x')


def test_content_key_mapping_content_is_order_independent():
    assert c.notification_key('Hi', 'Body') == c.content_key('notification', {'body': 'body', 'title': 'hi'})


def test_verdict_validation():
    verdict = _all_records()[-1]
    assert verdict.validate() is verdict
    with pytest.raises(ValueError):
        c.Verdict.from_json({**verdict.to_json(), 'mark': 'meh'}).validate()
    with pytest.raises(ValueError):
        c.Verdict.from_json({**verdict.to_json(), 'item_kind': 'nope'}).validate()


def test_utc_helpers():
    assert c.utc_iso(c.parse_utc('2026-01-15T09:00:00+02:00')) == '2026-01-15T07:00:00Z'
    assert c.parse_utc('2026-01-15T09:00:00Z').tzinfo is not None
