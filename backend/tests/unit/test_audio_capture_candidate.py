"""The capture window is a retry position for verified readers, never proof and never the first cut."""

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.conversation import Conversation
from models.transcript_segment import TranscriptSegment
from tests.unit import test_speaker_learning_pool as pool
from tests.unit.fixtures.audio_chunk_storage import memory_bucket  # noqa: F401
from tests.unit.test_speaker_learning_pool import world  # noqa: F401
from utils.conversations.audio_placement import capture_shift, capture_window, locate, provisional_window
from utils.conversations.merge_conversations import _merge_transcript_segments
from utils.conversations.render import conversation_to_dict, redact_conversation_for_integration
from utils.speaker_tag_prompts import clips

ORIGIN = 1_700_000_000.0
T = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _conversation(*segments):
    return {'id': 'c', 'started_at': ORIGIN, 'transcript_segments': list(segments)}


def _segment(sid, start, end, cap_start=None, cap_end=None, **extra):
    segment = {'id': sid, 'start': start, 'end': end, 'speaker_id': 1, **extra}
    if cap_start is not None:
        segment.update(audio_capture_start=cap_start, audio_capture_end=cap_end)
    return segment


def test_capture_window_follows_the_receiver_clock_not_the_legacy_origin():
    # After a reconnect the provider-relative text is 1,800 s behind where the audio was captured.
    drift = 1800.0
    conversation = _conversation(_segment('a', 10.0, 18.0, ORIGIN + drift + 10.0, ORIGIN + drift + 18.0))
    assert capture_window(conversation, 12.0, 16.0) == (ORIGIN + drift + 12.0, ORIGIN + drift + 16.0)
    assert provisional_window(conversation, 12.0, 16.0) == (ORIGIN + 12.0, ORIGIN + 16.0)
    assert capture_shift(conversation, 12.0, 16.0) == drift


def test_no_capture_fields_means_no_window_and_no_shift():
    conversation = _conversation(_segment('a', 10.0, 18.0))
    assert capture_window(conversation, 10.0, 18.0) is None
    assert capture_shift(conversation, 10.0, 18.0) is None


def test_contributors_must_all_carry_a_window_and_agree_on_one_offset():
    known = _segment('a', 10.0, 14.0, ORIGIN + 110.0, ORIGIN + 114.0)
    missing = _segment('b', 14.0, 18.0)
    other_epoch = _segment('c', 14.0, 18.0, ORIGIN + 514.0, ORIGIN + 518.0)
    agreeing = _segment('d', 14.0, 18.0, ORIGIN + 114.2, ORIGIN + 118.2)
    assert capture_window(_conversation(known, missing), 10.0, 18.0) is None
    assert capture_window(_conversation(known, other_epoch), 10.0, 18.0) is None
    window = capture_window(_conversation(known, agreeing), 10.0, 18.0)
    assert window is not None and abs(window[0] - (ORIGIN + 110.0)) <= 0.25 and abs(window[1] - window[0] - 8.0) < 1e-6


def test_a_capture_window_of_the_wrong_length_or_an_unplaced_contributor_is_refused():
    stretched = _segment('a', 10.0, 14.0, ORIGIN + 110.0, ORIGIN + 130.0)
    unplaced = _segment('b', 10.0, 14.0, ORIGIN + 110.0, ORIGIN + 114.0, audio_alignment='unplaced')
    assert capture_window(_conversation(stretched), 10.0, 14.0) is None
    assert capture_window(_conversation(unplaced), 10.0, 14.0) is None


def test_explicit_contributors_override_overlap_lookup():
    inside = _segment('a', 10.0, 14.0, ORIGIN + 110.0, ORIGIN + 114.0)
    bystander = _segment('b', 11.0, 13.0)
    conversation = _conversation(inside, bystander)
    assert capture_window(conversation, 10.0, 14.0) is None
    assert capture_window(conversation, 10.0, 14.0, segments=[inside]) == (ORIGIN + 110.0, ORIGIN + 114.0)


def test_capture_fields_never_make_a_window_trusted():
    segment = _segment('a', 10.0, 18.0, ORIGIN + 110.0, ORIGIN + 118.0)
    placement = locate(_conversation(segment), 10.0, 18.0)
    assert placement.window is None and placement.reason == 'untrusted_clock'


def test_teaching_that_works_at_the_legacy_position_is_not_changed_by_capture_fields(world, memory_bucket, monkeypatch):
    # Ordinary arrival jitter: the capture clock sits 0.5 s before the stored chunk clock. The
    # legacy cut verifies, so the capture window must not be consulted at all.
    from utils.audio_timeline import CaptureTimeline
    from utils.other import storage

    clock = CaptureTimeline(16000)
    frame = b'\x00\x00' * 8000
    arrival = ORIGIN
    for i in range(20):
        arrival = ORIGIN + (i + 1) * 0.5 + (0.5 if i else 0.0)
        clock.accept(frame, arrival, arrival - ORIGIN)
    first_audio = ORIGIN + 0.5
    chunk_start = arrival - 10.0
    memory_bucket.add(chunk_start, 10.0, uid=pool.UID, conversation_id=pool.CONV)
    monkeypatch.setattr(storage, 'list_audio_chunks', world.real_listing)
    monkeypatch.setattr(storage, 'download_audio_chunks_and_merge', world.real_merge)
    monkeypatch.delenv('SPEAKER_TEACHING_TEXT_PLACEMENT', raising=False)
    seg = pool.seg('a', 0.0, 10.0, scope='live:scope-a', text='alpha bravo charlie delta echo foxtrot golf')
    conv = pool.conversation(
        [seg], id=pool.CONV, started_at=first_audio, audio_files=[dict(chunk_timestamps=[chunk_start], duration=10.0)]
    )
    pool.set_conversation(world, conv)
    assert pool.teach(('a',)) == 'stored'
    seg.update(audio_capture_start=clock.wall(0), audio_capture_end=clock.wall(160000))
    pool.set_conversation(world, conv)
    assert capture_window(conv, 0.0, 10.0) == (ORIGIN, ORIGIN + 10.0)
    assert pool.teach(('a',)) == 'stored'
    assert world.captured['wav_seconds'] == 10.0


def test_teaching_retries_at_the_capture_window_when_the_legacy_position_has_no_audio(
    world, memory_bucket, monkeypatch
):
    # A reconnect put the audio 100 s after where the provider-relative text says it is.
    from utils.other import storage

    memory_bucket.add(ORIGIN + 100.0, 10.0, uid=pool.UID, conversation_id=pool.CONV)
    monkeypatch.setattr(storage, 'list_audio_chunks', world.real_listing)
    monkeypatch.setattr(storage, 'download_audio_chunks_and_merge', world.real_merge)
    monkeypatch.delenv('SPEAKER_TEACHING_TEXT_PLACEMENT', raising=False)
    seg = pool.seg('a', 0.0, 10.0, scope='live:scope-a', text='alpha bravo charlie delta echo foxtrot golf')
    conv = pool.conversation(
        [seg], id=pool.CONV, started_at=ORIGIN, audio_files=[dict(chunk_timestamps=[ORIGIN + 100.0], duration=10.0)]
    )
    pool.set_conversation(world, conv)
    assert pool.teach(('a',)) != 'stored'
    seg.update(audio_capture_start=ORIGIN + 100.0, audio_capture_end=ORIGIN + 110.0)
    pool.set_conversation(world, conv)
    assert pool.teach(('a',)) == 'stored'
    assert world.captured['wav_seconds'] == 10.0


def test_clip_reader_cuts_at_the_legacy_origin_unless_asked_for_the_capture_window(memory_bucket):
    uid, cid = 'synthetic-user', 'synthetic'
    source = memory_bucket.add(ORIGIN + 100.0, 20.0, uid=uid, conversation_id=cid)
    conv = dict(
        id=cid,
        started_at=ORIGIN,
        audio_files=[dict(chunk_timestamps=[ORIGIN + 100.0], duration=20.0)],
        transcript_segments=[
            dict(
                id='s',
                speaker_id=1,
                start=0.0,
                end=10.0,
                text='alpha bravo charlie delta echo',
                audio_capture_start=ORIGIN + 100.0,
                audio_capture_end=ORIGIN + 110.0,
            )
        ],
    )
    assert clips.conversation_clip_pcm(uid, conv, 0.0, 10.0) is None
    assert clips.conversation_clip_pcm(uid, conv, 0.0, 10.0, prefer_capture=True) == source[: 16000 * 10 * 2]


def _row():
    return dict(
        id='synthetic-c',
        created_at=T,
        started_at=T,
        finished_at=T,
        structured={},
        transcript_segments=[
            dict(
                id='synthetic-s',
                text='Synthetic words.',
                speaker_id=1,
                start=0.0,
                end=10.0,
                is_user=False,
                audio_capture_start=1767225600.0,
                audio_capture_end=1767225610.0,
            )
        ],
    )


def test_capture_fields_are_stored_but_never_served():
    segment = TranscriptSegment(**_row()['transcript_segments'][0])
    # Storage (python-mode dumps) keeps them.
    assert segment.model_dump()['audio_capture_start'] == 1767225600.0
    assert Conversation(**_row()).model_dump()['transcript_segments'][0]['audio_capture_end'] == 1767225610.0
    # API responses (JSON mode) never carry them.
    assert 'audio_capture_start' not in segment.model_dump(mode='json')
    app = FastAPI()

    @app.get('/synthetic', response_model=Conversation)
    def read():
        return _row()

    served = TestClient(app).get('/synthetic').json()['transcript_segments'][0]
    assert 'audio_capture_start' not in served and 'audio_capture_end' not in served
    # Third-party app webhooks never carry them.
    payload = redact_conversation_for_integration(conversation_to_dict(Conversation(**_row())))
    sent = payload['transcript_segments'][0]
    assert 'audio_capture_start' not in sent and 'audio_capture_end' not in sent


def test_manual_merge_of_overlapping_sources_stays_chronological():
    def seg(sid, start, end):
        return dict(id=sid, start=start, end=end, text=sid, speaker_id=1, is_user=False)

    first = dict(
        id='a',
        started_at=T,
        finished_at=T + timedelta(seconds=90),
        transcript_segments=[seg('early', 0.0, 1.0), seg('late', 80.0, 81.0)],
    )
    donor = dict(
        id='b',
        started_at=T + timedelta(seconds=5),
        finished_at=T + timedelta(seconds=10),
        transcript_segments=[seg('middle', 0.0, 5.0)],
    )
    merged = _merge_transcript_segments([first, donor])
    assert [s['id'] for s in merged] == ['early', 'middle', 'late']
    assert [s['start'] for s in merged] == [0.0, 5.0, 80.0]
    assert TranscriptSegment.can_display_seconds([TranscriptSegment(**s) for s in merged])
