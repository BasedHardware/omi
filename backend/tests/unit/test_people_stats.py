from datetime import datetime, timezone

from models.other import Person
from types import SimpleNamespace

from models.transcript_segment import TranscriptSegment
from utils.sync.speaker_identity import SpeakerIdentityDependencies, identify_speakers_for_segments
from utils.people_stats import aggregate_people_stats, apply_people_stats, collect_people_stats


def _conv(when, *segments, **extra):
    return {"started_at": when, "transcript_segments": list(segments), **extra}


def test_counts_conversations_once_per_person_and_sums_talk_time():
    t1 = datetime(2026, 9, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 5, tzinfo=timezone.utc)
    stats = aggregate_people_stats(
        [
            _conv(t2, {"person_id": "p1", "start": 0, "end": 10}, {"person_id": "p1", "start": 20, "end": 25}),
            _conv(t1, {"person_id": "p1", "start": 0, "end": 5}, {"person_id": "p2", "start": 5, "end": 6}),
        ]
    )
    assert stats["p1"] == {
        "conversation_count": 2,
        "last_heard_at": t2,
        "talk_seconds": 20.0,
        "auto_conversation_count": 0,
    }
    assert stats["p2"]["conversation_count"] == 1


def test_ignores_locked_and_malformed_rows():
    stats = aggregate_people_stats(
        [
            _conv(None, {"person_id": "p1", "start": 0, "end": 1}, is_locked=True),
            {"transcript_segments": "oops"},
            _conv(None, None, {"person_id": None}, {"person_id": "p3", "start": 4, "end": 2}),
        ]
    )
    assert set(stats) == {"p3"} and stats["p3"]["talk_seconds"] == 0.0


def test_collect_stops_at_cap_and_short_page():
    rows = [_conv(None, {"person_id": "p1", "start": 0, "end": 1}) for _ in range(30)]
    calls = []

    def fetch(limit, offset):
        calls.append((limit, offset))
        return rows[offset : offset + limit]

    assert collect_people_stats(fetch, scan_cap=25, batch=10)["p1"]["conversation_count"] == 25
    assert calls == [(10, 0), (10, 10), (5, 20)]
    assert collect_people_stats(fetch, scan_cap=100, batch=10)["p1"]["conversation_count"] == 30


def test_auto_conversation_count_needs_every_label_automatic():
    t = datetime(2026, 9, 5, tzinfo=timezone.utc)
    stats = aggregate_people_stats(
        [
            _conv(t, {"person_id": "p1", "start": 0, "end": 1, "speaker_match_source": "live_embedding"}),
            _conv(
                t,
                {"person_id": "p1", "start": 0, "end": 1, "speaker_match_source": "sync_embedding"},
                {"person_id": "p1", "start": 1, "end": 2},
            ),
        ]
    )
    assert stats["p1"]["conversation_count"] == 2
    assert stats["p1"]["auto_conversation_count"] == 1


def test_apply_people_stats_adds_reasons_without_moving_the_band():
    heard = Person(id="p1", name="Because", label_evidence={})
    unheard = Person(id="p2", name="Ines", label_evidence={"manual_labels": 1})
    band_before = unheard.confidence
    apply_people_stats(
        [heard, unheard],
        {"p1": {"conversation_count": 3, "last_heard_at": None, "talk_seconds": 4.0, "auto_conversation_count": 3}},
    )
    assert heard.conversation_count == 3 and heard.auto_conversation_count == 3
    assert {"auto_unconfirmed", "never_confirmed"} <= {r.code for r in heard.confidence_reasons}
    assert unheard.conversation_count == 0
    assert "not_heard" in {r.code for r in unheard.confidence_reasons}
    assert unheard.confidence == band_before


def test_sync_text_matches_are_automatic_without_changing_manual_labels():
    deps = SpeakerIdentityDependencies(
        users_db=SimpleNamespace(get_person_by_name=lambda uid, name: {'id': 'p1', 'name': name}),
        detect_speaker_from_text=lambda text, **kwargs: 'Maya' if text == 'I am Maya' else None,
    )
    for speaker_id in (0, 2):
        segments = [
            TranscriptSegment(id='intro', text='I am Maya', speaker_id=speaker_id, is_user=False, start=0, end=3),
            TranscriptSegment(id='later', text='hello', speaker_id=speaker_id, is_user=False, start=3, end=6),
            TranscriptSegment(
                id='manual', text='hello', speaker_id=speaker_id, is_user=False, person_id='p2', start=6, end=9
            ),
        ]
        identify_speakers_for_segments(segments, None, {}, 'u', dependencies=deps)
        assert segments[0].person_id == 'p1'
        assert segments[0].speaker_match_source == 'sync_text'
        assert segments[1].person_id == ('p1' if speaker_id > 0 else None)
        assert segments[1].speaker_match_source == ('sync_text' if speaker_id > 0 else None)
        assert segments[2].person_id == 'p2' and segments[2].speaker_match_source is None
        stats = aggregate_people_stats([_conv(None, *(segment.model_dump() for segment in segments))])
        assert stats['p1']['auto_conversation_count'] == 1
        assert stats['p2']['auto_conversation_count'] == 0
