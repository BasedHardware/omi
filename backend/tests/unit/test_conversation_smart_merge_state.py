"""The smart-merge Jev state must render the benchmark template exactly (synthetic text only)."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from utils.conversations.smart_merge_state import (
    QUESTIONS,
    Fragment,
    build_state,
    state_sha256,
    transcript_head,
    transcript_tail,
)

T0 = datetime(2026, 9, 28, 23, 10, tzinfo=timezone.utc)  # 19:10 in New York


def _fragment(fid, start_min, end_min, title, overview):
    return Fragment(fid, T0 + timedelta(minutes=start_min), T0 + timedelta(minutes=end_min), title, overview)


def _segments(*lines):
    return [
        {'text': text, 'speaker_id': speaker, 'is_user': speaker is None, 'start': float(i), 'end': float(i) + 1}
        for i, (speaker, text) in enumerate(lines)
    ]


def test_state_matches_the_benchmark_template_line_for_line():
    stretch = [_fragment('s1', -40, -25, 'Grocery run', 'Picked up bread.')]
    a = _fragment('a', -20, 0, 'Dinner at home', 'Two friends cook pasta.')
    b = _fragment('b', 5, 17, 'Evening walk', 'The same friends walk to the park.')
    state = build_state(
        source='omi',
        a=a,
        a_segments=_segments((None, 'Pass the salt.'), (1, 'Here you go. ')),
        b=b,
        b_segments=_segments((1, 'Nice night for a walk.'), (None, 'Let us take the long way.')),
        stretch=stretch,
        tz=ZoneInfo('America/New_York'),
    )
    expected = '\n\n'.join(
        [
            'Omi is a personal recorder that splits what it hears into conversations: a conversation ends after '
            'about two minutes without speech, and the next speech starts a new conversation. Below are two '
            'consecutive conversations captured by the Omi pendant (a wearable microphone): A (earlier) and B (the '
            'next one). Titles and summaries are AI-generated. Transcripts are imperfect speech-to-text: speaker '
            'labels are unreliable, and the audio can include TV or video, phone calls, or the owner dictating to '
            'AI assistants. The device owner is "the user".',
            'Timing (local time): A ran Mon 2026-09-28 18:50 to 19:10 (20 min). B started Mon 2026-09-28 19:15, '
            '5 min after A ended, and ran 12 min.',
            'Earlier conversations in the same stretch, oldest first (each began within 30 minutes of the previous '
            'one ending; A continues this stretch):\n- 18:30 Grocery run: Picked up bread.',
            'Conversation A\nTitle: Dinner at home\nSummary: Two friends cook pasta.',
            "End of A's transcript (last part):\nUser: Pass the salt.\nSpeaker 1: Here you go.",
            'Conversation B\nTitle: Evening walk\nSummary: The same friends walk to the park.',
            "Start of B's transcript (first part):\nSpeaker 1: Nice night for a walk.\nUser: Let us take the long way.",
        ]
    )
    assert state == expected


def test_stretch_section_is_omitted_without_predecessors_and_device_strings_follow_the_benchmark():
    a = _fragment('a', 0, 10, 'A', 'x')
    b = _fragment('b', 15, 20, 'B', 'y')
    state = build_state(source='desktop', a=a, a_segments=[], b=b, b_segments=[], stretch=[], tz=timezone.utc)
    assert 'Earlier conversations' not in state
    assert 'captured by the Omi desktop app (microphone and system audio)' in state
    assert 'A ran Mon 2026-09-28 23:10 to 23:20 (10 min)' in state


def test_stretch_summaries_are_cut_to_400_characters_but_a_and_b_keep_theirs():
    long = 'w' * 900
    a = _fragment('a', 0, 10, 'A', long)
    b = _fragment('b', 15, 20, 'B', long)
    stretch = [_fragment('s', -20, -5, 'S', long)]
    state = build_state(source='omi', a=a, a_segments=[], b=b, b_segments=[], stretch=stretch, tz=timezone.utc)
    assert f'- 22:50 S: {"w" * 400}\n\nConversation A' in state
    assert f'Summary: {long}' in state


def test_tail_and_head_keep_whole_lines_within_the_excerpt_budget():
    segments = _segments(*[(1, f'line {i} ' + 'z' * 40) for i in range(200)])
    tail = transcript_tail(segments, limit=200)
    head = transcript_head(segments, limit=200)
    assert len(tail) <= 200 and len(head) <= 200
    assert tail.splitlines()[-1].startswith('Speaker 1: line 199')
    assert head.splitlines()[0].startswith('Speaker 1: line 0')
    assert all(line.startswith('Speaker 1: line ') for line in tail.splitlines() + head.splitlines())


def test_one_oversized_line_is_cut_rather_than_dropped():
    segments = _segments((None, 'q' * 5000))
    assert len(transcript_tail(segments)) == 2500
    assert transcript_head(segments).startswith('User: qqq')


def test_question_is_wording_a_noul():
    question = QUESTIONS['decision']
    assert question['type'] == 'noul'
    assert question['instructions'].startswith('Is B a continuation of the same real-world occasion as A')
    assert set(question['criteria']) == {'true', 'false'}


def test_state_hash_is_stable_and_textless():
    digest = state_sha256('synthetic state')
    assert digest == state_sha256('synthetic state') and len(digest) == 64 and 'synthetic' not in digest


def test_ledger_round_trip_keeps_times_and_rejects_malformed_entries():
    fragment = _fragment('f', 0, 3, 'Title', 'Overview')
    assert Fragment.from_ledger_entry(fragment.as_ledger_entry()) == fragment
    assert Fragment.from_ledger_entry({'id': 'x', 'started_at': 'not a time'}) is None
