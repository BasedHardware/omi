"""Manual merge: a manually tagged source must not hand its speaker ids to another source's voices.

``_merge_transcript_segments`` keeps a source's numeric speaker ids verbatim when that
source carries manual (or carried) labels, because the manual receipt still names those
numbers. Previously one such source switched reallocation off for *every* source, so an
automatic voice from a second conversation kept its own provider-local ``speaker_id`` and
collided with the manually tagged voice. In the merged conversation the assign-speaker
route and the client group segments by ``speaker_id``, so tagging one of them relabelled
both. Automatic sources are now renumbered after reserving the kept ids.
"""

from datetime import datetime, timedelta, timezone

from utils.conversations.merge_conversations import _merge_transcript_segments

AT = datetime(2026, 5, 30, 10, tzinfo=timezone.utc)


def _conversation(cid, offset_seconds, segments):
    return {
        'id': cid,
        'started_at': AT + timedelta(seconds=offset_seconds),
        'finished_at': AT + timedelta(seconds=offset_seconds + 10),
        'transcript_segments': segments,
    }


def _segment(text, speaker_id, **extra):
    segment = {
        'id': text,
        'text': text,
        'speaker': f'SPEAKER_{speaker_id:02d}',
        'speaker_id': speaker_id,
        'speaker_id_scope': f'conn:{text}',
        'is_user': False,
        'start': 0.0,
        'end': 5.0,
    }
    segment.update(extra)
    return segment


def _by_text(merged):
    return {segment['text']: segment for segment in merged}


def test_automatic_source_is_renumbered_past_a_manually_tagged_source():
    manual = _conversation('A', 0, [_segment('alice', 0, speaker_label_source='manual', person_id='p-alice')])
    automatic = _conversation('B', 3600, [_segment('stranger', 0), _segment('friend', 1)])

    merged = _by_text(_merge_transcript_segments([manual, automatic]))

    assert merged['alice']['speaker_id'] == 0
    assert merged['alice']['person_id'] == 'p-alice'
    assert merged['stranger']['speaker_id'] != 0
    assert merged['friend']['speaker_id'] != 0
    assert merged['stranger']['speaker_id'] != merged['friend']['speaker_id']


def test_manual_source_keeps_its_numbers_whatever_its_position():
    automatic = _conversation('A', 0, [_segment('stranger', 0)])
    manual = _conversation(
        'B',
        3600,
        [_segment('alice', 0, speaker_label_source='manual'), _segment('bob', 1, speaker_label_source='manual')],
    )

    merged = _by_text(_merge_transcript_segments([automatic, manual]))

    assert merged['alice']['speaker_id'] == 0
    assert merged['bob']['speaker_id'] == 1
    assert merged['stranger']['speaker_id'] not in {0, 1}


def test_manual_receipt_without_manual_labels_reserves_its_speaker_numbers():
    manual = _conversation('A', 0, [_segment('alice', 0)])
    manual['manual_speaker_assignments'] = {'speakers': {'0': {'person_id': 'p-alice'}, '3': {'person_id': 'p-carl'}}}
    automatic = _conversation('B', 3600, [_segment('stranger', 0)])

    merged = _by_text(_merge_transcript_segments([manual, automatic]))

    assert merged['alice']['speaker_id'] == 0
    assert merged['stranger']['speaker_id'] > 3


def test_two_automatic_sources_still_share_one_allocation_space():
    first = _conversation('A', 0, [_segment('one', 0)])
    second = _conversation('B', 3600, [_segment('two', 0)])

    merged = _by_text(_merge_transcript_segments([first, second]))

    assert {merged['one']['speaker_id'], merged['two']['speaker_id']} == {0, 1}
