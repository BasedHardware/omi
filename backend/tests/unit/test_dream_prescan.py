"""Dream pre-scan: bounded signals, fail-open, shadow vs serve, and hit recall."""

import asyncio
import json
import logging
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from config import dream_levers
from config.dream_session import SessionLimits
from models.agent_tools import VerificationBatch, Verification
from tests.unit.test_dream_cleanup_edits import UID, store  # noqa: F401  (store: fixture for runtime)
from tests.unit.test_dream_harness_runtime import runtime  # noqa: F401  (fixture)
from tests.unit.test_dream_session import call, turn
from utils import dream_agent, dream_prescan
from utils.agent_capabilities.session import serialized_bytes
from utils.dream_harness_transport import MAIN_LANE, VERIFY_LANE
from utils.llm.shaped_agent import Turn

DUE = datetime(2026, 10, 30, 9, tzinfo=timezone.utc)


class FakeSnapshot:
    def __init__(self, snapshot_id, row):
        self.id = snapshot_id
        self._row = row

    def to_dict(self):
        return self._row


class FakeQuery:
    def __init__(self, client, rows):
        self._client = client
        self._rows = list(rows)

    def select(self, fields):
        self._client.projections.append(list(fields))
        return self

    def where(self, *args, filter=None):
        self._client.filters.append(filter)
        return self

    def order_by(self, field, direction=None):
        return self

    def limit(self, count):
        self._client.limits.append(count)
        return self

    def stream(self, **kwargs):
        return iter([FakeSnapshot(row_id, row) for row_id, row in self._rows])


class FakeOwner:
    def __init__(self, client):
        self._client = client

    def collection(self, name):
        return FakeQuery(self._client, self._client.collections.get(name, []))


class FakeUsers:
    def __init__(self, client):
        self._client = client

    def document(self, uid):
        assert uid
        return FakeOwner(self._client)


class FakeClient:
    def __init__(self, collections=None):
        self.collections = collections or {}
        self.projections = []
        self.filters = []
        self.limits = []

    def collection(self, name):
        assert name == 'users'
        return FakeUsers(self)


def person(name, **extra):
    return {'name': name, **extra}


def task(description, **extra):
    return {'source': 'conversation', 'description': description, 'due_at': DUE, 'owner': 'me', **extra}


def generated(description, **extra):
    now = DUE
    return {**task(description), 'account_generation': 3, 'created_at': now, 'updated_at': now, **extra}


# --- people_dupes ---------------------------------------------------------------------------------


def test_people_dupes_match_normalized_names_aliases_and_one_edit():
    rows = [
        ('p1', person('José García')),
        ('p2', person('jose garcia')),
        ('p3', person('Bob', aliases=['Robert Smith'])),
        ('p4', person('Robert Smith')),
        ('p5', person('Katherine')),
        ('p6', person('Katharine')),
        ('p7', person('Alice')),
        ('p8', person('Alicia')),
        ('p9', person('Ann')),
        ('p10', person('Anne')),
    ]
    result = dream_prescan.scan(UID, firestore_client=FakeClient({'people': rows}))
    assert result['counts'] == {'people_dupes': 6, 'junk_names': 0, 'task_dupes': 0}
    assert {ref for ref in result['refs']} == {
        'people/p1',
        'people/p2',
        'people/p3',
        'people/p4',
        'people/p5',
        'people/p6',
    }


def test_people_dupes_exclude_protected_and_dismissed_people():
    rows = [
        ('kept-1', person('Dana Nguyen')),
        ('confirmed', person('Dana Nguyen', user_confirmed=True)),
        ('created', person('Dana Nguyen', is_user_created=True)),
        ('pinned', person('Dana Nguyen', pinned=True)),
        ('evidence', person('Dana Nguyen', label_evidence={'manual': 1})),
        ('dismissed', person('Dana Nguyen', is_dismissed=True)),
    ]
    result = dream_prescan.scan(UID, firestore_client=FakeClient({'people': rows}))
    assert result['counts']['people_dupes'] == 0 and result['refs'] == []


# --- junk_names -----------------------------------------------------------------------------------


def test_junk_names_flag_clearly_non_person_names_only():
    rows = [
        ('j1', person('')),
        ('j2', person('A')),
        ('j3', person('123')),
        ('j4', person('speaker 1')),
        ('j5', person('Person 12')),
        ('j6', person('unknown')),
        ('j7', person('thanks')),
        ('j8', person('hello')),
        ('j9', person('Canadian')),
        ('j10', person('thanks team')),
        ('j11', person('Anna Müller')),
    ]
    result = dream_prescan.scan(UID, firestore_client=FakeClient({'people': rows}))
    assert result['counts'] == {'people_dupes': 0, 'junk_names': 8, 'task_dupes': 0}
    assert {ref for ref in result['refs']} == {
        'people/j1',
        'people/j2',
        'people/j3',
        'people/j4',
        'people/j5',
        'people/j6',
        'people/j7',
        'people/j8',
    }


def test_junk_names_exclude_protected_and_dismissed_people():
    rows = [
        ('dismissed', person('123', is_dismissed=True)),
        ('pinned', person('123', pinned=True)),
        ('confirmed', person('speaker 1', user_confirmed=True)),
    ]
    result = dream_prescan.scan(UID, firestore_client=FakeClient({'people': rows}))
    assert result['counts']['junk_names'] == 0 and result['refs'] == []


# --- task_dupes -----------------------------------------------------------------------------------


def test_task_dupes_group_by_merge_metadata_and_similar_descriptions():
    rows = [
        ('t1', generated('Email Alex about the contract')),
        ('t2', generated('Email Alex about the contracts')),
        ('t3', generated('Email Alex about the contract', due_at=DUE.replace(hour=10))),
        ('t4', generated('Email Alex about the contract', owner='someone-else')),
        ('t5', generated('Email Alex about the contract', account_generation=4)),
        ('t6', generated('Buy groceries for the dinner party')),
    ]
    result = dream_prescan.scan(UID, firestore_client=FakeClient({'action_items': rows}))
    assert result['counts']['task_dupes'] == 2
    assert result['refs'] == ['action_items/t1', 'action_items/t2']


def test_task_dupes_use_the_merge_tasks_predicate():
    now = DUE
    # Every protected variant shares the merge group and text with the eligible
    # baseline, so a single predicate hole would surface as a duplicate pair.
    rows = [
        ('good', generated('Ship the widget')),
        ('manual', {**generated('Ship the widget'), 'manual_assignment': True}),
        ('edited', generated('Ship the widget', updated_at=now.replace(hour=8))),
        ('linked', generated('Ship the widget', external_task_id='todoist:1')),
        (
            'external',
            {**task('Ship the widget', account_generation=3, created_at=now, updated_at=now), 'source': 'app'},
        ),
        ('done', generated('Ship the widget', completed=True)),
        ('deleted', generated('Ship the widget', deleted=True)),
        ('cancelled', generated('Ship the widget', status='cancelled')),
        ('created-missing', {k: v for k, v in generated('Ship the widget').items() if k != 'created_at'}),
    ]
    result = dream_prescan.scan(UID, firestore_client=FakeClient({'action_items': rows}))
    assert result['counts']['task_dupes'] == 0 and result['refs'] == []


# --- bounds and fail-open -------------------------------------------------------------------------


def test_scan_reads_are_bounded_and_refs_are_capped():
    junk = [(f'junk-{index}', person(str(index))) for index in range(20)]
    client = FakeClient(
        {'people': junk, 'action_items': [('t1', generated('Same task')), ('t2', generated('Same task'))]}
    )
    result = dream_prescan.scan(UID, firestore_client=client)
    assert client.limits == [dream_prescan.PEOPLE_LIMIT, dream_prescan.TASK_LIMIT]
    assert len(client.projections) == 2
    assert len(result['refs']) == dream_prescan.MAX_REFS == 16
    # Dismiss candidates lead, in scan order; the two duplicate tasks still counted.
    assert result['refs'] == ['people/' + row_id for row_id, _ in junk][: dream_prescan.MAX_REFS]
    assert result['counts'] == {'people_dupes': 0, 'junk_names': 20, 'task_dupes': 2}


def test_scan_fails_open_on_any_error(monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise RuntimeError('store unavailable')

    monkeypatch.setattr(dream_prescan.review_store, 'client', broken)
    with caplog.at_level(logging.WARNING, logger='utils.dream_prescan'):
        result = dream_prescan.scan(UID)
    assert result == {'refs': [], 'counts': {'people_dupes': 0, 'junk_names': 0, 'task_dupes': 0}}
    assert 'event=dream_lever_error lever=prescan exc=RuntimeError' in caplog.text


# --- serve targets --------------------------------------------------------------------------------


def test_serve_targets_prepends_and_dedupes():
    seed = {'targets': ['people/a', 'conversations/one'], 'vocabulary': []}
    served = dream_prescan.serve_targets(seed, ['people/a', 'people/b', 'people/b'], SessionLimits())
    assert served == 1
    assert seed['targets'] == ['people/b', 'people/a', 'conversations/one']


def test_serve_targets_respects_the_byte_ceiling_and_never_drops_dirty_targets():
    limits = SessionLimits(bucket='light')
    ceiling = dream_prescan.dream_seed.byte_ceiling(limits)
    seed = {'targets': ['conversations/one'], 'vocabulary': []}
    seed['vocabulary'] = ['x' * (ceiling - serialized_bytes(seed) - 40)]
    assert serialized_bytes(seed) <= ceiling
    refs = ['people/' + str(index) for index in range(16)]
    served = dream_prescan.serve_targets(seed, refs, limits)
    assert served < 16 and serialized_bytes(seed) <= ceiling
    assert seed['targets'][-1] == 'conversations/one'
    assert seed['targets'][:served] == refs[:served]
    # Nothing fits at all: dirty targets stay and the seed is unchanged.
    seed['vocabulary'] = ['x' * (ceiling - serialized_bytes({'targets': ['conversations/one'], 'vocabulary': []}))]
    before = deepcopy(seed)
    assert dream_prescan.serve_targets(seed, ['people/none'], limits) == 0
    assert seed == before


# --- hits -----------------------------------------------------------------------------------------


def test_applied_hits_counts_only_applied_outcomes_on_scan_refs():
    report = {
        'proposed': {
            'edits': [
                {'key': 'k1', 'kind': 'dismiss_person', 'target': 'people/j1'},
                {'key': 'k2', 'kind': 'retire_task', 'target': 'action_items/t9'},
                {'key': 'k3', 'kind': 'merge_tasks', 'target': 'action_items/t1#old', 'other': 'action_items/t2'},
            ],
            'questions': [{'key': 'k4', 'kind': 'question', 'target': 'people/j1'}],
        },
        'outcomes': [
            {'key': 'k1', 'kind': 'dismiss_person', 'status': 'applied'},
            {'key': 'k2', 'kind': 'retire_task', 'status': 'applied'},
            {'key': 'k3', 'kind': 'merge_tasks', 'status': 'verifier_disagree'},
            {'key': 'k4', 'kind': 'question', 'status': 'suggested'},
        ],
    }
    assert dream_prescan.applied_hits(report, ['people/j1', 'action_items/t2']) == 1
    assert dream_prescan.applied_hits(report, []) == 0


# --- pass-level shadow and serve (Firestore fake, scripted model) ----------------------------------


def _finish_only(captured):
    async def model(uid, lane, mount, messages):
        if lane != MAIN_LANE:
            pytest.fail('No staged work should need verification')
        captured.append(deepcopy(messages))
        return turn([call('finish', {'summary': 'Checked synthetic records', 'notes': ''})], tokens=10)

    return model


def _capturing_scripted(captured):
    async def model(uid, lane, mount, messages):
        if lane == MAIN_LANE:
            captured.append(deepcopy(messages))
            return turn(
                [
                    call(
                        'propose_edit',
                        {
                            'edit': {
                                'kind': 'dismiss_person',
                                'target': 'people/junk',
                                'evidence': ['conversations/one'],
                                'reason': 'Synthetic junk profile',
                                'value': 4,
                            }
                        },
                    ),
                    call(
                        'finish',
                        {'summary': 'Checked synthetic records', 'notes': 'Look for repeated junk profiles'},
                        2,
                    ),
                ],
                tokens=10,
            )
        assert lane == VERIFY_LANE
        batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
        return Turn(
            tokens=20,
            prompt_tokens=15,
            cached_tokens=5,
            value=VerificationBatch(
                decisions=[
                    Verification(id=row['id'], agree=True, reason='Synthetic independent evidence check')
                    for row in batch
                ]
            ),
        )

    return model


def _message_text(message):
    content = message.get('content')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ''.join(str(part.get('text') or '') for part in content if isinstance(part, dict))
    return ''


def _seed_payloads(captured):
    """The seed JSON of each captured turn; the seed rides the first user message."""
    payloads = []
    for messages in captured:
        for message in messages:
            text = _message_text(message)
            if 'UNTRUSTED SEED DATA\n' in text:
                payloads.append(json.loads(text.split('UNTRUSTED SEED DATA\n', 1)[1]))
    return payloads


def test_prescan_shadow_records_the_lever_and_changes_no_seed(runtime, monkeypatch):
    scan = {'refs': ['people/prescan-a'], 'counts': {'people_dupes': 0, 'junk_names': 1, 'task_dupes': 0}}
    monkeypatch.setattr(dream_prescan, 'scan', lambda uid, **kwargs: scan)
    captured = []
    report = asyncio.run(dream_agent.run_pass(UID, turn=_finish_only(captured)))
    assert report['status'] == 'complete', report
    assert report['levers']['prescan'] == {
        'arm': 'shadow',
        'targets': 1,
        'people_dupes': 0,
        'junk_names': 1,
        'task_dupes': 0,
        'served': 0,
        'hits': 0,
    }
    seeds = _seed_payloads(captured)
    assert seeds and all('people/prescan-a' not in seed.get('targets', []) for seed in seeds)


def _as_hunt(monkeypatch, hunt_pass=True):
    acquire = dream_agent.dream_store.acquire

    def hunt(*args, **kwargs):
        lease = acquire(*args, **kwargs)
        return lease if lease is None else {**lease, 'hunt': hunt_pass}

    monkeypatch.setattr(dream_agent.dream_store, 'acquire', hunt)


def test_prescan_serve_never_reorders_a_pass_admitted_for_dirty_work(runtime, monkeypatch):
    monkeypatch.setenv(dream_levers.PRESCAN_MODE_ENV, 'serve')
    _as_hunt(monkeypatch, False)
    scan = {'refs': ['people/prescan-a'], 'counts': {'people_dupes': 0, 'junk_names': 1, 'task_dupes': 0}}
    monkeypatch.setattr(dream_prescan, 'scan', lambda uid, **kwargs: scan)
    captured = []
    report = asyncio.run(dream_agent.run_pass(UID, turn=_finish_only(captured)))
    assert report['levers']['prescan']['served'] == 0
    assert all('people/prescan-a' not in seed.get('targets', []) for seed in _seed_payloads(captured))


def test_prescan_serve_prepends_targets_and_counts_hits(runtime, monkeypatch):
    monkeypatch.setenv(dream_levers.PRESCAN_MODE_ENV, 'serve')
    _as_hunt(monkeypatch)
    scan = {
        'refs': ['people/prescan-a', 'people/junk'],
        'counts': {'people_dupes': 0, 'junk_names': 2, 'task_dupes': 0},
    }
    monkeypatch.setattr(dream_prescan, 'scan', lambda uid, **kwargs: scan)
    captured = []
    report = asyncio.run(dream_agent.run_pass(UID, turn=_capturing_scripted(captured)))
    assert report['status'] == 'complete', report
    assert report['levers']['prescan'] == {
        'arm': 'serve',
        'targets': 2,
        'people_dupes': 0,
        'junk_names': 2,
        'task_dupes': 0,
        'served': 1,
        'hits': 1,
    }
    seeds = _seed_payloads(captured)
    assert seeds
    targets = seeds[0]['targets']
    # Pre-scan refs lead the dirty targets, without duplicating people/junk.
    assert targets[0] == 'people/prescan-a'
    assert targets.count('people/junk') == 1
    assert targets[-1] != 'people/prescan-a'


def test_people_projection_never_reads_voice_data():
    client = FakeClient({'people': [('p1', person('Dana Nguyen'))]})
    dream_prescan.scan(UID, firestore_client=client)
    people_projection = client.projections[0]
    assert 'speaker_embedding' not in people_projection and 'speech_samples' not in people_projection
    assert {'name', 'user_confirmed', 'is_user_created', 'pinned', 'label_evidence'} <= set(people_projection)
