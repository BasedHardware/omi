"""Conversation extraction must produce suggestions the user can actually see.

INVARIANT I1 says extraction never writes a task. That is only half a product:
the other half is that what it *does* write reaches the Suggested surface. A
proposal nobody can see is the same as a dropped one, so these tests walk the
whole path — policy outcome, Candidate creation, and the suggested-surface
projection — rather than stopping at "a Candidate exists".
"""

from datetime import datetime, timedelta, timezone

import pytest

import routers.candidates as candidates_router
from models.action_item import EvidenceRef, TaskCreatePayload
from models.candidate import CandidateRecord
from utils.task_intelligence.backend_capture import BackendCaptureSignals, adapt_backend_capture

NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


def _capture(**signals):
    return adapt_backend_capture(
        TaskCreatePayload(description='Send the budget'),
        evidence_ref=EvidenceRef(kind='conversation', id='conversation-1', scope='canonical'),
        source_surface='conversation',
        signals=BackendCaptureSignals(**signals),
    )


def _stored(proposal, *, created_at=NOW):
    return CandidateRecord(
        **proposal.model_dump(mode='python'),
        candidate_id='cand-1',
        account_generation=0,
        idempotency_key='idem-1',
        created_at=created_at,
        expires_at=created_at + timedelta(days=2),
    )


def _visible(decision, *, created_at=NOW, now=NOW):
    assert decision.candidate is not None
    return candidates_router._is_suggested_candidate(_stored(decision.candidate, created_at=created_at), now=now)


@pytest.mark.parametrize(
    'name,signals',
    [
        ('explicit_command', dict(explicit_command=True)),
        ('clear_commitment', dict(clear_commitment=True)),
        ('direct_request', dict(direct_request=True)),
        ('inferred_next_step', dict(inferred_next_step=True)),
    ],
)
def test_every_admitted_capture_kind_becomes_a_visible_suggestion(name, signals):
    decision = _capture(
        concrete_deliverable=True,
        owner='user',
        capture_confidence=0.94,
        ownership_confidence=0.9,
        **signals,
    )

    assert decision.policy.outcome == 'pending_candidate', name
    assert decision.candidate is not None, f'{name} produced no proposal'
    assert _visible(decision), f'{name} produced a proposal the Suggested surface hides'


def test_a_suggestion_is_hidden_once_its_two_day_window_closes():
    decision = _capture(
        clear_commitment=True,
        concrete_deliverable=True,
        owner='user',
        capture_confidence=0.94,
        ownership_confidence=0.9,
    )

    assert _visible(decision, created_at=NOW - timedelta(days=1))
    assert not _visible(decision, created_at=NOW - timedelta(days=3))


def test_low_confidence_extraction_is_ignored_rather_than_written_and_hidden():
    """The floor belongs in the policy, not only in the projection.

    A proposal admitted below the surface's confidence floor would be stored
    forever and shown never. Whatever the policy admits must be visible.
    """
    for signals in (
        dict(explicit_command=True),
        dict(clear_commitment=True),
        dict(direct_request=True),
        dict(inferred_next_step=True),
    ):
        decision = _capture(
            concrete_deliverable=True,
            owner='user',
            capture_confidence=0.55,
            ownership_confidence=0.55,
            **signals,
        )
        if decision.candidate is None:
            continue
        assert _visible(decision), f'{signals} is stored but never shown'
