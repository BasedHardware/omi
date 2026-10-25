"""The transcript character budget bounds every text field the reader returns."""

from utils.mcp_server.helpers import bounded_transcript_segments, conversation_card


def test_character_budget_counts_original_text():
    segments = [
        {"id": "s1", "text": "hello", "original_text": "a" * 20},
        {"id": "s2", "text": "world", "original_text": "b" * 20},
    ]

    bounded, truncated = bounded_transcript_segments(segments, max_segments=10, max_chars=10)

    assert truncated is True
    assert len(bounded) == 1
    assert bounded[0]["text"] == "hello"
    assert bounded[0]["original_text"] == "a" * 5
    assert len(bounded[0]["text"]) + len(bounded[0]["original_text"]) == 10


def test_character_budget_clipping_original_text_reports_truncation():
    bounded, truncated = bounded_transcript_segments(
        [{"id": "s1", "text": "hello", "original_text": "a" * 20}],
        max_segments=10,
        max_chars=5,
    )

    assert truncated is True
    assert bounded[0]["text"] == "hello"
    assert bounded[0]["original_text"] == ""


def test_mcp_keeps_owner_real_name_alongside_its_display_label():
    bounded, truncated = bounded_transcript_segments(
        [{'id': 's1', 'text': 'hello', 'speaker_id': 379, 'is_user': True, 'speaker_name': 'David Zhang'}],
        max_segments=10,
        max_chars=100,
        extra_keys=('speaker_name',),
    )
    assert not truncated
    assert bounded[0]['speaker_id'] is None
    assert bounded[0]['speaker_label'] == 'You'
    assert bounded[0]['speaker_name'] == 'David Zhang'


def test_developer_card_keeps_original_participant_wire_shape_while_mcp_uses_display():
    conversation = {
        'id': 'c1',
        'transcript_segments': [
            {'id': 's1', 'text': 'hello', 'speaker_id': 379, 'is_user': True},
        ],
    }
    assert conversation_card(conversation, include_display=False)['participants'] == [
        {'speaker_id': 379, 'person_id': None, 'is_user': True},
    ]
    mcp = conversation_card(conversation)['participants'][0]
    assert mcp['speaker_id'] is None
    assert mcp['speaker_key'] and mcp['speaker_label'] == 'You'
