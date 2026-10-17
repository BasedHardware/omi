"""The "what do I owe people?" read (GET /v1/tools/commitments service).

Covers the person rule (``resolve_counterparty``, pure) and the batched,
owner-scoped read (``get_commitments_result``) with the database functions
patched on their real modules, so nothing reaches Firestore.
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from utils.retrieval.tool_services import commitments as svc

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
PHONE_RE = re.compile(r'\+\d[\d\s().-]{6,}\d|\(\d{3}\)|\d{3}[\s.-]\d{4}\b')


def _segment(segment_id, text, *, is_user=False, person_id=None, speaker=None, start=None):
    segment = {'id': segment_id, 'text': text, 'is_user': is_user, 'person_id': person_id}
    if speaker is not None:
        segment['speaker'] = speaker
    if start is not None:
        segment.update(start=float(start), end=float(start) + 2.0)
    return segment


def _task(task_id='t1', conversation_id='c1', cited=('s2',), **overrides):
    task = {
        'id': task_id,
        'description': f'Commitment {task_id}',
        'owner': 'user',
        'status': 'active',
        'completed': False,
        'deleted': False,
        'source': 'conversation',
        'conversation_id': conversation_id,
        'created_at': NOW - timedelta(days=1),
        'provenance': (
            [
                {
                    'kind': 'conversation',
                    'id': conversation_id,
                    'scope': 'canonical',
                    'transcript_segment_ids': list(cited),
                }
            ]
            if cited
            else []
        ),
    }
    task.update(overrides)
    return task


def _conversation(conversation_id='c1', segments=None, **structured):
    # Back-to-back lines five seconds apart unless a test sets its own timing.
    for index, segment in enumerate(segments or []):
        segment.setdefault('start', index * 5.0)
        segment.setdefault('end', index * 5.0 + 3.0)
    return {
        'id': conversation_id,
        'started_at': NOW - timedelta(days=1),
        'structured': {'title': f'Talk {conversation_id}', **structured},
        'transcript_segments': segments if segments is not None else [],
    }


def _one_to_one(conversation_id='c1', person_id='p-priya'):
    return _conversation(
        conversation_id,
        [
            _segment('s1', 'Can you send me the pricing sheet?', person_id=person_id),
            _segment('s2', "Sure, I'll send it by Friday.", is_user=True),
        ],
    )


# ---------------------------------------------------------------------------
# Person rule (pure)
# ---------------------------------------------------------------------------


class TestResolveCounterparty:
    def test_one_non_user_speaker_in_the_cited_lines(self):
        conversation = _conversation(
            segments=[_segment('s1', 'Unrelated.', is_user=True), _segment('s2', 'I will send it.', person_id='p1')]
        )
        result = svc.resolve_counterparty(_task(), conversation, {'p1': 'Priya'})
        assert result == svc.Attribution(names=('Priya',), person_ids=('p1',), basis='speaker')

    def test_asker_just_before_the_cited_promise_is_found_by_the_look_back(self):
        result = svc.resolve_counterparty(_task(), _one_to_one(), {'p-priya': 'Priya'})
        assert result.names == ('Priya',)
        assert result.basis == 'speaker'

    def test_look_back_stops_after_two_segments(self):
        conversation = _conversation(
            segments=[
                _segment('s0', 'Ask from far back.', person_id='p-far'),
                _segment('s1', 'Filler.', is_user=True),
                _segment('s1b', 'More filler.', is_user=True),
                _segment('s2', "I'll do it.", is_user=True),
                _segment('s3', 'Later remark.', person_id='p-later'),
            ]
        )
        people = {'p-far': 'Far', 'p-later': 'Later'}
        assert svc.resolve_counterparty(_task(), conversation, people) == svc.UNATTRIBUTED

    def test_several_speakers_are_all_named_in_order_of_appearance(self):
        conversation = _conversation(
            segments=[
                _segment('s0', 'We need the deck.', person_id='p-sam'),
                _segment('s1', 'And the numbers.', person_id='p-priya'),
                _segment('s2', "I'll send both.", is_user=True),
            ]
        )
        result = svc.resolve_counterparty(_task(), conversation, {'p-priya': 'Priya', 'p-sam': 'Sam'})
        assert result.names == ('Sam', 'Priya')
        assert result.person_ids == ('p-sam', 'p-priya')
        assert result.basis == 'speakers'
        assert result.key == ('p-priya', 'p-sam')

    def test_one_to_one_fallback_uses_the_only_other_speaker(self):
        conversation = _conversation(
            segments=[
                _segment('s1', 'Some update.', person_id='p-alex'),
                _segment('s1b', 'Okay.', is_user=True),
                _segment('s1c', 'Sounds good.', is_user=True),
                _segment('s2', "I'll book it.", is_user=True),
            ]
        )
        conversation['transcript_segments'].insert(0, _segment('s0', 'Hi.', person_id='p-alex'))
        result = svc.resolve_counterparty(_task(), conversation, {'p-alex': 'Alex'})
        assert result == svc.Attribution(names=('Alex',), person_ids=('p-alex',), basis='conversation', likely=True)

    def test_a_meeting_roster_never_names_anyone(self):
        # Rosters are not used: the owner cannot be told apart from a guest reliably.
        conversation = _conversation(
            segments=[_segment('s2', "I'll send the notes.", is_user=True)],
            participants=[
                {'name': 'Notetaker', 'email': 'bot@fireflies.ai', 'is_ai_agent': True, 'source': 'roster'},
                {'name': 'Dana Lee', 'email': 'dana@corp.example', 'source': 'roster'},
            ],
        )
        assert svc.resolve_counterparty(_task(), conversation, {}) == svc.UNATTRIBUTED

    def test_owner_name_is_never_used_as_the_counterparty(self):
        # owner_name names the OWNER of an item; for a user-owned item it may even be
        # another participant's name from a confused summary. It must never leak in.
        summary_item = {'description': 'Send deck', 'target_task_id': 't1', 'owner_name': 'Sam Rivera'}
        conversation = _conversation(
            segments=[_segment('s2', "I'll send it.", is_user=True)], action_items=[summary_item]
        )
        assert svc.resolve_counterparty(_task(), conversation, {}) == svc.UNATTRIBUTED

        conversation = _one_to_one()
        conversation['structured']['action_items'] = [summary_item]
        result = svc.resolve_counterparty(_task(), conversation, {'p-priya': 'Priya'})
        assert result.names == ('Priya',)

    def test_cited_ids_missing_from_the_transcript_fall_through_without_error(self):
        result = svc.resolve_counterparty(_task(cited=('gone',)), _one_to_one(), {'p-priya': 'Priya'})
        assert result.basis == 'conversation'

    def test_without_provenance_the_linked_summary_item_supplies_the_cited_lines(self):
        conversation = _conversation(
            segments=[
                _segment('s1', 'Can you intro me to Sam?', person_id='p-priya'),
                _segment('s2', "Yes, I'll intro you.", is_user=True),
                _segment('s3', 'Different topic.', person_id='p-alex'),
            ],
            action_items=[{'description': 'Commitment t1', 'target_task_id': 't1', 'source_segment_ids': ['s2']}],
        )
        result = svc.resolve_counterparty(_task(cited=()), conversation, {'p-priya': 'Priya', 'p-alex': 'Alex'})
        assert result.names == ('Priya',)

    def test_an_unlinked_summary_item_with_the_same_text_is_not_used(self):
        conversation = _conversation(
            segments=[
                _segment('s1', 'Can you intro me to Sam?', person_id='p-priya'),
                _segment('s2', "Yes, I'll intro you.", is_user=True),
                _segment('s3', 'Different topic.', person_id='p-alex'),
            ],
            action_items=[{'description': 'Commitment t1', 'target_task_id': 'other', 'source_segment_ids': ['s2']}],
        )
        people = {'p-priya': 'Priya', 'p-alex': 'Alex'}
        assert svc.resolve_counterparty(_task(cited=()), conversation, people) == svc.UNATTRIBUTED

    def test_missing_conversation_is_unattributed(self):
        assert svc.resolve_counterparty(_task(), None, {'p-priya': 'Priya'}) == svc.UNATTRIBUTED

    def test_unresolvable_speaker_falls_through(self):
        assert svc.resolve_counterparty(_task(), _one_to_one(), {}) == svc.UNATTRIBUTED


# ---------------------------------------------------------------------------
# Batched, owner-scoped read
# ---------------------------------------------------------------------------


class FakeStore:
    def __init__(self, monkeypatch):
        self.tasks = []
        self.conversations = {}
        self.people = {}
        self.scan_hit_limit = False
        self.get_action_items = MagicMock(side_effect=self._get_action_items)
        self.get_conversations = MagicMock(
            side_effect=lambda uid, ids: [self.conversations[i] for i in ids if i in self.conversations]
        )
        self.get_people = MagicMock(side_effect=lambda uid, ids: [self.people[i] for i in ids if i in self.people])
        monkeypatch.setattr(svc.action_items_db, 'get_action_items', self.get_action_items)
        monkeypatch.setattr(svc.conversations_db, 'get_conversations_by_id_without_photos', self.get_conversations)
        monkeypatch.setattr(svc.users_db, 'get_people_by_ids', self.get_people)
        # No account or profile read: rosters are not used.
        monkeypatch.setattr(svc.users_db, 'get_user_profile', MagicMock(side_effect=AssertionError('profile read')))
        # Read-only: any write reaching the task store fails the test.
        for name in ('create_action_item', 'update_action_item', 'delete_action_item'):
            if hasattr(svc.action_items_db, name):
                monkeypatch.setattr(svc.action_items_db, name, MagicMock(side_effect=AssertionError(name)))

    def _get_action_items(self, **kwargs):
        if kwargs.get('scan_report') is not None:
            kwargs['scan_report']['hit_limit'] = self.scan_hit_limit
        return list(self.tasks)

    def read(self, **kwargs):
        return svc.get_commitments_result('uid-1', now=NOW, **kwargs)


@pytest.fixture
def store(monkeypatch):
    return FakeStore(monkeypatch)


def _add_one_to_one(store, index, *, name=None, created_offset=0, due=None, **task_overrides):
    conversation_id = f'c{index}'
    person_id = f'p{index}'
    store.conversations[conversation_id] = _one_to_one(conversation_id, person_id)
    store.people[person_id] = {'id': person_id, 'name': name or f'Person {index}'}
    task = _task(
        f't{index}',
        conversation_id,
        created_at=NOW - timedelta(hours=1 + created_offset),
        due_at=due,
        **task_overrides,
    )
    store.tasks.append(task)
    return task


class TestGetCommitmentsResult:
    def test_only_open_user_owned_conversation_tasks_are_listed(self, store):
        _add_one_to_one(store, 1, name='Priya')
        _add_one_to_one(store, 2, owner='other')
        _add_one_to_one(store, 3, owner='unknown')
        _add_one_to_one(store, 4, owner=None)
        _add_one_to_one(store, 5, status='cancelled')
        _add_one_to_one(store, 6, status='superseded')
        _add_one_to_one(store, 7, deleted=True)
        _add_one_to_one(store, 8, is_locked=True)
        _add_one_to_one(store, 9, source='manual')
        _add_one_to_one(store, 10)
        store.tasks[-1]['conversation_id'] = None
        _add_one_to_one(store, 11, completed=True, status='completed')

        result = store.read()

        listed = [c['task_id'] for g in result['groups'] for c in g['commitments']] + [
            c['task_id'] for c in result['unattributed']
        ]
        assert listed == ['t1']
        assert result['groups'][0]['names'] == ['Priya']
        # Unknown and missing owners are counted, never listed; "other" is the other direction.
        assert result['totals'] == {
            'people': 1,
            'commitments': 1,
            'unattributed': 0,
            'excluded_unknown_owner': 2,
            'not_checked': 0,
        }
        assert '2 more captured item(s) have an unclear owner' in result['result_text']

    def test_reads_are_batched_owner_scoped_and_never_write(self, store):
        for index in range(1, 6):
            _add_one_to_one(store, index)

        store.read()

        store.get_action_items.assert_called_once_with(
            uid='uid-1',
            completed=False,
            start_date=NOW - timedelta(days=30),
            limit=svc.TASK_SCAN_LIMIT + 1,
            extra_fields=('provenance',),
            scan_report=ANY,
        )
        store.get_conversations.assert_called_once()
        assert store.get_conversations.call_args.args[0] == 'uid-1'
        assert sorted(store.get_conversations.call_args.args[1]) == [f'c{i}' for i in range(1, 6)]
        store.get_people.assert_called_once()
        assert store.get_people.call_args.args[0] == 'uid-1'

    def test_gone_and_locked_conversations_leave_the_task_unattributed_without_excerpt(self, store):
        _add_one_to_one(store, 1)
        _add_one_to_one(store, 2)
        store.conversations['c2']['is_locked'] = True
        store.tasks.append(_task('t3', 'c-deleted'))  # deleted/discarded: the batch read drops it

        result = store.read()

        assert result['groups'] and result['groups'][0]['commitments'][0]['task_id'] == 't1'
        unattributed = {c['task_id']: c for c in result['unattributed']}
        assert set(unattributed) == {'t2', 't3'}
        for item in unattributed.values():
            assert item['excerpt'] is None
            assert item['conversation_title'] is None
            assert item['attribution'] == {'names': [], 'person_ids': [], 'basis': 'none', 'likely': False}
        assert [s['source_id'] for s in result['sources']] == ['c1']

    def test_people_cap_and_per_person_cap(self, store):
        for index in range(1, 13):
            _add_one_to_one(store, index, created_offset=index)
        for extra in range(6):
            store.tasks.append(_task(f't1-{extra}', 'c1', created_at=NOW - timedelta(minutes=extra)))

        result = store.read()

        assert len(result['groups']) == svc.DEFAULT_LIMIT_PEOPLE
        assert result['totals']['people'] == 12
        assert result['totals']['commitments'] == 18
        first = next(g for g in result['groups'] if g['person_ids'] == ['p1'])
        assert first['open_count'] == 7
        assert len(first['commitments']) == svc.MAX_PER_PERSON
        assert result['truncated'] is True

    def test_overall_commitment_cap(self, store):
        for index in range(1, 9):
            _add_one_to_one(store, index, created_offset=index)
            for extra in range(4):
                store.tasks.append(
                    _task(f't{index}-{extra}', f'c{index}', created_at=NOW - timedelta(hours=index, minutes=extra + 1))
                )

        result = store.read(limit_people=20)

        shown = sum(len(g['commitments']) for g in result['groups'])
        assert shown == svc.MAX_COMMITMENTS
        assert result['totals']['commitments'] == 40
        assert result['truncated'] is True

    def test_unattributed_cap(self, store):
        for index in range(12):
            store.tasks.append(_task(f'u{index}', f'gone-{index}', created_at=NOW - timedelta(minutes=index)))

        result = store.read()

        assert len(result['unattributed']) == svc.MAX_UNATTRIBUTED
        assert result['totals']['unattributed'] == 12
        assert result['truncated'] is True

    def test_conversation_cap_reads_only_the_newest_25(self, store):
        for index in range(1, 27):
            _add_one_to_one(store, index, created_offset=index)

        result = store.read(limit_people=20)

        read_ids = store.get_conversations.call_args.args[1]
        assert len(read_ids) == svc.CONVERSATION_CAP
        assert 'c26' not in read_ids
        # Not read is not "person not identified": it is counted as not checked.
        assert result['unattributed'] == []
        assert result['totals']['not_checked'] == 1
        assert result['totals']['unattributed'] == 0
        assert '1 older item(s) were not checked.' in result['result_text']
        assert result['truncated'] is True

    def test_only_a_page_past_the_scan_limit_is_reported_as_truncated(self, store):
        store.tasks = [_task(f't{i}', 'gone', owner='other') for i in range(svc.TASK_SCAN_LIMIT)]
        assert store.read()['truncated'] is False

        store.tasks.append(_task('t-extra', 'gone', owner='unknown'))
        result = store.read()
        assert result['truncated'] is True
        # Only the first TASK_SCAN_LIMIT rows are used; the probe row is not counted.
        assert result['totals']['excluded_unknown_owner'] == 0

    def test_a_scan_cut_short_by_soft_deleted_rows_is_reported_as_truncated(self, store):
        _add_one_to_one(store, 1)
        assert store.read()['truncated'] is False

        store.scan_hit_limit = True
        result = store.read()
        assert result['truncated'] is True
        assert result['groups'][0]['commitments'][0]['task_id'] == 't1'

    def test_since_defaults_to_30_days_and_is_clamped_to_90(self, store):
        store.read()
        assert store.get_action_items.call_args.kwargs['start_date'] == NOW - timedelta(days=30)

        store.read(since='2025-01-01T00:00:00+00:00')
        assert store.get_action_items.call_args.kwargs['start_date'] == NOW - timedelta(days=90)

        store.read(since='2026-10-04T00:00:00-07:00')
        assert store.get_action_items.call_args.kwargs['start_date'] == datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc)

    @pytest.mark.parametrize('since', ['last week', '2026-10-04', '2026-10-04T00:00:00'])
    def test_malformed_or_naive_since_is_an_error_result(self, store, since):
        result = store.read(since=since)
        assert result['result_text'].startswith('Error: Invalid since format')
        assert result['groups'] == [] and result['sources'] == []
        store.get_action_items.assert_not_called()

    def test_person_filter_matches_resolved_names_case_insensitively(self, store):
        _add_one_to_one(store, 1, name='Priya Shah')
        _add_one_to_one(store, 2, name='Sam Rivera')
        store.tasks.append(_task('u1', 'gone'))

        # A first name finding the full name is a normal match, not a partial one.
        for person, partial in (('priya', False), ('PRIYA SHAH', False), ('  priya  shah ', False)):
            result = store.read(person=person)
            assert [g['names'] for g in result['groups']] == [['Priya Shah']]
            assert result['groups'][0]['partial_match'] is partial
            assert result['groups'][0]['commitments'][0]['partial_match'] is partial
            assert result['unattributed'] == []
        assert '(partial name match)' not in store.read(person='priya')['result_text']

        assert store.read(person='pri')['groups'] == []
        assert store.read(person='Dana')['groups'] == []

    def test_excerpt_comes_only_from_cited_lines_and_is_bounded(self, store):
        long_promise = "I'll send " + ' '.join(f'word{i}' for i in range(80))
        store.conversations['c1'] = _conversation(
            'c1',
            [
                _segment('s1', 'ASKED-BEFORE text is not part of the excerpt.', person_id='p1'),
                _segment('s2', long_promise, is_user=True),
            ],
        )
        store.people['p1'] = {'id': 'p1', 'name': 'Priya'}
        store.tasks.append(_task('t1', 'c1'))

        item = store.read()['groups'][0]['commitments'][0]

        assert len(item['excerpt']) <= svc.EXCERPT_CHARS
        assert item['excerpt'].endswith('…')
        assert 'ASKED-BEFORE' not in item['excerpt']
        assert re.match(r"^I'll send word0 .*word\d+…$", item['excerpt'])

    def test_output_never_carries_an_email_or_phone_number(self, store):
        store.conversations['c1'] = _conversation(
            'c1',
            [
                _segment('s1', 'Can you send the contract? My mobile is 415 555 0123.', person_id='p-dana'),
                _segment('s2', "I'll send the contract to dana@corp.example by 3:00 PM.", is_user=True),
            ],
            title='Call with +1 (415) 555-0100',
            action_items=[
                {'target_task_id': 't1', 'context': 'Dana asked; reach her at 415.555.0199 or dana.lee@corp.example.'}
            ],
        )
        store.people['p-dana'] = {'id': 'p-dana', 'name': 'Dana Lee', 'email': 'dana@corp.example'}
        store.tasks.append(_task('t1', 'c1', description='Email the $1,200.50 quote to ops@corp.example'))
        _add_one_to_one(store, 2, name='Priya')
        store.conversations['c2']['transcript_segments'][1]['text'] = "I'll text you on +91 98765 43210 on 2026-10-12."
        store.people['p2'].update({'email': 'priya@corp.example', 'phone': '+1 415 555 0100'})

        result = store.read()
        serialized = json.dumps(result)

        assert {tuple(g['names']) for g in result['groups']} == {('Dana Lee',), ('Priya',)}
        assert not EMAIL_RE.search(serialized), serialized
        assert not PHONE_RE.search(serialized), serialized
        dana = next(g for g in result['groups'] if g['names'] == ['Dana Lee'])['commitments'][0]
        assert dana['description'] == 'Email the $1,200.50 quote to [email]'
        assert dana['excerpt'] == "I'll send the contract to [email] by 3:00 PM."
        assert dana['conversation_title'] == 'Call with [phone]'
        assert dana['context'] == 'Dana asked; reach her at [phone] or [email].'
        priya = next(g for g in result['groups'] if g['names'] == ['Priya'])['commitments'][0]
        assert priya['excerpt'] == "I'll text you on [phone] on 2026-10-12."
        previews = {s['source_id']: s['preview'] for s in result['sources']}
        assert previews == {'c1': dana['excerpt'], 'c2': priya['excerpt']}

    def test_malformed_person_doc_is_skipped_not_an_error(self, store):
        _add_one_to_one(store, 1)
        store.people['p1'] = {'id': 'p1', 'name': None, 'created_at': 'garbage'}

        result = store.read()

        assert result['groups'] == []
        assert [c['task_id'] for c in result['unattributed']] == ['t1']
        assert not result['result_text'].startswith('Error')

    def test_groups_sort_by_soonest_due_then_newest(self, store):
        _add_one_to_one(store, 1, name='Undated new', created_offset=0)
        _add_one_to_one(store, 2, name='Due later', due=NOW + timedelta(days=5))
        _add_one_to_one(store, 3, name='Due soon', due=NOW + timedelta(days=1), created_offset=5)
        _add_one_to_one(store, 4, name='Undated old', created_offset=10)

        names = [g['names'][0] for g in store.read()['groups']]

        assert names == ['Due soon', 'Due later', 'Undated new', 'Undated old']

    def test_group_shows_its_weakest_basis(self, store):
        _add_one_to_one(store, 1, name='Priya')
        # Same person, but only found as the one other speaker in a second conversation.
        store.conversations['c9'] = _conversation(
            'c9',
            [
                _segment('s0', 'Hello.', person_id='p1'),
                _segment('s1', 'Okay.', is_user=True),
                _segment('s1b', 'Right.', is_user=True),
                _segment('s2', "I'll call you.", is_user=True),
            ],
        )
        store.tasks.append(_task('t9', 'c9'))

        group = store.read()['groups'][0]

        assert group['names'] == ['Priya']
        assert group['basis'] == 'conversation'
        assert group['likely'] is True
        assert group['open_count'] == 2

    def test_linked_summary_item_supplies_context_and_due_certainty(self, store):
        _add_one_to_one(store, 1, due=NOW + timedelta(days=2))
        store.conversations['c1']['structured']['action_items'] = [
            {
                'description': 'Send pricing',
                'target_task_id': 't1',
                'context': 'Priya needs it for the board meeting.',
                'due_certainty': 'tentative',
            }
        ]

        item = store.read()['groups'][0]['commitments'][0]

        assert item['context'] == 'Priya needs it for the board meeting.'
        assert item['due_certainty'] == 'tentative'
        assert item['conversation_title'] == 'Talk c1'
        assert item['due_at'] == (NOW + timedelta(days=2)).isoformat()

    def test_backend_failure_is_a_generic_error_without_content(self, store, caplog):
        store.get_action_items.side_effect = RuntimeError('Send Priya the secret plan')

        result = store.read()

        assert result['result_text'] == 'Error: Could not load commitments right now.'
        assert 'secret plan' not in caplog.text
        assert 'RuntimeError' in caplog.text

    def test_empty_read_says_so(self, store):
        result = store.read()
        assert result['result_text'] == 'No open commitments to other people found since 2026-09-11.'
        assert result['since'] == (NOW - timedelta(days=30)).isoformat()
        assert result['groups'] == [] and result['unattributed'] == [] and result['sources'] == []
        store.get_conversations.assert_not_called()
        store.get_people.assert_not_called()


# ---------------------------------------------------------------------------
# Who was in the room, speaker labels, rosters, timing and redaction
# ---------------------------------------------------------------------------


class TestUnidentifiedPeopleBlockOnePersonFallbacks:
    def test_unlabelled_asker_does_not_credit_the_only_labelled_person(self):
        # Priya only said good morning; an unlinked voice asked; the user promised.
        conversation = _conversation(
            segments=[
                _segment('s0', 'Morning all.', person_id='p-priya', speaker='SPEAKER_01', start=0),
                _segment('s0b', 'Anyway.', is_user=True, start=200),
                _segment('s0c', 'Ok.', is_user=True, start=300),
                _segment('s1', 'Can you send me the contract?', speaker='SPEAKER_02', start=400),
                _segment('s2', "Sure, I'll send it to you tonight.", is_user=True, start=403),
            ]
        )
        assert svc.resolve_counterparty(_task(), conversation, {'p-priya': 'Priya'}) == svc.UNATTRIBUTED

    def test_unlabelled_voice_elsewhere_blocks_the_one_to_one_fallback(self):
        conversation = _conversation(
            segments=[
                _segment('s0', 'Hi.', person_id='p-alex'),
                _segment('s0b', 'Hello there.'),  # a voice nobody linked or labelled
                _segment('s1', 'Okay.', is_user=True),
                _segment('s1b', 'Sure.', is_user=True),
                _segment('s2', "I'll book it.", is_user=True),
            ]
        )
        assert svc.resolve_counterparty(_task(), conversation, {'p-alex': 'Alex'}) == svc.UNATTRIBUTED

    def test_an_untagged_line_on_a_tagged_persons_label_is_still_someone_unidentified(self):
        conversation = _conversation(
            segments=[
                _segment('s0', 'Hi.', person_id='p-alex', speaker='SPEAKER_01'),
                _segment('s0b', 'Quick update.', speaker='SPEAKER_01'),
                _segment('s1', 'Okay.', is_user=True),
                _segment('s1b', 'Sure.', is_user=True),
                _segment('s2', "I'll book it.", is_user=True),
            ]
        )
        assert svc.resolve_counterparty(_task(), conversation, {'p-alex': 'Alex'}) == svc.UNATTRIBUTED

    def test_unnamed_roster_human_blocks_the_one_to_one_fallback(self):
        conversation = _conversation(
            segments=[
                _segment('s0', 'Hi.', person_id='p-alex'),
                _segment('s1', 'Okay.', is_user=True),
                _segment('s1b', 'Sure.', is_user=True),
                _segment('s2', "I'll book it.", is_user=True),
            ],
            participants=[{'name': None, 'email': 'bob@corp.example', 'source': 'roster'}],
        )
        assert svc.resolve_counterparty(_task(), conversation, {'p-alex': 'Alex'}) == svc.UNATTRIBUTED

    def test_partly_unresolved_window_is_unattributed_not_a_single_speaker(self):
        conversation = _conversation(
            segments=[
                _segment('s0', 'We need the deck.', person_id='p-gone'),
                _segment('s1', 'And the numbers.', person_id='p-priya'),
                _segment('s2', "I'll send both.", is_user=True),
            ]
        )
        assert svc.resolve_counterparty(_task(), conversation, {'p-priya': 'Priya'}) == svc.UNATTRIBUTED


class TestSpeakerLabelsNeverNameAnyone:
    def test_a_tag_on_the_undiarized_default_label_is_not_spread(self):
        # Every line keeps SPEAKER_00; one early line was tagged Priya; Sam asks later.
        conversation = _conversation(
            segments=[
                _segment('s0', 'Hi everyone, Priya here.', person_id='p-priya', speaker='SPEAKER_00', start=0),
                _segment('s1', 'Sam here: can you send me the contract?', speaker='SPEAKER_00', start=600),
                _segment('s2', "Sure Sam, I'll send it tonight.", is_user=True, speaker='SPEAKER_00', start=604),
            ]
        )
        assert svc.resolve_counterparty(_task(), conversation, {'p-priya': 'Priya'}) == svc.UNATTRIBUTED

    def test_desktop_system_audio_label_with_priya_tagged_and_sams_untagged_ask(self):
        # Local transcription puts every remote voice on SPEAKER_01 (system audio).
        conversation = _conversation(
            segments=[
                _segment('s0', 'Morning, Priya here.', person_id='p-priya', speaker='SPEAKER_01', start=0),
                _segment('s1', 'Sam: can you send me the contract?', speaker='SPEAKER_01', start=600),
                _segment('s2', "Sure, I'll send it tonight.", is_user=True, speaker='SPEAKER_00', start=604),
            ]
        )
        assert svc.resolve_counterparty(_task(), conversation, {'p-priya': 'Priya'}) == svc.UNATTRIBUTED

    def test_three_people_on_the_system_audio_label_do_not_collapse_into_one_voice(self):
        conversation = _conversation(
            segments=[
                _segment('s0', 'Priya here.', person_id='p-priya', speaker='SPEAKER_01', start=0),
                _segment('s0b', 'Sam here.', speaker='SPEAKER_01', start=5),
                _segment('s0c', 'Alex here.', speaker='SPEAKER_01', start=9),
                _segment('s2', "I'll write the summary.", is_user=True, speaker='SPEAKER_00', start=900),
            ]
        )
        assert svc.resolve_counterparty(_task(), conversation, {'p-priya': 'Priya'}) == svc.UNATTRIBUTED

    @pytest.mark.parametrize('label', ['SPEAKER_0', 'SPEAKER_00', 'SPEAKER_01', 'SPEAKER_07'])
    def test_no_label_spreads_a_tag_to_untagged_lines(self, label):
        conversation = _conversation(
            segments=[
                _segment('s0', 'Priya here.', person_id='p-priya', speaker=label, start=0),
                _segment('s1', 'Can you send me the contract?', speaker=label, start=600),
                _segment('s2', "I'll send it.", is_user=True, speaker='SPEAKER_99', start=604),
            ]
        )
        assert svc.resolve_counterparty(_task(), conversation, {'p-priya': 'Priya'}) == svc.UNATTRIBUTED

    def test_a_person_tagged_on_their_own_line_in_the_exchange_is_plain(self):
        conversation = _conversation(
            segments=[
                _segment('s1', 'Can you send me the contract?', person_id='p-priya', speaker='SPEAKER_01', start=0),
                _segment('s2', "I'll send it.", is_user=True, speaker='SPEAKER_00', start=4),
            ]
        )
        result = svc.resolve_counterparty(_task(), conversation, {'p-priya': 'Priya'})
        assert result.basis == 'speaker' and result.likely is False


class TestRostersAreNotUsed:
    def test_the_service_reads_no_account_identity(self):
        assert not hasattr(svc, 'auth_db')
        assert not hasattr(svc, 'AccountIdentity')

    def test_a_roster_does_not_attribute_in_a_read(self, store):
        store.conversations['c1'] = _conversation(
            'c1',
            [_segment('s2', "I'll send the notes.", is_user=True)],
            participants=[{'name': 'Sauransh Kumar', 'source': 'roster'}, {'name': 'Priya', 'source': 'roster'}],
        )
        store.tasks.append(_task('t1', 'c1'))

        result = store.read()

        assert result['groups'] == []
        assert [c['task_id'] for c in result['unattributed']] == ['t1']


class TestTheLookBackIsTimeBound:
    def test_a_goodbye_half_an_hour_before_a_note_to_self_is_not_the_asker(self):
        conversation = _conversation(
            segments=[
                _segment('s0', 'Okay, talk later, bye!', person_id='p-priya', start=0),
                _segment('s2', 'Note to self: I need to renew my passport.', is_user=True, start=1800),
            ]
        )
        # Priya is still the only other voice, so this is at most a hedged guess.
        result = svc.resolve_counterparty(_task(), conversation, {'p-priya': 'Priya'})
        assert result.basis == 'conversation' and result.likely is True

    def test_the_asker_within_the_window_is_the_speaker(self):
        conversation = _conversation(
            segments=[
                _segment('s0', 'Can you renew my badge?', person_id='p-priya', start=0),
                _segment('s2', "Sure, I'll do it.", is_user=True, start=60),
            ]
        )
        result = svc.resolve_counterparty(_task(), conversation, {'p-priya': 'Priya'})
        assert result.basis == 'speaker' and result.likely is False

    def test_a_line_just_outside_the_window_is_not_counted(self):
        conversation = _conversation(
            segments=[
                _segment('s0', 'Can you renew my badge?', person_id='p-priya', start=0),
                _segment('s0b', 'Unrelated aside.', person_id='p-sam', start=500),
                _segment('s2', "Sure, I'll do it.", is_user=True, start=500 + 2 + svc.LOOK_BACK_SECONDS + 1),
            ]
        )
        people = {'p-priya': 'Priya', 'p-sam': 'Sam'}
        assert svc.resolve_counterparty(_task(), conversation, people) == svc.UNATTRIBUTED

    def test_overlapping_speech_is_the_same_exchange(self):
        conversation = _conversation(
            segments=[
                {
                    'id': 's1',
                    'text': 'Can you send it?',
                    'is_user': False,
                    'person_id': 'p-priya',
                    'start': 100.0,
                    'end': 106.0,
                },
                {'id': 's2', 'text': "Yes I'll send it.", 'is_user': True, 'start': 104.0, 'end': 107.0},
            ]
        )
        result = svc.resolve_counterparty(_task(), conversation, {'p-priya': 'Priya'})
        assert result.basis == 'speaker' and result.likely is False

    def test_an_earlier_line_ending_well_after_the_reply_starts_is_not_counted(self):
        conversation = _conversation(
            segments=[
                _segment('s0', 'Long monologue.', person_id='p-sam', start=0),
                {
                    'id': 's1',
                    'text': 'Can you send it?',
                    'is_user': False,
                    'person_id': 'p-priya',
                    'start': 100.0,
                    'end': 104.0 + svc.LOOK_BACK_OVERLAP_SECONDS + 1,
                },
                {'id': 's2', 'text': "Yes I'll send it.", 'is_user': True, 'start': 104.0, 'end': 107.0},
            ]
        )
        people = {'p-priya': 'Priya', 'p-sam': 'Sam'}
        assert svc.resolve_counterparty(_task(), conversation, people) == svc.UNATTRIBUTED

    def test_clocks_that_run_backwards_are_not_the_same_exchange(self):
        # A merged conversation: the second recording's clock restarts near zero.
        conversation = _conversation(
            segments=[
                _segment('s0', 'Can you book the venue?', person_id='p-priya', start=3000),
                _segment('s2', "I'll renew my passport.", is_user=True, start=10),
            ]
        )
        result = svc.resolve_counterparty(_task(), conversation, {'p-priya': 'Priya'})
        assert result.basis == 'conversation' and result.likely is True

    def test_lines_without_timing_are_not_counted_as_the_same_exchange(self):
        conversation = {
            'id': 'c1',
            'structured': {},
            'transcript_segments': [
                {'id': 's0', 'text': 'Send it?', 'is_user': False, 'person_id': 'p-priya'},
                {'id': 's0b', 'text': 'Hi.', 'is_user': False, 'person_id': 'p-sam'},
                {'id': 's2', 'text': "I'll send it.", 'is_user': True},
            ],
        }
        people = {'p-priya': 'Priya', 'p-sam': 'Sam'}
        assert svc.resolve_counterparty(_task(), conversation, people) == svc.UNATTRIBUTED


class TestRedaction:
    @pytest.mark.parametrize(
        'text',
        [
            'Call +1 415 555 0100 now',
            'Call (415) 555-0100 now',
            'Call 415-555-0100 now',
            'Call 415.555.0100 now',
            'Call 4155550100 now',
            'Call 555-0100 now',
            'Call +91 98765 43210 now',
            'Reach me on +44 20 7946 0958',
            'In 2026 call 415 555 0100',
            'Call me on 9123 4567',
            'ring 5550100',
            'my WhatsApp is 98765 43210',
            'Order shipped, call me on 415 555 0100',
            'see 555-0100',
            '(415) 555-0100 is his line',
            'try 98765 43210 after six',
        ],
    )
    def test_phone_numbers_by_plus_cue_or_grouping_become_phone(self, text):
        redacted = svc.redact_contact_details(text)
        assert '[phone]' in redacted and '[number]' not in redacted, redacted
        assert sum(ch.isdigit() for ch in redacted.replace('2026', '')) == 0, redacted

    @pytest.mark.parametrize(
        'text, expected',
        [
            ('Order number 4417529930 shipped', 'Order number [number] shipped'),
            ('Order no. 4417529930', 'Order no. [number]'),
            ('Invoice 2026001234 is overdue', 'Invoice [number] is overdue'),
            ('PNR 2025 0614 22 confirmed', 'PNR [number] confirmed'),
            ('ticket 12345678 is open', 'ticket [number] is open'),
            ('booking ref 4417 5299 30', 'booking ref [number]'),
        ],
    )
    def test_a_long_number_after_a_reference_word_becomes_number(self, text, expected):
        assert svc.redact_contact_details(text) == expected

    @pytest.mark.parametrize(
        'text, expected',
        [
            ("it's 4155550100", "it's [number]"),
            ('send it to 4155550100', 'send it to [number]'),
            ('The SKU is 8806094937', 'The SKU is [number]'),
            ('Revenue hit 120000000', 'Revenue hit [number]'),
            ('SSN 123-45-6789', 'SSN [number]'),
            ('Aadhaar 1234 5678 9012', 'Aadhaar [number]'),
            ('my card is 4111 1111 1111 1111', 'my card is [number]'),
            ('Amex 3782 822463 10005', 'Amex [number]'),
        ],
    )
    def test_long_unseparated_runs_and_id_shaped_numbers_become_number(self, text, expected):
        assert svc.redact_contact_details(text) == expected

    @pytest.mark.parametrize(
        'text, expected',
        [
            ('Call 4155550100 now', 'Call [phone] now'),
            ('call 555-6789', 'call [phone]'),
            ('text me on 1234 5678 9012', 'text me on [phone]'),
        ],
    )
    def test_a_phone_cue_wins_over_the_number_shapes(self, text, expected):
        assert svc.redact_contact_details(text) == expected

    @pytest.mark.parametrize(
        'text',
        [
            'We need 500-1000 samples',
            'Covered 2019-2023 in the report',
            'Plan for 300-4500 users',
            'It weighs 415 5550 kg',
            'see 12345678 for details',
            'Revenue hit 12000000 in Q3',
            'We sold 1500000 units last year',
        ],
    )
    def test_ranges_measures_and_figures_up_to_eight_digits_are_not_phones(self, text):
        assert svc.redact_contact_details(text) == text

    def test_a_spoken_domain_after_send_to_is_treated_as_an_email(self):
        # Accepted: "the team at Google dot com" after "send ... to" reads as an address.
        assert (
            svc.redact_contact_details('Send the link to the team at Google dot com') == 'Send the link to the [email]'
        )

    @pytest.mark.parametrize(
        'text',
        [
            'Due 2026-10-12 at 15:30',
            'On 10/11/2026 at 3:00 PM',
            'By 11.10.2026',
            'Budget $1,200.50 or 1,000,000 units',
            'About 3.5 million, 2,500 seats, 45%',
            'Order #12345, room 404, version 1.2.3',
            'Year 2026, 1999-2003',
            'Results for 2019 2020 2021 are in',
            'We sold 1500000 units last year',
            'Revenue hit 12000000 in Q3',
            'see 12345678 for details',
            'extension 4321',
            'Server is at 192.168.10.100 now',
            'Build v10.0.19045.2965 is out',
            'Look at this dot com bubble',
        ],
    )
    def test_plain_figures_dates_amounts_versions_ranges_and_ips_are_left_alone(self, text):
        assert svc.redact_contact_details(text) == text

    @pytest.mark.parametrize(
        'text, expected',
        [
            ('Mail priya.shah+work@corp.example.co.uk today', 'Mail [email] today'),
            ('my email is priya at gmail dot com', 'my email is [email]'),
            ('mail it to sam at acme dot co dot uk', 'mail it to [email]'),
            ('send it to priya at acme dot io', 'send it to [email]'),
            ('reach me at sam dot lee at acme dot com', 'reach me at [email]'),
            ('write to dana at corp dot com', 'write to [email]'),
        ],
    )
    def test_written_and_spoken_emails_are_redacted(self, text, expected):
        assert svc.redact_contact_details(text) == expected

    def test_spelled_out_digits_are_an_accepted_gap(self):
        text = 'call me on four one five five five five zero one zero zero'
        assert svc.redact_contact_details(text) == text


class TestFiltersCountsAndWindow:
    def test_full_name_query_finds_a_first_name_contact_and_accents_fold(self, store):
        _add_one_to_one(store, 1, name='Priya')
        _add_one_to_one(store, 2, name='Zoë Martín')

        shah = store.read(person='Priya Shah')['groups']
        assert [g['names'] for g in shah] == [['Priya']] and shah[0]['partial_match'] is True
        zoe = store.read(person='zoe martin')['groups']
        assert [g['names'] for g in zoe] == [['Zoë Martín']] and zoe[0]['partial_match'] is False
        assert store.read(person='Sam Priyanka')['groups'] == []

    def test_a_query_matching_more_than_one_person_is_partial(self, store):
        _add_one_to_one(store, 1, name='Priya Shah')
        _add_one_to_one(store, 2, name='Priya Patel')
        _add_one_to_one(store, 3, name='Sam Rivera')

        result = store.read(person='Priya')

        assert sorted(g['names'][0] for g in result['groups']) == ['Priya Patel', 'Priya Shah']
        assert all(g['partial_match'] for g in result['groups'])
        assert store.read(person='Priya Shah')['groups'][0]['partial_match'] is False

    def test_unclear_owner_count_is_not_reported_against_a_named_person(self, store):
        _add_one_to_one(store, 1, name='Priya')
        _add_one_to_one(store, 2, owner='unknown')

        assert store.read()['totals']['excluded_unknown_owner'] == 1
        filtered = store.read(person='Sam')
        assert filtered['groups'] == []
        assert filtered['totals']['excluded_unknown_owner'] == 0
        assert 'unclear owner' not in filtered['result_text']

    def test_not_checked_items_are_still_reported_under_a_person_filter(self, store):
        for index in range(1, 27):
            _add_one_to_one(store, index, name='Priya', created_offset=index)

        result = store.read(person='Priya', limit_people=20)

        assert result['totals']['not_checked'] == 1
        assert result['truncated'] is True

    def test_the_window_actually_checked_is_returned(self, store):
        assert store.read()['since'] == (NOW - timedelta(days=30)).isoformat()
        assert store.read(since='2025-01-01T00:00:00+00:00')['since'] == (NOW - timedelta(days=90)).isoformat()
        future = store.read(since='2030-01-01T00:00:00+00:00')
        assert future['since'] == NOW.isoformat()
        assert store.get_action_items.call_args.kwargs['start_date'] == NOW
        assert 'since 2026-10-11' in future['result_text']

    def test_each_conversation_is_analysed_once(self, store, monkeypatch):
        _add_one_to_one(store, 1)
        for extra in range(5):
            store.tasks.append(_task(f't1-{extra}', 'c1'))
        calls = []
        real = svc._conversation_facts
        monkeypatch.setattr(svc, '_conversation_facts', lambda conversation: calls.append(1) or real(conversation))

        result = store.read()

        assert len(calls) == 1
        assert result['groups'][0]['open_count'] == 6


@pytest.mark.parametrize(
    'overrides, expected',
    [
        ({}, True),
        ({'source': 'legacy'}, True),
        ({'deleted': True}, False),
        ({'completed': True}, False),
        ({'status': 'cancelled'}, False),
        ({'status': 'superseded'}, False),
        ({'conversation_id': None}, False),
        ({'is_locked': True}, False),
        ({'source': 'manual'}, False),
    ],
)
def test_shared_open_conversation_task_predicate(overrides, expected):
    from utils.task_predicates import is_open_conversation_task

    assert is_open_conversation_task(_task(**overrides)) is expected
