"""History-free independent verification and fail-closed decisions."""

import asyncio
from types import SimpleNamespace

from models.agent_tools import Verification, VerificationBatch
from utils.dream_verify import verify, disposition, batches, minimal_context
from utils.llm.shaped_agent import Turn


def proposal():
    return SimpleNamespace(
        id='synthetic-proposal',
        refs=('people/junk',),
        records={'people/junk': {'name': 'Canadian'}},
        payload=lambda: {'id': 'synthetic-proposal', 'kind': 'dismiss_person', 'operation': {'reason': 'Junk'}},
    )


def test_two_independent_batched_invocations_have_identical_evidence_without_history():
    messages_seen = []

    async def turn(mount, messages):
        messages_seen.append(messages)
        return Turn(
            tokens=12,
            value=VerificationBatch(
                decisions=[Verification(id='synthetic-proposal', agree=True, reason='Evidence supports junk')]
            ),
        )

    votes, calls = asyncio.run(verify([proposal()], turn, tokens=10000, deadline_seconds=5))
    assert calls == 2 and disposition(votes['synthetic-proposal']) == 'agree'
    assert messages_seen[0][0] != messages_seen[1][0]
    assert messages_seen[0][1] == messages_seen[1][1] and len(messages_seen[0]) == 2
    assert '"reason"' not in messages_seen[0][1]['content']
    assert 'Canadian' in messages_seen[0][1]['content']


def test_verifier_missing_duplicate_or_unknown_ids_cannot_authorize_apply():
    async def turn(mount, messages):
        return Turn(tokens=12, value=VerificationBatch(decisions=[]))

    votes, calls = asyncio.run(verify([proposal()], turn, tokens=10000, deadline_seconds=5))
    assert calls == 2 and disposition(votes['synthetic-proposal']) == 'unverified'
    assert disposition([False, False]) == 'disagree'
    assert disposition([True, False]) == 'split'
    assert disposition([True]) == 'unverified'


def test_oversized_evidence_is_not_silently_truncated_into_support():
    item = proposal()
    item.records['people/junk']['name'] = 'x' * 30000
    assert list(batches([item])) == []


def test_fragment_verifier_receives_exact_citation_and_neighbors_without_other_content():
    segments = [{'id': str(index), 'text': 'Synthetic speech ' + str(index), 'start': index} for index in range(7)]
    records = {
        'conversations/one': {
            'id': 'one',
            'transcript_segments': segments,
            'structured': {'overview': 'Unrelated summary'},
            'photos': ['unrelated'],
        }
    }
    context = minimal_context('conversations/one#3', records)
    assert context['cited_segment'] == segments[3]
    assert context['transcript_segments'] == segments[2:5]
    assert 'structured' not in context and 'photos' not in context
    assert minimal_context('conversations/one#missing', records) is None
    assert minimal_context('conversations/one', records)['transcript_segments'] == segments
