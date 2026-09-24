from datetime import datetime, timedelta, timezone

from models.speaker_tag_prompts import SpeakerTagPromptKind, SpeakerTagPromptOrigin
from utils.speaker_tag_prompts import selection

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def _segment(sid, speaker, start, end, text='hello there how are you doing', **extra):
    return {'id': sid, 'speaker_id': speaker, 'start': start, 'end': end, 'text': text, **extra}


def _conversation(cid='c1', hours_ago=2, segments=None, **extra):
    return {
        'id': cid,
        'started_at': NOW - timedelta(hours=hours_ago),
        'status': 'completed',
        'audio_files': [{'chunk_timestamps': [1.0]}],
        'structured': {'title': 'Coffee chat'},
        'transcript_segments': segments or [],
        **extra,
    }


def _select(conversations, *, owner_has_voice=True, named_allowed=True, answered=None, people=None, limit=4):
    return selection.select_prompts(
        conversations,
        now=NOW,
        owner_has_voice=owner_has_voice,
        named_allowed=named_allowed,
        answered=answered or set(),
        people=people or {},
        limit=limit,
    )


def test_owner_missed_asks_is_this_you_on_loudest_unnamed_voice():
    conversation = _conversation(
        segments=[
            _segment('a', 0, 0, 6),
            _segment('b', 1, 6, 9),
            _segment('c', 0, 9, 14),
        ]
    )
    prompts = _select([conversation])
    assert prompts[0].kind == SpeakerTagPromptKind.owner_check
    assert prompts[0].origin == SpeakerTagPromptOrigin.unnamed
    assert prompts[0].speaker_id == 0
    assert prompts[0].conversation_title == 'Coffee chat'


def test_named_prompts_hidden_without_entitlement_but_owner_check_stays_free():
    conversation = _conversation(
        segments=[
            _segment('a', 0, 0, 8, is_user=True),
            _segment('b', 1, 8, 16),
            _segment('c', 2, 16, 24, person_id='p1'),
        ]
    )
    prompts = _select([conversation], named_allowed=False, people={'p1': 'Sam'})
    assert {p.kind for p in prompts} == {SpeakerTagPromptKind.owner_check}
    assert prompts[0].origin == SpeakerTagPromptOrigin.auto_user


def test_auto_person_match_becomes_confirm_prompt_with_name():
    conversation = _conversation(
        segments=[
            _segment('a', 0, 0, 3, is_user=True),
            _segment('b', 1, 3, 11, person_id='p1'),
        ]
    )
    prompts = _select([conversation], people={'p1': 'Sam'})
    confirm = [p for p in prompts if p.kind == SpeakerTagPromptKind.confirm_person]
    assert confirm and confirm[0].suggested_person_id == 'p1' and confirm[0].suggested_person_name == 'Sam'
    assert prompts[0].kind == SpeakerTagPromptKind.confirm_person


def test_short_mixed_and_manually_decided_voices_are_not_asked():
    conversation = _conversation(
        segments=[
            _segment('a', 0, 0, 3, is_user=True),
            _segment('b', 1, 3, 6),  # too short
            _segment('c', 2, 6, 20),  # decided by the user below
        ],
        manual_speaker_assignments={'speakers': {'2': {'generation': 1, 'person_id': None, 'is_user': False}}},
    )
    assert _select([conversation]) == []


def test_other_voice_between_segments_splits_the_clip():
    conversation = _conversation(
        segments=[
            _segment('a', 0, 0, 3, is_user=True),
            _segment('b', 1, 3, 6),
            _segment('x', 0, 6, 7, is_user=True),
            _segment('c', 1, 7, 10),
        ]
    )
    assert _select([conversation]) == []


def test_clip_overlapping_another_diarized_voice_is_not_asked():
    conversation = _conversation(
        segments=[
            _segment('a', 0, 0, 8),
            _segment('b', 1, 3, 4),
        ]
    )
    assert _select([conversation]) == []


def test_capped_clip_overlapping_another_voice_is_not_asked():
    overlapping = _conversation(
        segments=[
            _segment('a', 0, 0, 30),
            _segment('b', 1, 14, 16),
        ]
    )
    assert _select([overlapping]) == []
    clear = _conversation(
        segments=[
            _segment('a', 0, 0, 30),
            _segment('b', 1, 2, 4),
        ]
    )
    prompt = _select([clear])[0]
    assert (prompt.clip_start, prompt.clip_end) == (10.0, 20.0)


def test_a_clean_run_wins_over_a_longer_overlapping_run_for_the_same_voice():
    conversation = _conversation(
        segments=[
            _segment('a', 0, 0, 20),
            _segment('x', 1, 10, 11),
            _segment('b', 0, 30, 37),
        ]
    )
    prompts = _select([conversation])
    assert len(prompts) == 1
    assert prompts[0].speaker_id == 0
    assert prompts[0].segment_ids == ['b']
    assert (prompts[0].clip_start, prompts[0].clip_end) == (30.0, 37.0)


def test_touching_clip_boundary_is_not_an_overlap():
    conversation = _conversation(
        segments=[
            _segment('a', 0, 0, 8),
            _segment('b', 1, 8, 9),
        ]
    )
    prompts = _select([conversation])
    assert prompts and (prompts[0].clip_start, prompts[0].clip_end) == (0.0, 8.0)


def test_overlapping_same_speaker_segments_keep_the_full_span():
    conversation = _conversation(
        segments=[
            _segment('a', 0, 0, 8),
            _segment('b', 0, 3, 5),
        ]
    )
    prompt = _select([conversation])[0]
    assert (prompt.clip_start, prompt.clip_end) == (0.0, 8.0)


def test_conversations_outside_48h_or_without_audio_are_skipped():
    old = _conversation('old', hours_ago=49, segments=[_segment('a', 0, 0, 9)])
    silent = _conversation('silent', segments=[_segment('a', 0, 0, 9)], audio_files=[])
    locked = _conversation('locked', segments=[_segment('a', 0, 0, 9)], is_locked=True)
    assert _select([old, silent, locked]) == []


def test_answered_prompts_are_not_repeated():
    conversation = _conversation(segments=[_segment('a', 0, 0, 9)])
    first = _select([conversation])
    assert first
    assert _select([conversation], answered={first[0].id}) == []


def test_clip_is_capped_and_centered():
    conversation = _conversation(segments=[_segment('a', 0, 0, 30)])
    prompt = _select([conversation])[0]
    assert prompt.clip_end - prompt.clip_start == selection.MAX_CLIP_SECONDS
    assert prompt.clip_start == 10.0


def test_excerpt_only_covers_segments_inside_the_clip():
    conversation = _conversation(
        segments=[
            _segment('a', 0, 0, 7, 'before the clip'),
            _segment('b', 0, 7, 13, 'inside the clip'),
            _segment('c', 0, 13, 20, 'after the clip'),
        ]
    )
    prompt = _select([conversation])[0]
    assert (prompt.clip_start, prompt.clip_end) == (5.0, 15.0)
    assert prompt.excerpt == 'inside the clip'


def test_a_long_single_segment_can_leave_an_empty_excerpt():
    conversation = _conversation(segments=[_segment('a', 0, 0, 20, 'one long utterance')])
    prompt = _select([conversation])[0]
    assert prompt.excerpt == ''


def test_limits_per_conversation_and_owner_checks():
    conversations = []
    for index in range(4):
        conversations.append(
            _conversation(
                f'c{index}',
                hours_ago=index + 1,
                segments=[_segment(f's{index}{s}', s, s * 10, s * 10 + 9) for s in range(4)],
            )
        )
    prompts = _select(conversations, limit=5)
    assert len(prompts) == 5
    assert sum(p.kind == SpeakerTagPromptKind.owner_check for p in prompts) <= selection.MAX_OWNER_CHECKS
    per_conversation = {}
    for prompt in prompts:
        per_conversation[prompt.conversation_id] = per_conversation.get(prompt.conversation_id, 0) + 1
    assert max(per_conversation.values()) <= selection.MAX_PER_CONVERSATION


def test_identify_suggests_recent_people_not_already_in_that_conversation():
    other = _conversation('c0', hours_ago=5, segments=[_segment('z', 0, 0, 2, person_id='p2')])
    conversation = _conversation(
        segments=[
            _segment('a', 0, 0, 2, is_user=True),
            _segment('b', 1, 2, 4, person_id='p1'),
            _segment('c', 2, 4, 12),
        ]
    )
    prompts = _select([conversation, other], people={'p1': 'Sam', 'p2': 'Ana'})
    identify = [p for p in prompts if p.kind == SpeakerTagPromptKind.identify]
    assert identify and identify[0].suggested_person_ids == ['p2']


def test_prompt_id_is_stable():
    assert selection.prompt_id('c', 1, SpeakerTagPromptKind.identify) == selection.prompt_id(
        'c', 1, SpeakerTagPromptKind.identify
    )
    assert selection.prompt_id('c', 1, SpeakerTagPromptKind.identify) != selection.prompt_id(
        'c', 1, SpeakerTagPromptKind.owner_check
    )
