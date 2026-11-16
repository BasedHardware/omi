"""Real Firestore builders and production-signature RPC mocks, no network."""

import json
import threading
from types import SimpleNamespace
import time
import zlib
from datetime import datetime, timedelta, timezone
from unittest.mock import create_autospec, patch

import pytest
from google.api_core.datetime_helpers import DatetimeWithNanoseconds
from google.auth.credentials import AnonymousCredentials
from google.cloud.firestore_v1 import Client, DocumentReference, DocumentSnapshot, Query

from utils import encryption
from utils.episodes import composer_default_context as context
from utils.episodes import composer_default_context_io as sources
from utils.episodes import composer_context_budget
from utils import executors

UID = 'synthetic-owner'
AT = datetime(2026, 11, 15, 1, tzinfo=timezone.utc)
MEMBERS = [
    {
        'id': 'current',
        'started_at': AT,
        'finished_at': AT + timedelta(hours=1),
        'transcript_segments': [{'person_id': 'p1', 'person_name': 'Avery', 'text': 'Avery follows up the garden.'}],
    }
]


def budget():
    return context.ReadBudget(time.monotonic() + 8)


def path(collection, key):
    return f'users/{UID}/{collection}/{key}'


@pytest.fixture
def store():
    """Use production query objects; autospec rejects unsupported RPC kwargs."""
    client = Client(project='synthetic-context', credentials=AnonymousCredentials())
    rows = {}
    calls = []

    def snapshot(key, data):
        return DocumentSnapshot(client.document(key), data, data is not None, None, None, None)

    def get(ref, field_paths=None, transaction=None, retry=None, timeout=None):
        assert timeout and timeout <= 8
        assert retry is None
        calls.append(('get', ref.path))
        return snapshot(ref.path, rows.get(ref.path))

    def stream(query, transaction=None, retry=None, timeout=None, *, explain_options=None):
        assert timeout and timeout <= 8
        assert retry is None
        collection_path = '/'.join(query._parent._path)
        prefix = collection_path + '/'
        calls.append(('query', collection_path))
        selected = [
            (key, data) for key, data in rows.items() if key.startswith(prefix) and '/' not in key[len(prefix) :]
        ]
        for item in query._field_filters:
            # Actual SDK FieldFilter protobuf operators.
            field, op, value = item.field.field_path, item.op, item.value
            operand = getattr(value, value._pb.WhichOneof('value_type'))
            if op == 8:
                operand = [v.string_value for v in value.array_value.values]
            if op == 5:  # EQUAL
                selected = [(key, row) for key, row in selected if row.get(field) == operand]
            elif op == 8:  # IN
                selected = [(key, row) for key, row in selected if row.get(field) in operand]
            elif op == 4:  # GREATER_THAN_OR_EQUAL
                selected = [(key, row) for key, row in selected if row.get(field) is not None and row[field] >= operand]
            elif op == 1:  # LESS_THAN
                selected = [(key, row) for key, row in selected if row.get(field) is not None and row[field] < operand]
            else:
                raise AssertionError(f'unhandled test filter {op}')
        for order in reversed(query._orders):
            selected = [(key, row) for key, row in selected if order.field.field_path in row]
            selected.sort(key=lambda pair: pair[1].get(order.field.field_path), reverse=order.direction == 2)
        if query._projection:
            fields = {field.field_path for field in query._projection.fields}
            assert 'transcript_segments' not in fields
            projected = []
            for key, row in selected:
                data = {k: v for k, v in row.items() if k in fields}
                for field in fields:
                    if field.startswith('structured.') and field.split('.')[1] in row.get('structured', {}):
                        data.setdefault('structured', {})[field.split('.')[1]] = row['structured'][field.split('.')[1]]
                projected.append((key, data))
            selected = projected
        return iter(snapshot(key, data) for key, data in selected[: query._limit])

    with patch.object(DocumentReference, 'get', autospec=True, side_effect=get), patch.object(
        Query, 'stream', autospec=True, side_effect=stream
    ):
        yield client, rows, calls


def populate(rows):
    rows[path('people', 'p1')] = {
        'name': 'Avery',
        'aliases': ['Av'],
        'relationship': 'colleague',
        'description': 'Garden designer',
        'facts': ['Likes native plants'],
    }
    rows[path('memory_items', 'fact')] = {
        'uid': UID,
        'subject_entity_id': 'person:p1',
        'content': 'Avery designed the rain garden.',
        'subject_scope': 'other_person',
        'visibility': 'private',
        'status': 'active',
    }
    rows[path('meetings', 'meeting')] = {
        'title': 'Garden follow-up',
        'participants': ['Avery'],
        'description': 'Review the rain garden',
        'start_time': AT - timedelta(minutes=10),
        'end_time': AT + timedelta(minutes=30),
    }
    rows[path('conversations', 'previous')] = {
        'started_at': AT - timedelta(days=1),
        'manual_speaker_assignments': {'speakers': {'1': {'person_id': 'p1', 'is_user': False}}},
        'structured': {'title': 'Garden design', 'overview': 'Avery proposed native plants.'},
    }
    rows[path('action_items', 'action')] = {
        'completed': False,
        'status': 'active',
        'conversation_id': 'previous',
        'description': 'Send the plan to Avery',
        'created_at': AT,
    }
    rows[path('open_loops', 'loop')] = {
        'status': 'opened',
        'data_compressed': True,
        'data': encryption.encrypt(
            zlib.compress(
                json.dumps(
                    {
                        'status': 'opened',
                        'what': 'Avery to send planting costs',
                        'who': 'Avery',
                        'source_conversation_ids': ['previous'],
                    }
                ).encode()
            ).hex(),
            UID,
        ),
    }


def test_all_sections_present_with_stored_provenance_and_same_account(store, monkeypatch):
    client, rows, calls = store
    populate(rows)
    monkeypatch.setattr(
        sources, 'get_firestore_client', create_autospec(sources.get_firestore_client, return_value=client)
    )
    read_budget = budget()
    sections = context.collect(UID, MEMBERS, read_budget, sources=sources)
    block = context.render(sections)
    assert all(heading in block for heading in context.HEADINGS)
    assert 'stored about this person' in block and 'calendar entry' in block
    assert 'from the conversation on 2026-11-14' in block
    assert 'rain garden' in block and 'native plants' in block
    assert 'Send the plan' in block and 'planting costs' in block
    assert read_budget.reads <= context.MAX_READS
    assert all(key.startswith(f'users/{UID}/') for _, key in calls)


@pytest.mark.parametrize('failed', ['people', 'calendar', 'prior', 'actions'])
@pytest.mark.parametrize('error', [RuntimeError('transport'), TimeoutError('timeout')])
def test_each_section_fails_empty_independently(failed, error):
    fake = create_autospec(sources, spec_set=True)
    for name in ('people', 'calendar', 'prior', 'actions'):
        getattr(fake, name).return_value = [{'name': name, 'conversation_id': 'prior'}]
    getattr(fake, failed).side_effect = error
    sections = context.collect(UID, MEMBERS, budget(), sources=fake)
    assert context.HEADINGS[('people', 'calendar', 'prior', 'actions').index(failed)] not in sections
    assert len(sections) == 3
    assert all(getattr(fake, name).call_count == 1 for name in ('people', 'calendar', 'prior', 'actions'))


def test_read_cap_reserved_before_rpc_and_no_retry(store):
    client, rows, calls = store
    populate(rows)
    read_budget = context.ReadBudget(time.monotonic() + 8, maximum=1)
    with pytest.raises(RuntimeError, match='read cap'):
        sources.calendar(UID, MEMBERS, read_budget, firestore_client=client)
    assert calls == [] and read_budget.reads == 0
    with pytest.raises(RuntimeError, match='read cap'):
        sources.people(UID, ['p1', 'p2'], read_budget, firestore_client=client)
    assert read_budget.reads == 1 and len(calls) == 1


def test_empty_queries_charge_minimum_and_refund_unused_reservation(store):
    client, _, _ = store
    read_budget = budget()
    assert sources.calendar(UID, MEMBERS, read_budget, firestore_client=client) == []
    assert read_budget.reads == 1


def test_failed_rpc_keeps_full_reservation(store):
    client, _, _ = store
    read_budget = budget()
    Query.stream.side_effect = TimeoutError
    with pytest.raises(TimeoutError):
        sources.calendar(UID, MEMBERS, read_budget, firestore_client=client)
    assert read_budget.reads == 8


@pytest.mark.parametrize('value', ['x', '🍀', '日本語'])
def test_render_caps_characters_and_utf8_bytes(value):
    block = context.render({heading: [{'name': value * 10000}] for heading in context.HEADINGS})
    assert len(block) <= context.MAX_BYTES and len(block.encode()) <= context.MAX_BYTES
    assert block.startswith('BACKGROUND') and 'cannot establish' in block
    assert 'truncated' in block
    assert value * 10000 not in block
    for line in block.splitlines():
        if line.startswith('{'):
            json.loads(line)


def test_switch_off_calls_original_gather_exactly(monkeypatch):
    monkeypatch.setenv('EPISODE_COMPOSER_DEFAULT_CONTEXT_ENABLED', 'false')
    old_load = create_autospec(context.gather_with_defaults, return_value=('old profile', 'old memories'))
    bounded = create_autospec(context.bounded_gather, return_value=('old profile', 'old memories'))
    monkeypatch.setattr(context, 'bounded_gather', bounded)
    assert context.gather_with_defaults(UID, MEMBERS, old_load, 'fallback') == ('old profile', 'old memories')
    bounded.assert_called_once_with(old_load, 'fallback')
    old_load.assert_not_called()


def test_switch_defaults_on_and_is_read_at_call_time(monkeypatch):
    monkeypatch.delenv('EPISODE_COMPOSER_DEFAULT_CONTEXT_ENABLED', raising=False)
    assert context.enabled()
    monkeypatch.setenv('EPISODE_COMPOSER_DEFAULT_CONTEXT_ENABLED', 'false')
    assert not context.enabled()


def test_default_sections_survive_original_memory_failure(store, monkeypatch):
    client, rows, _ = store
    populate(rows)
    monkeypatch.setattr(
        sources, 'get_firestore_client', create_autospec(sources.get_firestore_client, return_value=client)
    )

    def bounded(load, fallback):
        try:
            return load(time.monotonic() + 8)
        except RuntimeError:
            return fallback, ''

    def original_load(deadline):
        assert deadline > time.monotonic()
        raise RuntimeError('memory unavailable')

    monkeypatch.setattr(context, 'bounded_gather', create_autospec(context.bounded_gather, side_effect=bounded))
    profile, memories = context.gather_with_defaults(UID, MEMBERS, original_load, 'fallback')
    assert profile == 'fallback'
    assert all(heading in memories for heading in context.HEADINGS)


@pytest.mark.parametrize(
    'field,value', [('deleted', True), ('is_deleted', True), ('deleted_at', AT), ('is_dismissed', True)]
)
def test_deleted_people_never_render(store, field, value):
    client, rows, _ = store
    rows[path('people', 'p1')] = {'name': 'Deleted', field: value}
    assert sources.people(UID, ['p1'], budget(), firestore_client=client) == []


def test_cross_account_and_unsafe_ids_do_not_escape_owner(store):
    client, rows, calls = store
    rows['users/another-owner/people/p1'] = {'name': 'Other account'}
    assert sources.people(UID, ['../another-owner', 'p1'], budget(), firestore_client=client) == []
    assert all(key.startswith(f'users/{UID}/') for _, key in calls)
    with pytest.raises(ValueError):
        sources.people('users/another-owner', ['p1'], budget(), firestore_client=client)


def test_calendar_requires_real_overlap_and_excludes_deleted(store):
    client, rows, _ = store
    rows[path('meetings', 'before')] = {'title': 'Past', 'start_time': AT - timedelta(hours=2), 'end_time': AT}
    rows[path('meetings', 'deleted')] = {
        'deleted': True,
        'title': 'Deleted',
        'start_time': AT,
        'end_time': AT + timedelta(hours=1),
    }
    rows[path('meetings', 'future')] = {
        'title': 'Later',
        'start_time': AT + timedelta(hours=1),
        'end_time': AT + timedelta(hours=2),
    }
    assert sources.calendar(UID, MEMBERS, budget(), firestore_client=client) == []


def test_prior_is_time_ordered_bounded_and_excludes_current_members(store):
    client, rows, _ = store
    for index in range(20):
        rows[path('conversations', f'prior-{index:02}')] = {
            'started_at': AT - timedelta(days=index + 1),
            'manual_speaker_assignments': {'speakers': {'1': {'person_id': 'p1', 'is_user': False}}},
            'structured': {'title': str(index), 'overview': 'summary' * 400},
        }
    result = sources.prior(UID, MEMBERS, ['p1'], budget(), firestore_client=client)
    assert [row['title'] for row in result] == ['0', '1']
    assert all(len(row['existing_summary']) <= 700 for row in result)


def test_prior_uses_manual_overrides_and_never_fetches_transcript_pointer(store):
    client, rows, calls = store
    rows[path('conversations', 'prior')] = {
        'started_at': AT - timedelta(days=1),
        'transcript_segments': [{'id': 's', 'speaker_id': 1, 'person_id': 'wrong'}],
        'manual_speaker_assignments': {'speakers': {'1': {'person_id': 'p1', 'is_user': False}}},
        'structured': {'title': 'Prior'},
    }
    rows[path('conversations', 'pointer')] = {
        'started_at': AT - timedelta(hours=1),
        'transcript_segments': {'storage': 'gcs', 'key': 'never-fetch'},
    }
    result = sources.prior(UID, MEMBERS, ['p1'], budget(), firestore_client=client)
    assert len(result) == 1 and result[0]['conversation_id'] == 'prior'
    assert all(kind == 'query' for kind, _ in calls)


def test_unrelated_closed_and_deleted_actions_are_excluded(store):
    client, rows, _ = store
    for key, overrides in [
        ('unrelated', {'description': 'Other project'}),
        ('deleted', {'deleted': True}),
        ('done', {'status': 'completed'}),
    ]:
        rows[path('action_items', key)] = {'completed': False, 'description': 'Avery follow-up', **overrides}
    assert sources.actions(UID, ['p1'], [{'name': 'Avery'}], [], budget(), firestore_client=client) == []


def test_deadline_prevents_all_io(store):
    client, _, calls = store
    with pytest.raises(TimeoutError):
        sources.calendar(UID, MEMBERS, context.ReadBudget(time.monotonic() - 1), firestore_client=client)
    assert not calls


def test_full_candidate_windows_stay_under_read_cap(store, monkeypatch):
    client, rows, _ = store
    ids = [f'p{index}' for index in range(6)]
    for index, pid in enumerate(ids):
        rows[path('people', pid)] = {'name': pid}
        if index < 3:
            for collection in ('memories', 'memory_items'):
                for fact in range(2):
                    rows[path(collection, f'{pid}-{collection}-{fact}')] = {
                        'uid': UID,
                        'subject_entity_id': f'person:{pid}',
                        'content': 'fact',
                    }
    for index in range(16):
        rows[path('conversations', f'prior-{index}')] = {
            'started_at': AT - timedelta(days=index + 1),
            'transcript_segments': [],
        }
    for index in range(8):
        rows[path('meetings', f'm{index}')] = {
            'title': 'Meeting',
            'start_time': AT,
            'end_time': AT + timedelta(minutes=30),
        }
        rows[path('action_items', f'a{index}')] = {
            'completed': False,
            'person_id': 'p0',
            'conversation_id': 'current',
            'created_at': AT,
            'description': 'Follow up',
        }
        rows[path('open_loops', f'l{index}')] = {
            'status': 'opened',
            'data': {'status': 'opened', 'person_id': 'p0', 'what': 'Question'},
        }
    members = [{**MEMBERS[0], 'transcript_segments': [{'person_id': pid} for pid in ids]}]
    monkeypatch.setattr(
        sources, 'get_firestore_client', create_autospec(sources.get_firestore_client, return_value=client)
    )
    read_budget = budget()
    sections = context.collect(UID, members, read_budget, sources=sources)
    assert len(sections) == 4
    assert read_budget.reads == context.MAX_READS == 48
    with pytest.raises(RuntimeError, match='read cap'):
        read_budget.reserve(1)


def test_reset_generation_excludes_old_action_rows(store):
    client, rows, _ = store
    rows[path('task_intelligence_control', 'state')] = {'account_generation': 2}
    rows[path('action_items', 'old')] = {
        'completed': False,
        'account_generation': 1,
        'person_id': 'p1',
        'description': 'Old reset task',
    }
    assert sources.actions(UID, ['p1'], [], [], budget(), firestore_client=client) == []


def test_real_firestore_nanosecond_timestamps_remain_valid_query_operands(store):
    client, rows, _ = store
    populate(rows)
    start = DatetimeWithNanoseconds(2026, 11, 15, 1, nanosecond=123456789, tzinfo=timezone.utc)
    end = DatetimeWithNanoseconds(2026, 11, 15, 2, nanosecond=123456789, tzinfo=timezone.utc)
    members = [{**MEMBERS[0], 'started_at': start, 'finished_at': end}]
    assert type(context.utc(start)) is datetime
    assert sources.calendar(UID, members, budget(), firestore_client=client)[0]['title'] == 'Garden follow-up'


def test_people_facts_reuse_authoritative_memories_without_another_reader():
    sections = {context.HEADINGS[0]: [{'name': 'Avery', 'aliases': ['Av']}]}
    enriched = context.with_memory_facts(
        sections, '- [other_person] Avery designed the rain garden.\n- [user] I like skiing.'
    )
    block = context.render(enriched)
    assert 'other_person' in block and 'rain garden' in block and 'authoritative' in block
    assert 'skiing' not in block
    assert sections[context.HEADINGS[0]][0] == {'name': 'Avery', 'aliases': ['Av']}


def test_ambiguous_person_names_do_not_assign_memory_facts():
    sections = {context.HEADINGS[0]: [{'name': 'Sam', 'person_id': 'p1'}, {'name': 'Sam', 'person_id': 'p2'}]}
    enriched = context.with_memory_facts(sections, '- [other_person] Sam prefers blue.')
    assert all(not row['related_stored_facts'] for row in enriched[context.HEADINGS[0]])


def test_completed_section_survives_noncooperative_timeout_and_late_results(monkeypatch):
    # The caller's whole budget elapses on an injected clock while the calendar
    # source is still inside its call; no real-clock budget races the runner.
    elapsed = [0.0]
    release, entered = threading.Event(), threading.Event()
    futures = []

    class ExpiringEvent(threading.Event):
        def wait(self, timeout=None):
            assert entered.wait(5)
            elapsed[0] += timeout
            return self.is_set()

    monkeypatch.setattr(
        composer_context_budget, 'time', SimpleNamespace(monotonic=lambda: time.monotonic() + elapsed[0])
    )
    monkeypatch.setattr(composer_context_budget, 'threading', SimpleNamespace(Event=ExpiringEvent, Lock=threading.Lock))

    def submit(worker):
        futures.append(executors.submit_with_context(executors.get_context_executor(), worker))

    def calendar(uid, members, budget, *, firestore_client=None):
        entered.set()
        release.wait(5)
        return [{'title': 'late result'}]

    original_load = create_autospec(lambda deadline: ('profile', 'memories'), return_value=('profile', 'memories'))
    monkeypatch.setattr(
        composer_context_budget, '_submit', create_autospec(composer_context_budget._submit, side_effect=submit)
    )
    monkeypatch.setattr(sources, 'people', create_autospec(sources.people, return_value=[{'name': 'Avery'}]))
    monkeypatch.setattr(sources, 'calendar', create_autospec(sources.calendar, side_effect=calendar))
    try:
        result = context.gather_with_defaults(UID, MEMBERS, original_load, 'fallback')
        # Returned at the deadline while the calendar source was still running.
        assert not release.is_set() and futures and not futures[0].done()
        assert (
            result[0] == 'profile'
            and 'memories' in result[1]
            and 'Avery' in result[1]
            and 'late result' not in result[1]
        )
    finally:
        release.set()
        for future in futures:
            future.result(timeout=5)
    assert 'late result' not in result[1]
    original_load.assert_called_once()


def test_memory_keeps_full_budget_and_defaults_use_only_remaining_time(store, monkeypatch):
    from config.episodes import COMPOSER_CONTEXT_MAX_READS
    from utils.other.list_budget import ListReadBudget

    client, rows, _ = store
    populate(rows)
    monkeypatch.setattr(
        sources, 'get_firestore_client', create_autospec(sources.get_firestore_client, return_value=client)
    )
    deadlines = []
    original_people = sources.people

    def people(uid, ids, budget, *, firestore_client=None):
        assert deadlines and budget.deadline == deadlines[0]
        assert budget.reads == 0 and budget.maximum == 48
        return original_people(uid, ids, budget, firestore_client=firestore_client)

    def memory(deadline):
        deadlines.append(deadline)
        budget = ListReadBudget(
            deadline_monotonic=deadline, max_documents=COMPOSER_CONTEXT_MAX_READS, strict_documents=True
        )
        budget.charge(640)
        assert budget.remaining_documents == 0
        return 'profile', 'memory block'

    monkeypatch.setattr(sources, 'people', create_autospec(sources.people, side_effect=people))
    result = context.gather_with_defaults(UID, MEMBERS, memory, 'fallback')
    assert all(heading in result[1] for heading in context.HEADINGS)
    assert 'memory block' in result[1]


@pytest.mark.parametrize('status', sorted(sources.OPEN_STATUSES))
def test_real_stored_open_loop_statuses_match(store, status):
    client, rows, _ = store
    rows[path('open_loops', 'loop')] = {
        'status': status,
        'data': {'status': status, 'person_id': 'p1', 'what': 'Send estimate'},
    }
    result = sources.actions(UID, ['p1'], [], [], budget(), firestore_client=client)
    assert any('open loop' in row['source'] for row in result)


def test_current_and_prior_conversation_links_precede_unrelated_tasks(store):
    client, rows, _ = store
    for i in range(20):
        rows[path('action_items', f'unrelated-{i}')] = {
            'completed': False,
            'conversation_id': 'elsewhere',
            'created_at': AT,
            'description': 'Unrelated',
        }
    for cid in ['current', 'previous']:
        rows[path('action_items', cid)] = {'completed': False, 'conversation_id': cid, 'description': 'Send estimate'}
    result = sources.actions(
        UID, [], [], [{'conversation_id': 'previous'}], budget(), member_ids=['current'], firestore_client=client
    )
    assert len(result) == 2


def test_render_never_splits_a_row_and_reports_omissions():
    row = {'description': 'complete fact', 'source': 'stored action'}
    block = context.render({context.HEADINGS[0]: [{'description': '🌿' * 3000}, row]})
    assert 'truncated' in block and 'complete fact' in block
    assert [json.loads(line) for line in block.splitlines() if line.startswith('{')] == [row]
    assert len(block.encode()) <= context.MAX_BYTES


def test_prior_deadline_reserves_actions_time(monkeypatch):
    fake = create_autospec(sources, spec_set=True)
    seen = []
    for name in ('people', 'calendar', 'actions'):
        getattr(fake, name).return_value = []

    def prior(uid, members, ids, budget, *, firestore_client=None):
        seen.append(budget.deadline - budget.section_deadline)
        raise TimeoutError('prior deadline')

    fake.prior.side_effect = prior
    # With 2 s left an unreserved prior section would run to 0.75 s before the
    # deadline (its own 1.25 s share); the reservation must leave half, about 1 s.
    sections = context.collect(UID, MEMBERS, context.ReadBudget(time.monotonic() + 2), sources=fake)
    assert 0.9 <= seen[0] <= 1.0
    assert context.HEADINGS[3] in sections
