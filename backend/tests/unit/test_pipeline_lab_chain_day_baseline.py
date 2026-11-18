"""Pipeline lab, lane chain: day outputs (memory delta, recap instant, chat readiness) and baseline view."""

from datetime import datetime, timedelta, timezone
import json

from testing.pipeline_lab.baseline.build import build_baseline
from testing.pipeline_lab.baseline.compare import baseline_view, compare_pair, iou, match_conversations, production_view
from testing.pipeline_lab.chain.export import normalize_conversation
from testing.pipeline_lab.day.outputs import (
    build_day_json,
    chat_index_readiness,
    day_bounds,
    memory_delta,
    recap_instant,
    vector_id_checker,
)
from testing.pipeline_lab.seed.synthetic import make_conversation
from testing.pipeline_lab.stack.io import append_jsonl, write_json
from testing.pipeline_lab.vector.index import NumericVectorIndex

UID = 'local-dev-user'
DAY = datetime(2026, 3, 14, tzinfo=timezone.utc)


def test_day_bounds_and_recap_instant_use_the_local_day():
    start, end = day_bounds('2026-03-14', 'America/Los_Angeles')
    assert start == datetime(2026, 3, 14, 7, tzinfo=timezone.utc)
    assert end - start == timedelta(hours=24)
    at, source = recap_instant('2026-03-14', 'America/Los_Angeles')
    assert (at, source) == (datetime(2026, 3, 15, 5, tzinfo=timezone.utc), 'local_22h')
    at, source = recap_instant('2026-03-14', None, production_at='2026-03-14T21:05:00Z')
    assert source == 'production' and at.hour == 21


def test_memory_delta_added_updated_removed():
    before = [
        {'id': 'm1', 'content': 'Likes tomatoes', 'category': 'interesting'},
        {'id': 'm2', 'content': 'Lives near the park', 'category': 'system'},
        {'id': 'm3', 'content': 'Already gone', 'category': 'x', 'deleted': True},
    ]
    after = [
        {'id': 'm1', 'content': 'Loves heirloom tomatoes', 'category': 'interesting'},
        {'id': 'm2', 'content': 'Lives near the park', 'category': 'system', 'superseded_by': 'm4'},
        {'id': 'm4', 'content': 'Moved across town', 'category': 'system', 'conversation_id': 'c9'},
    ]
    delta = memory_delta(before, after)
    assert [m['id'] for m in delta['added']] == ['m4'] and delta['added'][0]['conversation_id'] == 'c9'
    assert [m['id'] for m in delta['removed']] == ['m2']
    assert delta['updated'][0]['id'] == 'm1' and delta['updated'][0]['before']['content'] == 'Likes tomatoes'


def test_chat_index_readiness_against_owner_routed_namespaces():
    index = NumericVectorIndex(2)
    index.upsert(vectors=[{'id': f'{UID}-c1', 'values': [1, 0], 'metadata': {'uid': UID}}], namespace='ns1-p1-0a')
    index.upsert(vectors=[{'id': f'{UID}-c2', 'values': [1, 0], 'metadata': {'uid': UID}}], namespace='ns4')
    result = chat_index_readiness(['c1', 'c2'], has_vector=vector_id_checker(index, UID), has_search_doc=lambda c: True)
    assert result['vector_indexed'] == 1 and result['missing_vectors'] == ['c2'] and result['ready'] is False
    assert result['search_indexed'] == 2


def test_build_day_json_shape():
    payload = build_day_json(
        daily_summary={'date': '2026-03-14', 'headline': 'h', 'overview': 'o', 'internal': 'dropped'},
        goals=[{'id': 'g1', 'title': 'Grow', 'current_value': 2, 'target_value': 5, 'secret_field': 1}],
        memories_before=[],
        memories_after=[{'id': 'm1', 'content': 'c', 'category': 'x'}],
        notifications=[
            {'fire_at': '2026-03-14T22:00:00Z', 'title': 'Your day', 'body': 'b', 'trigger': 'daily_summary'},
            {
                'at': '2026-03-14T09:00:00Z',
                'title': 'Task',
                'body': 'b',
                'trigger': 'finalize',
                'conversation_id': 'c1',
            },
        ],
        chat_index={'ready': True},
    )
    assert {'daily_summary', 'goals', 'memory_delta', 'notifications'} <= set(payload)
    assert payload['daily_summary'] == {'title': 'h', 'overview': 'o', 'highlights': [], 'date': '2026-03-14'}
    assert payload['goals'] == [
        {
            'id': 'g1',
            'title': 'Grow',
            'progress_before': None,
            'progress_after': 2.0,
            'target': 5.0,
            'note': 'new during the day',
        }
    ]
    assert [n['title'] for n in payload['notifications']] == ['Task', 'Your day']
    assert payload['memory_delta']['added'][0]['id'] == 'm1'


def _contract(cid, start, minutes=10, **structured):
    row = make_conversation(UID, 0, start)
    row['id'] = cid
    row['finished_at'] = (start + timedelta(minutes=minutes)).isoformat()
    row['structured'].update(structured)
    return normalize_conversation(row, baseline_id=None)


def test_matching_by_id_then_overlap_then_unmatched():
    t = DAY + timedelta(hours=9)
    replay = [
        _contract('a', t),
        _contract('r-new', t + timedelta(hours=1)),
        _contract('r-split', t + timedelta(hours=3)),
    ]
    production = [
        _contract('a', t),
        _contract('p-old', t + timedelta(hours=1, minutes=2)),
        _contract('p-gone', t + timedelta(hours=6)),
    ]
    matches = {(m.replay_id, m.baseline_id): m.method for m in match_conversations(replay, production)}
    assert matches == {
        ('a', 'a'): 'id',
        ('r-new', 'p-old'): 'overlap',
        ('r-split', None): 'unmatched',
        (None, 'p-gone'): 'unmatched',
    }
    assert iou(replay[0], production[0]) == 1.0


def test_status_chips():
    t = DAY + timedelta(hours=9)
    same = compare_pair(_contract('a', t), _contract('a', t))
    assert same['status'] == 'same' and same['changed_fields'] == []
    changed = compare_pair(_contract('a', t, title='New title'), _contract('a', t))
    assert changed['status'] == 'changed' and changed['diff']['title']['production'] != 'New title'
    assert changed['label'] == 'vs production'
    flipped_row = _contract('a', t)
    flipped_row['discarded'] = True
    assert compare_pair(flipped_row, _contract('a', t))['status'] == 'discard flipped'
    assert compare_pair(None, _contract('a', t))['status'] == 'missing'
    assert compare_pair(_contract('a', t), None)['status'] == 'new'


def test_production_view_groups_tasks_and_memories_by_conversation():
    row = make_conversation(UID, 0, DAY)
    view = production_view(
        [row],
        memories=[{'id': 'm', 'content': 'x', 'category': 'c', 'conversation_id': row['id']}],
        action_items=[{'id': 't', 'description': 'Real task', 'conversation_id': row['id']}],
    )
    assert view[0]['action_items'][0]['description'] == 'Real task'
    assert view[0]['memories'][0]['content'] == 'x'
    assert view[0]['evaluable'] == {'boundaries': True, 'reason': 'production'}


def test_build_baseline_from_store_files(tmp_path):
    run_dir, baseline_dir = tmp_path / 'run', tmp_path / 'baseline'
    prod = make_conversation(UID, 0, DAY + timedelta(hours=9))
    append_jsonl(baseline_dir / 'conversations.jsonl', prod)
    append_jsonl(
        baseline_dir / 'action_items.jsonl',
        {'description': 'Order heirloom tomato seeds', 'conversation_id': prod['id']},
    )
    replay = normalize_conversation(
        {**prod, 'structured': {**prod['structured'], 'title': 'Different'}}, baseline_id=prod['id']
    )
    write_json(run_dir / 'conversations' / f'{prod["id"]}.json', replay)
    view = build_baseline(run_dir, baseline_dir)
    assert view['counts'] == {'changed': 1}
    assert view['conversations'][0]['changed_fields'] == ['title']
    assert json.loads((run_dir / 'baseline.json').read_text()) == view
    assert (run_dir / 'baseline' / 'conversations' / f'{prod["id"]}.json').exists()
    assert baseline_view([], [])['counts'] == {}
