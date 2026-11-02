"""Immediate guard feedback and model-directed hunting on the real sanctioned loop."""

import asyncio
from copy import deepcopy
import json

from config.dream_session import SessionLimits
from models.agent_refs import base_ref
from tests.unit.test_dream_cleanup_edits import store, records, UID
from utils.agent_capabilities import tools as dream_tools
from utils.agent_capabilities.evidence import EvidenceRecords
from utils.agent_capabilities.session import Session
from utils.llm.shaped_agent import Turn


def test_guard_feedback_distinguishes_stale_scope_and_schema_repairs():
    from database.review_store import ReviewConflict
    from models.agent_tools import ProposeEdit
    from pydantic import ValidationError
    from utils.agent_capabilities.session import rejection

    assert rejection(ReviewConflict('Dream memory changed'))['reason'] == 'agent_memory_changed'
    assert (
        rejection(ReviewConflict('Replacement must share privacy, subject and attribute'))['reason']
        == 'agent_memory_scope_mismatch'
    )
    failure = rejection(RuntimeError('Synthetic private text'))
    assert failure['code'] == 'agent_stale_or_unavailable' and failure['retryable'] is False
    try:
        ProposeEdit.model_validate(
            {
                'edit': {
                    'kind': 'merge_tasks',
                    'target': 'action_items/one',
                    'reason': 'Synthetic duplicate',
                    'evidence': ['conversations/one'],
                }
            }
        )
    except ValidationError as error:
        feedback = rejection(error)
        assert feedback['errors'][0]['message'] == 'A merge needs a distinct other ref and preserves its text'
    else:
        raise AssertionError('Merge without other must be rejected')


def call(name, arguments, index=1):
    return {
        'id': 'synthetic-call-' + str(index),
        'type': 'function',
        'function': {'name': name, 'arguments': json.dumps(arguments)},
    }


def turn(calls, tokens=10):
    return Turn(
        tokens=tokens,
        prompt_tokens=tokens,
        cached_tokens=0,
        tool_calls=tuple(calls),
        messages=({'role': 'assistant', 'content': None, 'tool_calls': calls},),
    )


class Source:
    def __init__(self, db):
        self.db = db
        self.searches = []

    async def read(self, ref):
        return records(self.db).get(base_ref(ref))

    async def search(self, request):
        self.searches.append(request)
        return {
            'results': [{'ref': 'people/junk', 'snippet': 'Canadian'}],
            'cursors': {},
            'counts': {},
            'complete': True,
        }


def session(db, monkeypatch, *, limits=None, seed_records=True):
    source = Source(db)
    monkeypatch.setattr(dream_tools, 'proposal_record', lambda uid, ref, snapshot: records(db).get(base_ref(ref)))
    seen = EvidenceRecords(records(db)) if seed_records else EvidenceRecords()
    return Session(
        UID,
        source,
        limits or SessionLimits(),
        {'targets': list(seen), 'vocabulary': []},
        authority='dream',
        records=seen,
    )


def test_missing_merge_field_can_be_repaired_and_counted_as_resubmission(store, monkeypatch):
    active = session(store, monkeypatch)
    operation = {
        'kind': 'merge_tasks',
        'target': 'action_items/one',
        'reason': 'Synthetic duplicate obligation',
        'evidence': ['conversations/one'],
    }
    first = asyncio.run(active.execute([call('propose_edit', {'edit': operation})]))
    assert 'distinct other ref' in first[0]['content']
    repaired = asyncio.run(active.execute([call('propose_edit', {'edit': {**operation, 'other': 'action_items/two'}})]))
    assert '"status": "staged"' in repaired[0]['content']
    assert active.counters['resubmits_succeeded'] == 1 and len(active.staged) == 1


def test_missing_evidence_is_returned_and_successful_resubmission_is_counted_without_writes(store, monkeypatch):
    active = session(store, monkeypatch)
    edit = {'kind': 'dismiss_person', 'target': 'people/junk', 'reason': 'Synthetic junk detection'}
    requests = []

    async def model(mount, messages):
        requests.append(deepcopy(messages))
        if len(requests) == 1:
            return turn([call('propose_edit', {'edit': edit})])
        assert '"reason": "schema"' in messages[-1]['content']
        assert 'evidence' in messages[-1]['content']
        return turn(
            [
                call('propose_edit', {'edit': {**edit, 'evidence': ['conversations/one']}}),
                call('finish', {'summary': 'Staged one synthetic correction.'}, 2),
            ]
        )

    before = deepcopy(store.rows)
    result = asyncio.run(active.run(model, deadline_seconds=5))
    assert result.reason == 'finished' and len(active.staged) == 1
    assert active.counters['resubmits_succeeded'] == 1
    assert active.rejections['schema'] == 1
    assert requests[0] == requests[1][: len(requests[0])]
    assert store.rows == before and not store.transactions


def test_same_turn_resubmission_resolves_rejected_call_before_finish(store, monkeypatch):
    active = session(store, monkeypatch)
    edit = {'kind': 'dismiss_person', 'target': 'people/junk', 'reason': 'Synthetic junk detection'}

    async def model(mount, messages):
        return turn(
            [
                call('propose_edit', {'edit': edit}),
                call('propose_edit', {'edit': {**edit, 'evidence': ['conversations/one']}}, 2),
                call('finish', {'summary': 'Staged one synthetic correction.'}, 3),
            ]
        )

    result = asyncio.run(active.run(model, deadline_seconds=5))

    assert result.reason == 'finished'
    assert len(active.staged) == 1
    assert active.counters['resubmits_succeeded'] == 1
    assert active.rejections['schema'] == 1


def test_empty_backlog_can_search_read_and_stage_hunt_work(store, monkeypatch):
    active = session(store, monkeypatch, seed_records=False)
    step = 0

    async def model(mount, messages):
        nonlocal step
        step += 1
        if step == 1:
            return turn([call('search', {'collections': ['people'], 'query': 'Canadian'})])
        if step == 2:
            return turn([call('read', {'refs': ['people/junk']})])
        return turn(
            [
                call(
                    'propose_edit',
                    {
                        'edit': {
                            'kind': 'dismiss_person',
                            'target': 'people/junk',
                            'reason': 'Synthetic junk detection',
                            'evidence': ['people/junk'],
                        }
                    },
                ),
                call('finish', {'summary': 'Checked a synthetic person.'}, 2),
            ]
        )

    result = asyncio.run(active.run(model, deadline_seconds=5))
    assert result.reason == 'finished' and len(active.staged) == 1
    assert active.source.searches and active.read_bytes > 0


def test_unknown_refs_and_oversized_reads_return_feedback_without_authorizing_edits(store, monkeypatch):
    active = session(store, monkeypatch, limits=SessionLimits(read_call_bytes=8, read_bytes=8), seed_records=False)
    active.known.add('conversations/one')
    replies = asyncio.run(active.execute([call('read', {'refs': ['conversations/foreign', 'conversations/one']})]))
    assert 'agent_unknown_ref' in replies[0]['content']
    assert 'agent_read_byte_budget' in replies[0]['content']
    assert not active.records and not active.staged


def test_turn_and_token_exhaustion_keep_previously_staged_edits_for_verification(store, monkeypatch):
    active = session(store, monkeypatch, limits=SessionLimits(turns=1))

    async def model(mount, messages):
        return turn(
            [
                call(
                    'propose_edit',
                    {
                        'edit': {
                            'kind': 'dismiss_person',
                            'target': 'people/junk',
                            'reason': 'Synthetic junk detection',
                            'evidence': ['people/junk'],
                        }
                    },
                )
            ]
        )

    result = asyncio.run(active.run(model, deadline_seconds=5))
    assert result.reason == 'turn_budget' and len(active.staged) == 1


def test_malformed_tool_payloads_and_unknown_tools_do_not_abort_the_session(store, monkeypatch):
    active = session(store, monkeypatch)
    replies = asyncio.run(
        active.execute(
            [call('propose_edit', {'edit': 'not an object'}), call('invented-tool', {}), call('propose_edit', {})]
        )
    )
    assert len(replies) == 3 and active.rejections['schema'] == 2
    assert active.rejections['agent_unknown_tool'] == 1 and not active.staged


def test_all_profiles_bound_light_users_without_a_static_verifier_hold():
    light, medium, heavy = SessionLimits.for_size(3), SessionLimits.for_size(20), SessionLimits.for_size(1000)
    assert light.turns == heavy.turns == 64 and light.read_bytes < heavy.read_bytes
    assert light.tokens == 375000 and medium.tokens == 625000 and heavy.tokens == 1000000
    assert light.verification_tokens == medium.verification_tokens == heavy.verification_tokens == 0
    assert SessionLimits.for_size(3, token_ceiling=32000).tokens == 32000
