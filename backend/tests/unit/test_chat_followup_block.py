"""The typed chat lane's grounded closing question.

Two contracts are covered. The parser owns what a follow-up tail is: the
delimiter and everything after it always leave the visible text, and only a
specific, short, real question survives as a chip. The route owns delivery: the
persisted assistant message carries the ``followUp`` content block on a grounded
turn and carries nothing on a failed one, because a chip on a failed turn asks
the user to go one hop further into an answer they never got.
"""

import pytest

from tests.unit.test_chat_stream_error_fallback import _cleanup, _decode_done_frame, _make_client
from utils.chat_followup import (
    FOLLOWUP_DELIMITER,
    FollowUpTailStreamFilter,
    build_followup_block,
    followup_content_blocks,
    split_followup_tail,
)


def test_tail_is_lifted_off_the_visible_text():
    visible, question = split_followup_tail(
        f"You and Priya settled on shipping Thursday.\n{FOLLOWUP_DELIMITER} Who else was in that call?"
    )
    assert visible == "You and Priya settled on shipping Thursday."
    assert question == "Who else was in that call?"
    assert FOLLOWUP_DELIMITER not in visible


def test_answer_without_a_tail_is_untouched():
    assert split_followup_tail("Nothing came up for that.") == ("Nothing came up for that.", None)


def test_empty_answer_yields_no_question():
    assert split_followup_tail('') == ('', None)
    assert split_followup_tail(None) == ('', None)


@pytest.mark.parametrize(
    'tail',
    [
        'Anything else?',
        'anything else i can help with?',
        'Want more detail?',
        'Does that help?',
        'Let me know if you want more.',
        'Want me to keep going?',
    ],
)
def test_generic_tails_are_dropped_but_still_stripped(tail):
    visible, question = split_followup_tail(f"Here it is.\n{FOLLOWUP_DELIMITER} {tail}")
    assert visible == 'Here it is.'
    assert question is None


def test_overlong_tail_is_dropped():
    long_tail = ' '.join(['word'] * 30) + '?'
    visible, question = split_followup_tail(f"Answer.\n{FOLLOWUP_DELIMITER} {long_tail}")
    assert visible == 'Answer.'
    assert question is None


def test_tail_that_is_not_a_question_is_dropped():
    visible, question = split_followup_tail(f"Answer.\n{FOLLOWUP_DELIMITER} I will check that next.")
    assert visible == 'Answer.'
    assert question is None


def test_only_the_first_tail_line_is_the_question():
    visible, question = split_followup_tail(
        f"Answer.\n{FOLLOWUP_DELIMITER} When is the review due?\nAlso here is more prose."
    )
    assert visible == 'Answer.'
    assert question == 'When is the review due?'


def test_failed_turn_gets_no_block():
    assert (
        followup_content_blocks(
            'm1',
            'Who else was in that call?',
            visible_text='Something went wrong.',
            failed=True,
        )
        == []
    )


def test_refusal_or_empty_answer_gets_no_block():
    assert followup_content_blocks('m1', 'Who else was there?', visible_text='   ', failed=False) == []


def test_answer_that_is_itself_a_question_gets_no_block():
    assert (
        followup_content_blocks(
            'm1',
            'Who else was there?',
            visible_text='Which standup did you mean — Monday or Thursday?',
            failed=False,
        )
        == []
    )


def test_grounded_turn_gets_exactly_one_block_in_the_wire_shape():
    blocks = followup_content_blocks(
        'msg-7',
        'Who else was in that call?',
        visible_text='You and Priya settled on shipping Thursday.',
        failed=False,
    )
    assert blocks == [{'type': 'followUp', 'id': 'msg-7:followup', 'text': 'Who else was in that call?'}]
    assert build_followup_block('msg-7', 'Who else was in that call?') == blocks[0]


def test_stream_filter_never_shows_the_tail_even_split_across_chunks():
    stream_filter = FollowUpTailStreamFilter()
    emitted = ''.join(
        stream_filter.push(chunk)
        for chunk in ['You and Priya ', 'settled on Thursday.\n<<<FOLL', 'OWUP>>> Who else was there?']
    )
    emitted += stream_filter.flush()
    assert emitted == 'You and Priya settled on Thursday.\n'
    assert stream_filter.suppressing


def test_stream_filter_releases_text_that_only_looked_like_the_delimiter():
    stream_filter = FollowUpTailStreamFilter()
    emitted = ''.join(stream_filter.push(chunk) for chunk in ['a <<<b', ' and more'])
    emitted += stream_filter.flush()
    assert emitted == 'a <<<b and more'
    assert not stream_filter.suppressing


def _grounded_stream(answer: str, question: str):
    async def stream(*args, **kwargs):
        kwargs['callback_data']['answer'] = answer
        kwargs['callback_data']['followup'] = question
        yield None

    return stream


def test_persisted_message_carries_the_followup_block():
    client, router_module, _chat_utils, chat_db, saved = _make_client()
    try:
        router_module.execute_chat_stream = _grounded_stream(
            'You and Priya settled on shipping Thursday.', 'Who else was in that call?'
        )

        response = client.post(
            '/v2/messages',
            json={'text': 'what did priya say about the ship date', 'file_ids': []},
            headers={'X-App-Platform': 'ios'},
        )

        assert response.status_code == 200
        payload = _decode_done_frame(response.text)
        assert payload['content_blocks'] == [
            {'type': 'followUp', 'id': f"{payload['id']}:followup", 'text': 'Who else was in that call?'}
        ]
        # The chip's text is delivered once, not duplicated into the prose.
        assert payload['text'] == 'You and Priya settled on shipping Thursday.'

        ai_writes = [call.args[1] for call in chat_db.add_message.call_args_list if call.args[1].get('sender') == 'ai']
        assert len(ai_writes) == 1
        assert ai_writes[0]['content_blocks'] == payload['content_blocks']
    finally:
        _cleanup(saved)


def test_failed_turn_persists_no_followup_block():
    client, router_module, _chat_utils, chat_db, saved = _make_client()
    try:

        async def failing_stream(*args, **kwargs):
            kwargs['callback_data']['error'] = 'idle_timeout'
            kwargs['callback_data']['answer'] = 'Something went wrong on my side.'
            kwargs['callback_data']['followup'] = 'Who else was in that call?'
            yield None

        router_module.execute_chat_stream = failing_stream

        response = client.post(
            '/v2/messages',
            json={'text': 'what did priya say', 'file_ids': []},
            headers={'X-App-Platform': 'ios'},
        )

        assert response.status_code == 200
        payload = _decode_done_frame(response.text)
        assert payload['content_blocks'] == []

        ai_writes = [call.args[1] for call in chat_db.add_message.call_args_list if call.args[1].get('sender') == 'ai']
        assert len(ai_writes) == 1
        assert ai_writes[0]['content_blocks'] == []
    finally:
        _cleanup(saved)


@pytest.mark.parametrize(
    'tail',
    [
        'Who else was there? What did they decide?',
        'That was the Q3 review. Want the attendee list?',
        'Nice! Should I pull the attendee list?',
    ],
)
def test_tail_with_more_than_one_sentence_is_dropped(tail):
    """One chip carries one question; a packed tail has left the contract."""
    visible, question = split_followup_tail(f"Answer.\n{FOLLOWUP_DELIMITER} {tail}")
    assert visible == 'Answer.'
    assert question is None


@pytest.mark.parametrize(
    'tail',
    [
        'Want the notes from the 10 a.m. standup?',
        'Should I check what the 3.5 release changed?',
    ],
)
def test_one_question_survives_an_internal_period(tail):
    """A decimal or a lowercase abbreviation is not a sentence boundary."""
    visible, question = split_followup_tail(f"Answer.\n{FOLLOWUP_DELIMITER} {tail}")
    assert visible == 'Answer.'
    assert question == tail


def test_a_turn_cut_short_mid_marker_leaves_no_residue():
    """A timeout can stop the model part-way through the delimiter it was writing."""
    visible, question = split_followup_tail('You and Priya settled on Thursday.\n<<<FOLL')
    assert visible == 'You and Priya settled on Thursday.\n'
    assert question is None


def test_text_that_merely_ends_in_an_angle_bracket_is_kept():
    assert split_followup_tail('The condition is x <') == ('The condition is x <', None)
