"""Regressions for cut attribution and published audio ownership across reconciles."""

from datetime import datetime, timedelta, timezone
import unittest

from utils.conversations.v3 import outline, planner


class FragmentationRepro(unittest.TestCase):
    def test_manual_cut_does_not_finish_continuous_speech_after_it(self):
        origin = datetime(2026, 11, 19, tzinfo=timezone.utc)
        cut = origin + timedelta(seconds=20)
        now = origin + timedelta(seconds=40)
        entry = {'first_line': 1, 'kind': 'conversation', 'title': '', 'line': ''}

        def segment(start, end):
            return {'id': str(start), 'start': start, 'end': end, 'text': f'synthetic speech {start}'}

        existing = {}
        readings = []
        continuation_ids = set()
        claims = {}
        for tail in ([], [segment(23, 24)], [segment(23, 24), segment(25, 26)]):
            members = [
                {
                    'id': 'ended',
                    'started_at': origin,
                    'finished_at': cut,
                    'v3_manual_end': True,
                    'transcript_segments': [segment(18, 22)],
                },
                {'id': 'live', 'started_at': origin, 'transcript_segments': tail},
            ]
            recordings = {member['id']: member for member in members}
            for rid, recording in recordings.items():
                recording['claims'] = claims.get(rid, [])
            groups = outline.stretches(members, now)
            windows = planner.preserve_finished_windows(
                planner.windows(groups, [[entry] for group in groups]), existing, recordings
            )
            rows = [
                planner.build('synthetic', window, recordings, existing.get(window.get('existing_id')))
                for window in windows
            ]
            for row in rows:
                existing[row['id']] = row
            claims = {
                rid: [
                    {'conversation_id': row['id'], **claim} for row in rows for claim in row['_v3_claims'].get(rid, [])
                ]
                for rid in recordings
            }
            readings.append([(row['status'], row['manual_end']) for row in rows])
            continuation_ids.update(row['id'] for row in rows if row['status'] == 'in_progress')

        self.assertEqual(
            readings,
            [
                [('processing', True)],
                [('processing', True), ('in_progress', False)],
                [('processing', True), ('in_progress', False)],
            ],
        )
        assert len(continuation_ids) == 1

    def test_resegmented_speech_does_not_create_overlapping_audio_claim(self):
        origin = datetime(2026, 11, 19, tzinfo=timezone.utc)
        entry = {'first_line': 1, 'kind': 'conversation', 'title': '', 'line': ''}
        recording = {
            'id': 'recording',
            'started_at': origin,
            'audio_files': [{'id': 'file', 'duration': 30}],
            'transcript_segments': [{'id': 'speech', 'start': 0, 'end': 10, 'text': 'synthetic speech'}],
        }

        def plan(existing):
            groups = outline.stretches([recording], origin + timedelta(minutes=10))
            return planner.preserve_finished_windows(
                planner.windows(groups, [[entry]]), existing, {'recording': recording}
            )

        original = planner.build('synthetic', plan({})[0], {'recording': recording})
        recording['claims'] = [
            {'conversation_id': original['id'], **span} for span in original['_v3_claims']['recording']
        ]
        recording['transcript_segments'] = [{'id': 'speech', 'start': 8, 'end': 12, 'text': 'synthetic speech'}]
        fresh = [
            planner.build('synthetic', window, {'recording': recording})
            for window in plan({original['id']: original})
            if not window.get('existing_id')
        ]
        assert len(fresh) == 1
        tail = fresh[0]
        assert [(piece['start'], piece['end']) for piece in tail['recording_pieces']] == [(10, 12)]
        assert tail['_v3_claims']['recording'] == [
            {'start': origin + timedelta(seconds=10), 'end': origin + timedelta(seconds=12)}
        ]
        assert len(tail['transcript_segments']) == 1
        assert [(piece['start'], piece['end']) for piece in original['recording_pieces']] == [(0, 10)]

        recording['claims'].extend({'conversation_id': tail['id'], **span} for span in tail['_v3_claims']['recording'])
        replay = plan({original['id']: original, tail['id']: tail})
        assert [window.get('existing_id') for window in replay] == [tail['id']]

    def test_manual_cut_finishes_one_window_even_when_outlined_in_chapters(self):
        origin = datetime(2026, 11, 19, tzinfo=timezone.utc)
        cut = origin + timedelta(minutes=30)
        recording = {
            'id': 'recording',
            'started_at': origin,
            'finished_at': cut,
            'v3_manual_end': True,
            'transcript_segments': [
                {'id': str(second), 'start': second, 'end': second + 15, 'text': 'synthetic speech'}
                for second in range(0, 30 * 60, 15)
            ],
        }
        groups = outline.stretches([recording], cut)
        windows = planner.windows(
            groups,
            [
                [
                    {'first_line': 1, 'title': 'First', 'kind': 'media', 'line': '', 'people': ['A']},
                    {'first_line': 60, 'title': 'Second', 'kind': 'conversation', 'line': '', 'people': ['B']},
                ]
            ],
        )
        assert len(windows) == 1
        assert windows[0]['manual_end']
        assert len(windows[0]['lines']) == 120
        assert any(section['first_line'] == 60 for section in windows[0]['sections'])
        assert windows[0]['people'] == ['A', 'B']
        row = planner.build('synthetic', windows[0], {'recording': recording})
        assert row['outline_kind'] == 'conversation' and not row['home_hidden']

    def test_silence_ends_the_manual_continuation_context(self):
        origin = datetime(2026, 11, 19, tzinfo=timezone.utc)
        recording = {
            'id': 'recording',
            'started_at': origin,
            'finished_at': origin + timedelta(seconds=10),
            'v3_manual_end': True,
            'transcript_segments': [
                {'id': 'before', 'start': 0, 'end': 10, 'text': 'before'},
                {'id': 'after', 'start': 310, 'end': 320, 'text': 'after'},
                {'id': 'new', 'start': 325, 'end': 330, 'text': 'new'},
            ],
        }
        groups = outline.stretches([recording], origin + timedelta(minutes=20))
        assert len(groups) == 2
        assert groups[0]['manual_end']
        assert not groups[1]['after_manual_end']
        entry = {'first_line': 1, 'kind': 'conversation', 'title': '', 'line': ''}
        windows = planner.windows(groups, [[entry], [entry, {**entry, 'first_line': 2}]])
        assert [window['manual_end'] for window in windows] == [True, False, False]
