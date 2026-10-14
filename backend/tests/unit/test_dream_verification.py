"""History-free independent verification and fail-closed decisions."""

import asyncio
from types import SimpleNamespace

from models.dream_harness import Verification, VerificationBatch
from utils.dream_verify import verify, disposition, batches
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
    assert messages_seen[0] == messages_seen[1] and len(messages_seen[0]) == 2
    assert 'Canadian' in messages_seen[0][1]['content']


def test_verifier_missing_duplicate_or_unknown_ids_cannot_authorize_apply():
    async def turn(mount, messages):
        return Turn(tokens=12, value=VerificationBatch(decisions=[]))

    votes, calls = asyncio.run(verify([proposal()], turn, tokens=10000, deadline_seconds=5))
    assert calls == 2 and disposition(votes['synthetic-proposal']) == 'split'
    assert disposition([False, False]) == 'disagree'
    assert disposition([True, False]) == disposition([True]) == 'split'


def test_oversized_evidence_is_not_silently_truncated_into_support():
    item = proposal()
    item.records['people/junk']['name'] = 'x' * 30000
    assert list(batches([item])) == []
