"""Regressions for cut attribution and published audio ownership across reconciles."""

from datetime import datetime, timedelta, timezone
import unittest

from utils.conversations.v3 import outline, planner, service


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

    def test_published_speech_inside_an_open_stretch_leaves_one_open_window(self):
        # Production shape (2026-11-19): a finished, published row sits inside a stretch that is still
        # open (late-synced or overlapping capture around it, or a backlog page held open). Preservation
        # cut the open window into a fresh fragment per gap and every fragment stayed in progress, so
        # the commit refused with multiple_open_conversations on every pass.
        origin = datetime(2026, 11, 19, tzinfo=timezone.utc)
        entry = {'first_line': 1, 'kind': 'conversation', 'title': '', 'line': ''}

        def segment(start, end):
            return {'id': str(start), 'start': start, 'end': end, 'text': f'synthetic speech {start}'}

        def plan(recordings, existing, now):
            groups = outline.stretches(list(recordings.values()), origin + timedelta(seconds=now))
            windows = planner.preserve_finished_windows(planner.windows(groups, [[entry]]), existing, recordings)
            return groups, windows

        def claim(recording, row):
            recording['claims'].extend(
                {'conversation_id': row['id'], **span} for span in row['_v3_claims'][recording['id']]
            )

        live = {
            'id': 'live',
            'started_at': origin,
            'claims': [],
            'audio_files': [{'id': 'live-file', 'duration': 400}],
            'transcript_segments': [segment(60, 70), segment(90, 100)],
        }
        _, windows = plan({'live': live}, {}, 400)
        published = planner.build('synthetic', windows[0], {'live': live}, None)
        assert published['status'] == 'processing'
        published['status'] = 'completed'
        claim(live, published)
        held = list(published['_v3_claims']['live'])

        # The live recording keeps going: one open row after the published one.
        live['transcript_segments'].append(segment(370, 380))
        existing = {published['id']: published}
        _, windows = plan({'live': live}, existing, 385)
        assert [(w.get('existing_id'), w['finished']) for w in windows] == [(published['id'], True), (None, False)]
        open_row = planner.build('synthetic', windows[1], {'live': live}, None)
        assert open_row['status'] == 'in_progress'
        claim(live, open_row)
        existing[open_row['id']] = open_row

        # Speech of a second capture arrives late, around and inside the published row.
        synced = {
            'id': 'synced',
            'started_at': origin,
            'claims': [],
            'transcript_segments': [segment(0, 10), segment(75, 85), segment(200, 210)],
        }
        recordings = {'live': live, 'synced': synced}
        groups, windows = plan(recordings, existing, 390)
        assert [group['finished'] for group in groups] == [False]
        assert [(w.get('existing_id'), w['finished']) for w in windows] == [
            (None, True),
            (published['id'], True),
            (None, True),
            (None, False),
        ]
        # No speech is lost or moved, and the open edge holds the stretch's latest line.
        assert sorted(line['start'] for w in windows for line in w['lines']) == sorted(
            line['start'] for line in groups[0]['lines']
        )
        assert windows[-1]['lines'][-1] is groups[0]['lines'][-1]

        rows, used = [], {published['id']}
        for window in windows:
            prior = existing.get(window.get('existing_id')) or service._match(window, existing, used)
            if prior:
                used.add(prior['id'])
            rows.append(planner.build('synthetic', window, recordings, prior))
        # commit_projection refuses more than one in-progress row; the stored open row keeps its id.
        assert [row['status'] == 'in_progress' for row in rows] == [False, False, False, True]
        assert rows[-1]['id'] == open_row['id']
        assert len({row['id'] for row in rows}) == 4
        # The retained row keeps its claims and audio; the open edge claims only unpublished audio.
        assert rows[1]['_v3_claims']['live'] == held
        assert rows[1]['recording_pieces'] == published['recording_pieces']
        assert rows[-1]['_v3_claims']['live'] == [
            {'start': origin + timedelta(seconds=370), 'end': origin + timedelta(seconds=380)}
        ]
        assert [(piece['start'], piece['end']) for piece in rows[-1]['recording_pieces']] == [(370, 380)]

    def test_fresh_prefix_finishes_when_published_speech_ends_the_open_stretch(self):
        origin = datetime(2026, 11, 19, tzinfo=timezone.utc)
        published_recording = {
            'id': 'published',
            'started_at': origin,
            'transcript_segments': [{'id': 'tail', 'start': 60, 'end': 70, 'text': 'published speech'}],
        }
        late_recording = {
            'id': 'late',
            'started_at': origin,
            'transcript_segments': [{'id': 'prefix', 'start': 40, 'end': 50, 'text': 'late speech'}],
        }
        entry = {'first_line': 1, 'kind': 'conversation', 'title': '', 'line': ''}
        published_groups = outline.stretches([published_recording], origin + timedelta(minutes=10))
        published_window = planner.windows(published_groups, [[entry]])[0]
        published = planner.build('synthetic', published_window, {'published': published_recording})
        published['status'] = 'completed'

        published_recording['_v3_page_continues'] = True
        recordings = {'published': published_recording, 'late': late_recording}
        groups = outline.stretches(list(recordings.values()), origin + timedelta(minutes=10))
        planned = planner.windows(groups, [[entry]])
        assert [window['finished'] for window in planned] == [False]

        prefix, retained = planner.preserve_finished_windows(planned, {published['id']: published}, recordings)
        assert [line['segment']['id'] for line in prefix['lines']] == ['prefix']
        assert retained['existing_id'] == published['id']
        assert [line['segment']['id'] for line in retained['lines']] == ['tail']
        assert retained['finished']
        assert planner.build('synthetic', prefix, recordings)['status'] == 'processing'

    def test_only_the_last_stretch_stays_open(self):
        # Production shapes (2026-11-19): a backlog page's continuation marker held every stretch that
        # ends in the page's latest recording open, and speech stamped in the future kept stretches
        # open across recorded silence. Each planned two open windows and parked the owner.
        origin = datetime(2026, 11, 19, tzinfo=timezone.utc)
        speech = [
            {'id': 'a', 'start': 0, 'end': 10, 'text': 'synthetic speech a'},
            {'id': 'b', 'start': 400, 'end': 410, 'text': 'synthetic speech b'},
            {'id': 'c', 'start': 800, 'end': 810, 'text': 'synthetic speech c'},
        ]
        continued = {
            'id': 'page',
            'started_at': origin,
            'finished_at': origin + timedelta(seconds=810),
            '_v3_page_continues': True,
            'transcript_segments': speech,
        }
        groups = outline.stretches([continued], origin + timedelta(hours=10))
        assert [group['finished'] for group in groups] == [True, True, False]

        future = {'id': 'future', 'started_at': origin, 'transcript_segments': speech}
        groups = outline.stretches([future], origin + timedelta(seconds=30))
        assert [group['finished'] for group in groups] == [True, True, False]
        entry = {'first_line': 1, 'kind': 'conversation', 'title': '', 'line': ''}
        windows = planner.windows(groups, [[entry] for _ in groups], cohesion=True)
        assert [window['finished'] for window in windows] == [True, True, False]
