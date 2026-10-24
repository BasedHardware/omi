from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from utils.conversations import screen_frame_evidence as evidence_mod
from utils.conversations.screen_frame_evidence import (
    ScreenFrameEvidence,
    load_screen_frame_evidence,
    screen_moment_lines,
    with_screen_frame_participants,
)

PROD = 'omi-screen-frames'
START = datetime(2026, 9, 30, 17, 0, tzinfo=timezone.utc)


class TestTimestampAndSuitabilityCoercion:
    @pytest.fixture(autouse=True)
    def _setting_on(self, monkeypatch):
        monkeypatch.setattr(evidence_mod, 'get_meeting_note_screenshots_enabled', lambda uid: True)
        monkeypatch.setenv('BUCKET_SCREEN_FRAMES', PROD)

    def test_load_screen_frame_evidence_coerces_iso_naive_and_epoch_timestamps(self, monkeypatch):
        docs = [
            {
                'id': 'f_aware',
                'captured_at': datetime(2026, 9, 30, 17, 4, tzinfo=timezone.utc),
                'storage_bucket': PROD,
                'screen_summary': 'Fourth',
            },
            {
                'id': 'f_iso',
                'captured_at': '2026-09-30T17:02:00Z',
                'storage_bucket': PROD,
                'screen_summary': 'Second',
            },
            {
                'id': 'f_naive',
                'captured_at': datetime(2026, 9, 30, 17, 1, 0),
                'storage_bucket': PROD,
                'screen_summary': 'First',
            },
            {
                'id': 'f_epoch',
                'captured_at': datetime(2026, 9, 30, 17, 3, tzinfo=timezone.utc).timestamp(),
                'storage_bucket': PROD,
                'screen_summary': 'Third',
            },
            {
                'id': 'f_bool',
                'captured_at': True,
                'storage_bucket': PROD,
                'screen_summary': 'Ignored bool',
            },
            {
                'id': 'f_corrupt',
                'captured_at': 'not-a-timestamp',
                'storage_bucket': PROD,
                'screen_summary': 'Ignored corrupt',
            },
        ]
        monkeypatch.setattr(evidence_mod, 'get_conversation_screen_frames', lambda *_: docs)

        loaded = load_screen_frame_evidence('u', 'c')

        assert [item.frame_id for item in loaded] == ['f_naive', 'f_iso', 'f_epoch', 'f_aware']
        assert all(item.captured_at.tzinfo == timezone.utc for item in loaded)

    def test_load_screen_frame_evidence_tolerates_malformed_banner_suitability(self, monkeypatch):
        docs = [
            {
                'id': 'f_str_suitability',
                'captured_at': START,
                'storage_bucket': PROD,
                'banner_suitability': 'not-a-float',
                'screen_summary': 'Slide',
            },
            {
                'id': 'f_nan_suitability',
                'captured_at': START + timedelta(minutes=1),
                'storage_bucket': PROD,
                'banner_suitability': float('nan'),
                'screen_summary': 'Slide 2',
            },
            {
                'id': 'f_bool_suitability',
                'captured_at': START + timedelta(minutes=2),
                'storage_bucket': PROD,
                'banner_suitability': True,
                'screen_summary': 'Slide 3',
            },
        ]
        monkeypatch.setattr(evidence_mod, 'get_conversation_screen_frames', lambda *_: docs)

        loaded = load_screen_frame_evidence('u', 'c')

        assert [item.frame_id for item in loaded] == [
            'f_str_suitability',
            'f_nan_suitability',
            'f_bool_suitability',
        ]
        assert [item.banner_suitability for item in loaded] == [0.0, 0.0, 0.0]

    def test_screen_moment_lines_handles_naive_and_iso_captured_at_against_aware_started_at(self):
        evidence = [
            ScreenFrameEvidence(
                frame_id='a',
                captured_at=datetime(2026, 9, 30, 17, 2, 0),
                role='strip',
                banner_suitability=0.5,
                names=('Jordan Rivera',),
                summary='Naive capture time',
            ),
            ScreenFrameEvidence(
                frame_id='b',
                captured_at='2026-09-30T17:05:30Z',  # type: ignore[arg-type]
                role='strip',
                banner_suitability=0.5,
                names=(),
                summary='ISO capture time',
            ),
        ]

        lines = screen_moment_lines(evidence, '2026-09-30T17:00:00Z')  # type: ignore[arg-type]

        assert lines == (
            '- [+02:00] Naive capture time (on screen: Jordan Rivera)',
            '- [+05:30] ISO capture time',
        )

    def test_screen_moment_lines_without_started_at_formats_naive_iso_and_corrupt_captured_at(self):
        evidence = [
            ScreenFrameEvidence(
                frame_id='a',
                captured_at=datetime(2026, 9, 30, 17, 15, 0),
                role='strip',
                banner_suitability=0.5,
                names=(),
                summary='Clock fallback',
            ),
            ScreenFrameEvidence(
                frame_id='b',
                captured_at='2026-09-30T17:45:00Z',  # type: ignore[arg-type]
                role='strip',
                banner_suitability=0.5,
                names=(),
                summary='ISO clock fallback',
            ),
            ScreenFrameEvidence(
                frame_id='c',
                captured_at='corrupt',  # type: ignore[arg-type]
                role='strip',
                banner_suitability=0.5,
                names=(),
                summary='Corrupt fallback',
            ),
        ]

        lines = screen_moment_lines(evidence, None)

        assert lines == (
            '- [17:15] Clock fallback',
            '- [17:45] ISO clock fallback',
            '- [+00:00] Corrupt fallback',
        )

    def test_select_for_images_sorts_mixed_naive_aware_and_iso_captured_at(self):
        evidence = [
            ScreenFrameEvidence('f0', datetime(2026, 9, 30, 17, 0), 'strip', 0.1, (), ''),
            ScreenFrameEvidence('f1', '2026-09-30T17:01:00Z', 'strip', 0.1, (), ''),  # type: ignore[arg-type]
            ScreenFrameEvidence('f2', START + timedelta(minutes=2), 'strip', 0.1, (), ''),
            ScreenFrameEvidence('f3', datetime(2026, 9, 30, 17, 3), 'strip', 0.1, (), ''),
            ScreenFrameEvidence('f4', START + timedelta(minutes=4), 'strip', 0.1, (), ''),
            ScreenFrameEvidence('banner', datetime(2026, 9, 30, 17, 1, 30), 'banner', 0.9, (), ''),
        ]

        selected = evidence_mod._select_for_images(evidence)

        assert len(selected) == 4
        assert 'banner' in [item.frame_id for item in selected]
        assert [item.frame_id for item in selected] == ['f0', 'f1', 'banner', 'f3']

    def test_with_screen_frame_participants_coerces_iso_and_naive_started_at(self):
        ctx_iso = with_screen_frame_participants(
            None,
            ['Jordan Rivera'],
            started_at='2026-09-30T17:00:00Z',  # type: ignore[arg-type]
            duration_minutes=30,
        )
        assert ctx_iso is not None
        assert ctx_iso.start_time == START

        ctx_naive = with_screen_frame_participants(
            None,
            ['Jordan Rivera'],
            started_at=datetime(2026, 9, 30, 17, 0),
            duration_minutes=30,
        )
        assert ctx_naive is not None
        assert ctx_naive.start_time == START

        ctx_invalid = with_screen_frame_participants(
            None,
            ['Jordan Rivera'],
            started_at='invalid-date',  # type: ignore[arg-type]
            duration_minutes=30,
        )
        assert ctx_invalid is None

    def test_frame_evidence_started_at_and_duration_accept_iso_and_epoch_conversation_fields(self):
        conv = SimpleNamespace(
            started_at='2026-09-30T17:00:00Z',
            finished_at=(START + timedelta(minutes=25)).timestamp(),
        )
        assert evidence_mod.frame_evidence_started_at(conv) == START
        assert evidence_mod.frame_evidence_duration_minutes(conv) == 25

    def test_as_utc_rejects_booleans_and_blank_strings(self):
        assert evidence_mod._as_utc(True) is None
        assert evidence_mod._as_utc(False) is None
        assert evidence_mod._as_utc('') is None
        assert evidence_mod._as_utc('   ') is None
        assert evidence_mod._as_utc('not-a-timestamp') is None
