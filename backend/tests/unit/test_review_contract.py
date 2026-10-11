from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from models.entity_pages import EntityCorrection
from models.review import EntitySummary, ReviewAnswer, ReviewItem, SamePersonItem, SpellingItem, SpeakerAnswer
from utils.review import rank_review_items

NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


def spelling(index=1):
    return ReviewItem(
        item_id=f'spelling:{index}',
        kind='spelling',
        title='Which spelling?',
        created_at=NOW,
        spelling=SpellingItem(term_id=str(index), options=['Pairform', 'Paraform'], allow_custom=True),
    )


def test_ranking_is_bounded_and_deterministic():
    left = EntitySummary(entity_id='person:a', type='person', name='A', conversation_count=4)
    right = EntitySummary(entity_id='person:b', type='person', name='B', conversation_count=2)
    merge = ReviewItem(
        item_id='same_person:ab',
        kind='same_person',
        title='Same person?',
        created_at=NOW,
        same_person=SamePersonItem(left=left, right=right, reason='Voice match'),
    )
    items = [spelling(4), spelling(2), merge, spelling(1), spelling(3)]
    assert [i.item_id for i in rank_review_items(items, 9)] == ['same_person:ab', 'spelling:1', 'spelling:2']
    assert len(rank_review_items(items, 1)) == 1
    assert rank_review_items(items, 0) == []


@pytest.mark.parametrize(
    'payload',
    [
        {},
        {'not_sure': True, 'spelling': {'value': 'X'}},
        {'spelling': {'value': 'X'}, 'same_person': {'decision': 'yes'}},
        {'speaker': {'is_me': True, 'person_id': 'p'}},
        {'speaker': {'is_me': False}},
    ],
)
def test_invalid_answers_are_rejected(payload):
    with pytest.raises(ValidationError):
        ReviewAnswer.model_validate(payload)


def test_single_answer_and_not_sure():
    assert ReviewAnswer(not_sure=True).not_sure
    assert ReviewAnswer(speaker=SpeakerAnswer(is_me=True)).speaker.is_me


@pytest.mark.parametrize('text', ['', '   ', 'x' * 2001])
def test_correction_bounds(text):
    with pytest.raises(ValidationError):
        EntityCorrection(text=text)


def test_correction_trim_and_item_payload_match():
    assert EntityCorrection(text='  My role changed.  ').text == 'My role changed.'
    payload = spelling().model_dump()
    payload['kind'] = 'task'
    with pytest.raises(ValidationError):
        ReviewItem.model_validate(payload)


def test_agent_proposal_and_answer_contract():
    from models.dream_agent import Edit
    from models.review import AgentProposalItem, AgentProposalAnswer, ReviewItemV2, ReviewAnswerV2

    edit = Edit(kind='close_task', target='action_items/toy-task', reason='Done', evidence=['conversations/toy'])
    item = ReviewItemV2(
        item_id='agent_proposal:toy',
        kind='agent_proposal',
        title='Close toy task?',
        created_at=NOW,
        agent_proposal=AgentProposalItem(edit=edit),
    )
    assert ReviewItemV2.model_validate(item.model_dump()).agent_proposal.edit == edit
    assert ReviewAnswerV2(agent_proposal=AgentProposalAnswer(decision='accept')).agent_proposal.decision == 'accept'
    for body in [
        {'agent_proposal': {'decision': 'yes'}},
        {'agent_proposal': {'decision': 'accept', 'edit': edit.model_dump()}},
        {'not_sure': True, 'agent_proposal': {'decision': 'accept'}},
    ]:
        with pytest.raises(ValidationError):
            ReviewAnswerV2.model_validate(body)
    with pytest.raises(ValidationError):
        AgentProposalItem()


def test_legacy_review_contract_rejects_agent_payloads():
    from models.review import ReviewItemV2, AgentProposalItem
    from models.dream_agent import Edit

    item = ReviewItemV2(
        item_id='agent_proposal:toy',
        kind='agent_proposal',
        title='Review task',
        created_at=NOW,
        agent_proposal=AgentProposalItem(
            edit=Edit(kind='close_task', target='action_items/toy', reason='Done', evidence=['conversations/toy'])
        ),
    )
    with pytest.raises(ValidationError):
        ReviewItem.model_validate(item.model_dump())
    with pytest.raises(ValidationError):
        ReviewAnswer.model_validate({'agent_proposal': {'decision': 'accept'}})
