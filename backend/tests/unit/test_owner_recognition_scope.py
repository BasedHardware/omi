"""Source-scoped fragment labels must reach the serialized transcript."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from models.transcript_segment import TranscriptSegment
from models.conversation import Conversation
from models.structured import Structured
from utils.conversations.merge_conversations import _merge_transcript_segments
from utils.conversations.speaker_resolution import apply_speaker_resolution
from utils.stt.conversation_speakers import resolve_conversation_speakers


def test_same_integer_id_in_two_scopes_cannot_label_other_short_reply():
    segments = [
        {
            'id': 'owner',
            'speaker_id': 0,
            'speaker_id_scope': 'pendant:0',
            'start': 0.0,
            'end': 10.0,
            'is_user': False,
            'text': 'Owner',
        },
        {
            'id': 'other',
            'speaker_id': 0,
            'speaker_id_scope': 'desktop:0',
            'start': 11.0,
            'end': 17.0,
            'is_user': False,
            'text': 'Other',
        },
        {
            'id': 'short',
            'speaker_id': 0,
            'speaker_id_scope': 'desktop:0',
            'start': 18.0,
            'end': 18.5,
            'is_user': False,
            'text': 'Okay',
        },
    ]
    resolution = resolve_conversation_speakers(
        segments, {'owner': np.array([1.0, 0.0]), 'other': np.array([0.0, 1.0])}, voiceprints={'user': [1.0, 0.0]}
    )
    conversation = Conversation(
        id='merged',
        started_at=None,
        finished_at=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        structured=Structured(),
        transcript_segments=[TranscriptSegment(**s) for s in segments],
    )
    apply_speaker_resolution(
        conversation,
        resolution.speaker_ids,
        resolution.voice_identities,
        resolution.voice_identity_statuses,
        owner_voiceprint_available=resolution.owner_voiceprint_available,
    )
    assert [s['is_user'] for s in conversation.model_dump()['transcript_segments']] == [True, False, False]
    assert resolution.speaker_ids['short'] == resolution.speaker_ids['other']
    assert resolution.speaker_ids['short'] != resolution.speaker_ids['owner']


@pytest.mark.parametrize('speaker_id', [0, '0'])
def test_manual_merge_reallocates_automatic_donor_voice_ids_and_preserves_capture_clock(speaker_id):
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def row(cid, offset, owner):
        return {
            'id': cid,
            'started_at': at + timedelta(seconds=offset),
            'finished_at': at + timedelta(seconds=offset + 6),
            'transcript_segments': [
                {
                    'id': cid,
                    'text': cid,
                    'speaker': 'SPEAKER_0',
                    'speaker_id': speaker_id,
                    'is_user': owner,
                    'start': 0.0,
                    'end': 6.0,
                    'audio_capture_start': at.timestamp() + offset,
                    'audio_capture_end': at.timestamp() + offset + 6,
                }
            ],
        }

    merged = _merge_transcript_segments([row('first', 0, True), row('second', 10, False)])
    payload = [TranscriptSegment(**s).model_dump() for s in merged]
    assert payload[0]['speaker_id'] != payload[1]['speaker_id']
    assert payload[0]['speaker_id_scope'] != payload[1]['speaker_id_scope']
    assert payload[1]['audio_capture_start'] == at.timestamp() + 10
    assert payload[1]['start'] == 10


def test_short_reply_from_acoustically_contradicted_voice_withdraws_auto_owner():
    segments = [
        {
            'id': 'owner',
            'speaker_id': 0,
            'speaker_id_scope': 'conn:0',
            'start': 0.0,
            'end': 10.0,
            'is_user': False,
            'text': 'Owner',
        },
        {
            'id': 'other',
            'speaker_id': 0,
            'speaker_id_scope': 'conn:0',
            'start': 11.0,
            'end': 17.0,
            'is_user': False,
            'text': 'Other',
        },
        {
            'id': 'short',
            'speaker_id': 0,
            'speaker_id_scope': 'conn:0',
            'start': 18.0,
            'end': 18.5,
            'is_user': True,
            'speaker_label_source': 'auto',
            'text': 'Okay',
        },
    ]
    resolution = resolve_conversation_speakers(
        segments, {'owner': np.array([1.0, 0.0]), 'other': np.array([0.0, 1.0])}, voiceprints={'user': [1.0, 0.0]}
    )
    conversation = Conversation(
        id='merged',
        started_at=None,
        finished_at=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        structured=Structured(),
        transcript_segments=[TranscriptSegment(**s) for s in segments],
    )
    apply_speaker_resolution(
        conversation,
        resolution.speaker_ids,
        resolution.voice_identities,
        resolution.voice_identity_statuses,
        owner_voiceprint_available=resolution.owner_voiceprint_available,
        contradicted_segment_ids=resolution.contradicted_segment_ids,
    )
    assert conversation.model_dump()['transcript_segments'][-1]['is_user'] is False


def _merge_rows(rows):
    return _merge_transcript_segments(rows)


def _conv(cid, offset, segments, **extra):
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return {
        'id': cid,
        'started_at': at + timedelta(seconds=offset),
        'finished_at': at + timedelta(seconds=offset + 6),
        'transcript_segments': segments,
        **extra,
    }


def _voice(cid, sid, **extra):
    return {
        'id': cid,
        'text': cid,
        'speaker': f'SPEAKER_{sid:02d}',
        'speaker_id': sid,
        'speaker_id_scope': f'conn:{cid}',
        'is_user': False,
        'start': 0.0,
        'end': 6.0,
        **extra,
    }


def test_tagged_source_keeps_ids_and_automatic_donor_is_renumbered():
    # Regression: a manual label on one source must not disable renumbering for
    # every automatic source, which let provider-local ids collide.
    tagged = _conv('A', 0, [_voice('alice', 0, speaker_label_source='manual', person_id='p-alice')])
    auto = _conv('B', 3600, [_voice('stranger', 0)])
    merged = _merge_rows([tagged, auto])
    by_text = {s['text']: s['speaker_id'] for s in merged}
    assert by_text['alice'] == 0
    assert by_text['stranger'] == 1
    assert merged[0].get('person_id') == 'p-alice'


def test_tagged_source_second_also_reserves_its_ids():
    auto = _conv('A', 0, [_voice('stranger', 0)])
    tagged = _conv('B', 3600, [_voice('alice', 0, speaker_label_source='manual', person_id='p-alice')])
    merged = _merge_rows([auto, tagged])
    by_text = {s['text']: s['speaker_id'] for s in merged}
    assert by_text['alice'] == 0
    assert by_text['stranger'] != 0


def test_receipt_only_source_reserves_its_ids():
    receipt_only = _conv(
        'A', 0, [_voice('alice', 0)],
        manual_speaker_assignments={'speakers': {'0': {'person_id': 'p-alice'}}},
    )
    auto = _conv('B', 3600, [_voice('stranger', 0)])
    merged = _merge_rows([receipt_only, auto])
    by_text = {s['text']: s['speaker_id'] for s in merged}
    assert by_text['alice'] == 0
    assert by_text['stranger'] == 1


def test_all_automatic_sources_still_renumber():
    a = _conv('A', 0, [_voice('x', 0)])
    b = _conv('B', 3600, [_voice('y', 0)])
    merged = _merge_rows([a, b])
    by_text = {s['text']: s['speaker_id'] for s in merged}
    assert by_text['x'] == 0 and by_text['y'] == 1


def test_tagged_source_at_sentinel_neighbour_skips_the_sentinel():
    """A reserved id next to OMI_SPEAKER_ID_SENTINEL must not absorb it.

    The tagged source owns 98, so the allocator's floor lands at 99 — the
    sentinel reserved for the Omi device voice. Re-numbering must jump straight
    to 100: handing the device sentinel to a merged provider voice makes that
    speaker resolve as the device everywhere the sentinel is checked.
    """
    tagged = _conv('A', 0, [_voice('alice', 98, speaker_label_source='manual', person_id='p-alice')])
    auto = _conv('B', 3600, [_voice('stranger', 0)])
    merged = _merge_rows([tagged, auto])
    by_text = {s['text']: s['speaker_id'] for s in merged}
    assert by_text['alice'] == 98
    assert by_text['stranger'] == 100
    assert 99 not in by_text.values()


def test_carried_label_source_keeps_ids_while_donor_is_renumbered():
    """``carried`` is the receipt-migration spelling of manual authority.

    A carried label keeps its own numbers (here 0, bound to the person_id the
    receipt will migrate onto), while the automatic donor must be renumbered
    past it. Pre-fix the carried label disabled renumbering globally, so the
    donor kept provider-local 0 and collided with the carried voice.
    """
    carried = _conv('A', 0, [_voice('alice', 0, speaker_label_source='carried', person_id='p-alice')])
    auto = _conv('B', 3600, [_voice('stranger', 0)])
    merged = _merge_rows([carried, auto])
    by_text = {s['text']: s['speaker_id'] for s in merged}
    assert by_text['alice'] == 0
    assert by_text['stranger'] == 1
    assert merged[0].get('person_id') == 'p-alice'


def test_receipt_only_source_at_sentinel_rekey_excludes_the_sentinel():
    """The receipt scan must reserve real ids but never treat 99 as owned.

    hydrate_receipt() advances the floor per key; a receipt entry for the
    device sentinel (99) must not count as an owned voice, otherwise the first
    renumbered donor would start at 100 for no reason (or, worse, a receipt
    that only maps the sentinel would reserve nothing real but block id 99 in a
    way no source owns). Real ids in the same receipt still reserve.
    """
    receipt_only = _conv(
        'A', 0, [_voice('alice', 0)],
        manual_speaker_assignments={'speakers': {'0': {'person_id': 'p-alice'}, '99': {'person_id': 'omi'}}},
    )
    auto = _conv('B', 3600, [_voice('stranger', 0)])
    merged = _merge_rows([receipt_only, auto])
    by_text = {s['text']: s['speaker_id'] for s in merged}
    assert by_text['alice'] == 0
    # hydrate_receipt() skips the '99' key, so the floor comes only from the
    # owned id 0: the donor renumbered to 1. Had 99 been reserved as a real
    # voice, the donor would start at 100; had 0 gone unreserved, the donor
    # would collide with alice at 0.
    assert by_text['stranger'] == 1
    assert 99 not in by_text.values()
