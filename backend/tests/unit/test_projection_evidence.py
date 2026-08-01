"""Evidence-packet assembly for projections.

A projection's subject is selected by one LLM pass over a bounded 7-day packet of the
user's own material. These tests pin the deterministic half of that: what enters the
packet, what bounds it, and which rung of the degradation ladder a given corpus lands on.

The ladder matters more than it looks. Its bottom rung is *generate nothing* — an empty
corpus must produce a refusal rather than an invented projection, because a projection with
no evidence behind it is exactly the evidence-free artifact this feature exists to replace.
"""

from datetime import datetime, timedelta, timezone

from utils.projections.evidence import (
    MAX_CONVERSATIONS,
    MAX_OVERVIEW_CHARS,
    EvidenceTier,
    assemble_packet,
)

NOW = datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)


def _conversation(days_ago: int, overview: str, *, title: str = 'A conversation', **overrides):
    conversation = {
        'id': f'conv-{days_ago}',
        'created_at': NOW - timedelta(days=days_ago),
        'discarded': False,
        'structured': {'title': title, 'overview': overview, 'category': 'personal'},
    }
    conversation.update(overrides)
    return conversation


def _action_item(description: str, *, created_days_ago: int = 3, due_days_ago=None, completed: bool = False):
    return {
        'id': f'item-{description}',
        'description': description,
        'completed': completed,
        'created_at': NOW - timedelta(days=created_days_ago),
        'due_at': None if due_days_ago is None else NOW - timedelta(days=due_days_ago),
    }


def test_rich_corpus_carries_conversation_prose_oldest_first():
    packet = assemble_packet(
        conversations=[_conversation(1, 'Talked about the move again.'), _conversation(5, 'First mention of a move.')],
        action_items=[],
        goal=None,
        now=NOW,
    )

    assert packet.tier is EvidenceTier.RICH
    assert [c.overview for c in packet.conversations] == ['First mention of a move.', 'Talked about the move again.']

    # Recurrence is judged by reading prose across days, so the rendered packet has to carry
    # the dates alongside the prose — not just the text.
    rendered = packet.as_prompt_text()
    assert 'First mention of a move.' in rendered
    assert '2026-07-23' in rendered and '2026-07-27' in rendered
    assert '[conversation:conv-5]' in rendered


def test_discarded_and_overview_less_conversations_are_excluded():
    packet = assemble_packet(
        conversations=[
            _conversation(1, 'Kept.'),
            _conversation(2, 'Discarded.', discarded=True),
            _conversation(3, '   '),
            _conversation(4, 'No structure at all', structured=None),
        ],
        action_items=[],
        goal=None,
        now=NOW,
    )

    assert [c.overview for c in packet.conversations] == ['Kept.']


def test_open_action_items_carry_computed_age_and_overdue_days():
    packet = assemble_packet(
        conversations=[_conversation(1, 'Something.')],
        action_items=[
            _action_item('Return company laptop', created_days_ago=14, due_days_ago=13),
            _action_item('Already done', completed=True),
        ],
        goal=None,
        now=NOW,
    )

    assert [item.description for item in packet.action_items] == ['Return company laptop']
    item = packet.action_items[0]
    assert item.age_days == 14
    assert item.overdue_days == 13
    assert 'overdue 13' in packet.as_prompt_text()
    assert '[action_item:item-Return company laptop]' in packet.as_prompt_text()


def test_action_item_with_a_future_due_date_is_not_overdue():
    packet = assemble_packet(
        conversations=[],
        action_items=[_action_item('Book the flight', created_days_ago=2, due_days_ago=-4)],
        goal=None,
        now=NOW,
    )

    assert packet.action_items[0].overdue_days is None


def test_thin_corpus_falls_back_to_open_action_items():
    packet = assemble_packet(
        conversations=[],
        action_items=[_action_item('Return company laptop', created_days_ago=14, due_days_ago=13)],
        goal={'title': 'Leave the job well'},
        now=NOW,
    )

    assert packet.tier is EvidenceTier.THIN
    assert packet.goal is not None and packet.goal.title == 'Leave the job well'


def test_a_goal_alone_is_not_something_to_project_from():
    packet = assemble_packet(conversations=[], action_items=[], goal={'title': 'Leave the job well'}, now=NOW)

    assert packet.tier is EvidenceTier.EMPTY


def test_empty_corpus_is_empty():
    packet = assemble_packet(conversations=[], action_items=[], goal=None, now=NOW)

    assert packet.tier is EvidenceTier.EMPTY
    assert packet.conversations == () and packet.action_items == ()


def test_packet_is_bounded_by_conversation_count_and_overview_length():
    packet = assemble_packet(
        conversations=[_conversation(days_ago, 'x' * (MAX_OVERVIEW_CHARS + 500)) for days_ago in range(60)],
        action_items=[],
        goal=None,
        now=NOW,
    )

    assert len(packet.conversations) == MAX_CONVERSATIONS
    # The most recent conversations survive the cap, not an arbitrary slice of the window.
    assert packet.conversations[-1].id == 'conv-0'
    assert all(len(c.overview) <= MAX_OVERVIEW_CHARS for c in packet.conversations)


def test_signal_summary_records_what_selected_from_without_copying_the_material():
    packet = assemble_packet(
        conversations=[_conversation(1, 'Talked about the move again.')],
        action_items=[_action_item('Return company laptop')],
        goal={'title': 'Leave the job well'},
        now=NOW,
    )

    summary = packet.signal_summary()

    assert summary == {
        'tier': 'rich',
        'window_days': packet.window_days,
        'conversation_count': 1,
        'conversation_ids': ['conv-1'],
        'action_item_count': 1,
        'action_item_ids': ['item-Return company laptop'],
        'has_goal': True,
    }
    # Metadata travels further than the packet does; it must not carry the prose itself.
    assert 'Talked about the move again.' not in str(summary)


def test_reference_ids_distinguish_grounding_material_from_goal_context():
    packet = assemble_packet(
        conversations=[_conversation(1, 'Talked about the move again.')],
        action_items=[_action_item('Return company laptop')],
        goal={'title': 'Leave the job well'},
        now=NOW,
    )

    assert packet.grounding_reference_ids() == (
        'conversation:conv-1',
        'action_item:item-Return company laptop',
    )
    assert packet.reference_ids() == (
        'conversation:conv-1',
        'action_item:item-Return company laptop',
        'goal:active',
    )

    receipts = packet.receipts_for(('action_item:item-Return company laptop', 'conversation:conv-1'))
    assert [(receipt['source'], receipt['label']) for receipt in receipts] == [
        ('action_item', 'Return company laptop'),
        ('conversation', 'A conversation'),
    ]
    assert 'Talked about the move again.' not in str(receipts)
