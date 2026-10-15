"""Deterministic synthetic recurring-error hunt through the actual v2 runtime."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
import pytest
from fastapi import HTTPException
from pathlib import Path

from config.dream_session import SessionLimits
from database import review_changes, review_store
from models.agent_tools import VerificationBatch, Verification
from models.agent_refs import base_ref
from tests.unit.test_dream_harness_runtime import runtime, store, UID
from tests.unit.test_dream_session import call, turn as tool_turn
from utils.agent_capabilities import search as dream_search
from utils.agent_capabilities import tools as dream_tools
from utils import dream_agent, dream_seed
from utils.agent_capabilities.evidence import EvidenceRecords
from utils.dream_harness_transport import MAIN_LANE, input_bytes
from utils.llm.shaped_agent import Turn


@pytest.mark.parametrize(
    'kind,fields',
    [
        ('dismiss_person', {}),
        ('retire_task', {}),
        ('merge_tasks', {'other': 'action_items/two'}),
        ('merge_conversations', {'other': 'conversations/two'}),
        ('set_language', {'before': 'xx', 'after': 'en'}),
    ],
)
def test_scripted_cleanup_corpus_verifies_applies_and_undoes(runtime, kind, fields):
    from tests.unit.test_dream_cleanup_edits import edit

    operation = edit(kind, **fields)
    if kind == 'retire_task':
        operation = operation.model_copy(update={'reason': 'Another speaker\'s obligation was filed to the owner'})
        runtime.rows[('users', UID, 'conversations', 'one')]['transcript_segments'][0].update(
            text='I am the invented other speaker. I will draft the workshop outline for my own project, and this obligation belongs to me.',
            is_user=False,
        )
    elif kind == 'merge_tasks':
        runtime.rows[('users', UID, 'action_items', 'two')][
            'description'
        ] = 'Create the outline for the invented workshop.'
    original = deepcopy(runtime.rows[('users', UID, *operation.target.split('/'))])

    async def model(uid, lane, mount, messages):
        if lane == MAIN_LANE:
            return tool_turn(
                [
                    call('propose_edit', {'edit': operation.model_dump(mode='json')}),
                    call('finish', {'summary': 'Synthetic cleanup'}, 2),
                ]
            )
        batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
        return Turn(
            tokens=10,
            value=VerificationBatch(
                decisions=[
                    Verification(id=row['id'], agree=True, reason='Scripted synthetic evidence') for row in batch
                ]
            ),
        )

    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert report['outcomes'][0]['status'] == 'applied', report
    assert report['verifier_calls'] == 2
    change = next(
        review_store.decode_doc(UID, row)['change']
        for path, row in runtime.rows.items()
        if path[2:3] == ('review_changes',)
    )
    review_changes.set_undone(UID, change['change_id'], True)
    assert runtime.rows[('users', UID, *operation.target.split('/'))] == original


@pytest.mark.parametrize('kind', ['merge_people', 'vocabulary'])
def test_scripted_split_person_and_vocabulary_corpus(runtime, kind):
    from tests.unit.test_dream_cleanup_edits import person_merge_records, person_merge

    if kind == 'merge_people':
        person_merge_records(runtime)
        tool = call('propose_edit', {'edit': person_merge().model_dump(mode='json')})
    else:
        tool = call(
            'learn_term',
            {'term': {'kind': 'project', 'spelling': 'Qorbi', 'aliases': [], 'evidence': ['conversations/one']}},
        )

    async def model(uid, lane, mount, messages):
        if lane == MAIN_LANE:
            return tool_turn([tool, call('finish', {'summary': 'Synthetic identity and vocabulary'}, 2)])
        batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
        return Turn(
            tokens=10,
            value=VerificationBatch(
                decisions=[
                    Verification(id=row['id'], agree=True, reason='Scripted synthetic evidence') for row in batch
                ]
            ),
        )

    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert report['outcomes'][0]['status'] == 'applied', report
    change = next(
        review_store.decode_doc(UID, row)['change']
        for path, row in runtime.rows.items()
        if path[2:3] == ('review_changes',)
    )
    review_changes.set_undone(UID, change['change_id'], True)
    if kind == 'merge_people':
        assert 'redirect_entity_id' not in runtime.rows[('users', UID, 'knowledge_nodes', 'person:right')]
    else:
        assert not review_store.decode_doc(UID, runtime.rows[('users', UID, 'dream_vocabulary', 'current')]).get(
            'source'
        )


@pytest.mark.parametrize('size,bucket', [(8, 'light'), (40, 'medium'), (90, 'heavy')])
def test_scripted_session_cost_by_bucket(runtime, monkeypatch, size, bucket):
    from tests.unit.test_dream_harness_runtime import scripted

    source = dream_seed.load

    def seed(uid, caps):
        data, records, dirty, _ = source(uid, caps)
        return data, records, dirty, SessionLimits.for_size(size)

    monkeypatch.setattr(dream_seed, 'load', seed)
    model = scripted([True, True])

    async def counted(uid, lane, mount, messages):
        return measured(await model(uid, lane, mount, messages), mount, messages)

    report = asyncio.run(dream_agent.run_pass(UID, turn=counted))
    assert report['status'] == 'complete' and report['outcomes'][0]['status'] == 'applied', report
    assert report['size_bucket'] == bucket and report['turns'] == 1 and report['verifier_calls'] == 2
    assert report['accounted_tokens'] <= SessionLimits.for_size(size).tokens
    destination = os.getenv('DREAM_SYNTHETIC_BUCKET_RECEIPTS')
    if destination:
        path = Path(destination)
        data = json.loads(path.read_text()) if path.exists() else {}
        data[bucket] = {
            key: report[key]
            for key in ('size_bucket', 'turns', 'verifier_calls', 'accounted_tokens', 'cost_usd_upper_bound')
        }
        path.write_text(json.dumps(data, indent=2) + '\n')


NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)


def corpus(db):
    # Every byte is invented. Correct speech + a confirmed name expose a repeated
    # generated-summary defect across 90 captures, independently of dirty work.
    for path in list(db.rows):
        if path[:2] == ('users', UID) and path[2:3] in [('conversations',), ('people',), ('action_items',)]:
            del db.rows[path]
    db.rows[('users', UID, 'people', 'right')] = {'id': 'right', 'name': 'Qorbi', 'is_user_created': True}
    for index in range(90):
        key = f'replay-{index:03}'
        db.rows[('users', UID, 'conversations', key)] = {
            'id': key,
            'status': 'completed',
            'created_at': NOW,
            'structured': {
                'title': 'Qorby workshop',
                'overview': 'Qorby plans the invented workshop.',
                'sections': [
                    {
                        'heading': 'Qorby plan',
                        'body_markdown': 'Qorby will draft the sample outline.',
                        'source_segment_ids': ['segment-one'],
                    }
                ],
                'note_claims': [
                    {
                        'target': '/sections/0/body_markdown',
                        'text': 'Qorby will draft the sample outline.',
                        'evidence_ids': ['unchanged-evidence-id'],
                        'provenance': 'said',
                    }
                ],
            },
            'transcript_segments': [
                {
                    'id': 'segment-one',
                    'text': 'Qorbi is the confirmed spelling. Qorbi will draft the sample outline.',
                    'start': 0,
                    'end': 5,
                    'is_user': True,
                }
            ],
        }


def current(db):
    return {
        '/'.join(path[2:]): deepcopy(row)
        for path, row in db.rows.items()
        if path[:2] == ('users', UID) and len(path) == 4 and path[2] in {'conversations', 'people'}
    }


def measured(result, mount, messages):
    # Scripted deterministic token units, not a real tokenizer/provider bill.
    # They depend on the real serialized mount, seed, tools and loop history.
    prompt = math.ceil(input_bytes(messages, mount) / 4)
    output = math.ceil(
        len(
            json.dumps(
                (
                    result.value.model_dump(mode='json')
                    if isinstance(result.value, VerificationBatch)
                    else list(result.tool_calls)
                ),
                default=str,
            ).encode()
        )
        / 4
    )
    result.prompt_tokens = prompt
    result.completion_tokens = output
    result.tokens = prompt + output
    result.cached_tokens = 0
    return result


def test_hunt_finds_90_summary_typos_resubmits_and_applies_25_with_exact_undo(runtime, monkeypatch):
    corpus(runtime)
    keys = [f'replay-{index:03}' for index in range(90)]
    pages = []

    def keyword(*, uid, query, limit, page, **kwargs):
        assert uid == UID and query == 'Qorby'
        pages.append(page)
        return keys[(page - 1) * limit : page * limit]

    monkeypatch.setattr(dream_search, 'keyword_search_conversation_ids', keyword)

    def lookup(ref):
        collection, key = base_ref(ref).split('/', 1)
        return deepcopy(runtime.rows.get(('users', UID, collection, key)))

    monkeypatch.setattr(dream_tools, 'proposal_record', lambda uid, ref, snapshot: lookup(ref))

    async def read(source, ref, request=None):
        assert source.uid == UID
        return lookup(ref)

    monkeypatch.setattr(dream_search.OwnerSearch, 'read', read)
    monkeypatch.setattr(dream_search.OwnerSearch, 'hydrate', read)
    monkeypatch.setattr(
        dream_seed,
        'load',
        lambda uid, caps: (
            {'targets': [], 'vocabulary': [], 'confirmed_people': [{'ref': 'people/right', 'name': 'Qorbi'}]},
            EvidenceRecords(),
            [],
            SessionLimits.for_size(91),
        ),
    )
    step = 0

    async def model(uid, lane, mount, messages):
        nonlocal step
        if lane != MAIN_LANE:
            batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
            assert len(messages) == 2 and 'UNTRUSTED SEED' not in messages[-1]['content']
            result = Turn(
                value=VerificationBatch(
                    decisions=[
                        Verification(
                            id=row['id'],
                            agree=True,
                            reason='Explicit correct spelling in speech and a confirmed profile',
                        )
                        for row in batch
                    ]
                )
            )
            return measured(result, mount, messages)
        step += 1
        if step <= 5:
            arguments = {'query': 'Qorby', 'collections': ['conversations'], 'limit': 20}
            if step > 1:
                arguments['cursor'] = 'lexical:' + str(step)
            return measured(tool_turn([call('search', arguments)]), mount, messages)
        if step == 6:
            refs = ['conversations/' + key for key in keys[:25]] + ['people/right']
            return measured(
                tool_turn([call('read', {'refs': refs[index : index + 8]}, index) for index in range(0, len(refs), 8)]),
                mount,
                messages,
            )
        assert step == 7
        edits = [
            {
                'kind': 'spelling',
                'target': 'conversations/' + key,
                'before': 'Qorby',
                'after': 'Qorbi',
                'reason': 'Synthetic recurring summary typo',
                'evidence': ['conversations/' + key, 'people/right'],
                'value': 4,
            }
            for key in keys[:25]
        ]
        invalid = {key: value for key, value in edits[0].items() if key != 'evidence'}
        calls = [call('propose_edit', {'edit': invalid}, 0)]
        calls.extend(call('propose_edit', {'edit': edit}, index + 1) for index, edit in enumerate(edits))
        calls.append(
            call(
                'finish',
                {
                    'summary': 'Found repeated synthetic summary typos.',
                    'notes': 'Continue the Qorby lexical hunt beyond the first 25 corrected captures.',
                },
                27,
            )
        )
        return measured(tool_turn(calls), mount, messages)

    before = deepcopy(runtime.rows[('users', UID, 'conversations', keys[0])])
    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert report['status'] == 'complete', str(report)
    assert pages == [1, 2, 3, 4, 5] and report['size_bucket'] == 'heavy'
    assert report['resubmits_succeeded'] == 1 and report['rejected']['schema'] == 1
    assert sum(row['status'] == 'applied' for row in report['outcomes']) == 25
    after = runtime.rows[('users', UID, 'conversations', keys[0])]
    assert after['structured']['title'] == 'Qorbi workshop'
    assert after['structured']['note_claims'][0]['text'].startswith('Qorbi')
    assert after['structured']['note_claims'][0]['evidence_ids'] == ['unchanged-evidence-id']
    assert after['transcript_segments'] == before['transcript_segments']
    change = next(
        review_store.decode_doc(UID, row)['change']
        for path, row in runtime.rows.items()
        if path[2:3] == ('review_changes',) and review_store.decode_doc(UID, row)['change']['refs'][0]['id'] == keys[0]
    )
    assert change['context'] and change['before'] == 'Qorby' and change['after'] == 'Qorbi'
    review_changes.set_undone(UID, change['change_id'], True)
    assert runtime.rows[('users', UID, 'conversations', keys[0])] == before
    receipt = {
        key: report.get(key)
        for key in (
            'size_bucket',
            'turns',
            'verifier_calls',
            'tokens',
            'accounted_tokens',
            'cost_usd_upper_bound',
            'cached_tokens',
            'uncached_tokens',
            'tool_counts',
            'rejected',
            'resubmits_succeeded',
        )
    }
    receipt.update(
        captures_discovered=90, changes_applied=25, usage_basis='scripted serialized bytes / 4; no provider call'
    )
    destination = os.getenv('DREAM_SYNTHETIC_REPLAY_RECEIPT')
    if destination:
        Path(destination).write_text(json.dumps(receipt, indent=2) + '\n')


def test_heavy_budget_reads_past_large_and_unreadable_search_hits(runtime, monkeypatch):
    # Nine ~100KB decoys would exhaust a heavy budget if search charged full rows.
    # The editable capture is last and stays under one read call.
    decoys = [f'decoy-{index}' for index in range(9)]
    runtime.rows[('users', UID, 'people', 'right')] = {'id': 'right', 'name': 'Qorbi', 'is_user_created': True}
    for key in decoys:
        runtime.rows[('users', UID, 'conversations', key)] = {
            'id': key,
            'status': 'completed',
            'created_at': NOW,
            'structured': {'title': 'Synthetic decoy', 'overview': 'Synthetic decoy overview'},
            'transcript_segments': [{'id': 'segment-one', 'text': 'x' * 100000, 'start': 0, 'end': 5, 'is_user': True}],
        }
    runtime.rows[('users', UID, 'conversations', 'target')] = {
        'id': 'target',
        'status': 'completed',
        'created_at': NOW,
        'structured': {
            'title': 'Qorby workshop',
            'overview': 'Qorby plans the invented workshop.',
            'sections': [
                {
                    'heading': 'Qorby plan',
                    'body_markdown': 'Qorby will draft the sample outline.',
                    'source_segment_ids': ['segment-one'],
                }
            ],
            'note_claims': [
                {
                    'target': '/sections/0/body_markdown',
                    'text': 'Qorby will draft the sample outline.',
                    'evidence_ids': ['unchanged-evidence-id'],
                    'provenance': 'said',
                }
            ],
        },
        'transcript_segments': [
            {
                'id': 'segment-one',
                'text': 'Qorbi is the confirmed spelling. Qorbi will draft the sample outline.',
                'start': 0,
                'end': 5,
                'is_user': True,
            }
        ],
    }
    order = [*decoys, 'dead', 'raising', 'target']

    def keyword(*, uid, query, limit, page, **kwargs):
        assert uid == UID and query == 'Qorby' and page == 1
        return order

    monkeypatch.setattr(dream_search, 'keyword_search_conversation_ids', keyword)

    def lookup(ref):
        _collection, key = base_ref(ref).split('/', 1)
        if key == 'raising':
            raise HTTPException(404, 'Synthetic missing capture')
        row = runtime.rows.get(('users', UID, _collection, key))
        return deepcopy(row) if row else None

    monkeypatch.setattr(dream_tools, 'proposal_record', lambda uid, ref, snapshot: lookup(ref))

    async def load(source, ref, request=None):
        assert source.uid == UID
        return lookup(ref)

    monkeypatch.setattr(dream_search.OwnerSearch, 'read', load)
    monkeypatch.setattr(dream_search.OwnerSearch, 'hydrate', load)
    monkeypatch.setattr(
        dream_seed,
        'load',
        lambda uid, caps: (
            {'targets': [], 'vocabulary': [], 'confirmed_people': [{'ref': 'people/right', 'name': 'Qorbi'}]},
            EvidenceRecords(),
            [],
            SessionLimits.for_size(91),
        ),
    )
    step = 0

    async def model(uid, lane, mount, messages):
        nonlocal step
        if lane != MAIN_LANE:
            batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
            result = Turn(
                value=VerificationBatch(
                    decisions=[
                        Verification(
                            id=row['id'],
                            agree=True,
                            reason='Explicit correct spelling in speech and a confirmed profile',
                        )
                        for row in batch
                    ]
                )
            )
            return measured(result, mount, messages)
        step += 1
        if step == 1:
            return measured(
                tool_turn([call('search', {'query': 'Qorby', 'collections': ['conversations'], 'limit': 20})]),
                mount,
                messages,
            )
        if step == 2:
            return measured(
                tool_turn([call('read', {'refs': ['conversations/target', 'people/right']})]), mount, messages
            )
        return measured(
            tool_turn(
                [
                    call(
                        'propose_edit',
                        {
                            'edit': {
                                'kind': 'spelling',
                                'target': 'conversations/target',
                                'before': 'Qorby',
                                'after': 'Qorbi',
                                'reason': 'Synthetic recurring summary typo',
                                'evidence': ['conversations/target', 'people/right'],
                                'value': 4,
                            }
                        },
                    ),
                    call('finish', {'summary': 'Corrected the synthetic summary.'}, 2),
                ]
            ),
            mount,
            messages,
        )

    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert report['status'] == 'complete', str(report)
    assert report['size_bucket'] == 'heavy'
    assert report['tool_counts'].get('search', 0) >= 1 and report['tool_counts'].get('read', 0) >= 1
    assert any(row['status'] == 'applied' for row in report['outcomes']), {
        'outcomes': report.get('outcomes'),
        'rejected': report.get('rejected'),
        'read_bytes': report.get('read_bytes'),
        'tool_counts': report.get('tool_counts'),
    }
    assert report['read_bytes'] < 80000
    assert report['read_bytes'] < SessionLimits.for_size(91).read_bytes
    assert runtime.rows[('users', UID, 'conversations', 'target')]['structured']['title'] == 'Qorbi workshop'
