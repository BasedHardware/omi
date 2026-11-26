from datetime import datetime, timedelta, timezone

import pytest

from config.conversations_v3 import boundary_seconds, max_window_seconds
from utils.conversations.summary_selection import render_sections_markdown, select_primary_summary
from utils.conversations.v3 import context, outline

AT = datetime(2026, 11, 19, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    'gap,lock,expected',
    [
        ('120', '3600', (120, 3600)),
        ('1800', '120', (1800, 120)),
        ('119', '3601', (300, 300)),
        ('1801', '119', (300, 300)),
        ('invalid', '1.5', (300, 300)),
        ('300', '300', (300, 300)),
    ],
)
def test_boundary_settings(monkeypatch, gap, lock, expected):
    monkeypatch.setenv('CONVERSATIONS_V3_SILENCE_GAP_SECONDS', gap)
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', lock)
    assert boundary_seconds(cohesion=True) == expected
    assert boundary_seconds(cohesion=False) == (300, 300)


@pytest.mark.parametrize(
    'value,expected',
    [
        (None, 10800),
        ('  OFF ', 0),
        ('0', 0),
        ('120', 120),
        ('7200', 7200),
        ('119', 10800),
        ('10801', 10800),
        ('-1', 10800),
        ('invalid', 10800),
    ],
)
def test_window_cap_setting(monkeypatch, value, expected):
    key = 'CONVERSATIONS_V3_MAX_WINDOW_SECONDS'
    if value is None:
        monkeypatch.delenv(key, raising=False)
    else:
        monkeypatch.setenv(key, value)
    assert max_window_seconds() == expected


def test_gap_and_lock_deadlines_are_independent():
    member = {
        'id': 'recording',
        'started_at': AT,
        'transcript_segments': [
            {'start': 0, 'end': 10, 'text': 'synthetic'},
            {'start': 500, 'end': 510, 'text': 'fresh synthetic'},
        ],
    }
    now = AT + timedelta(seconds=900)
    defaults = outline.stretches([member], now)
    assert len(defaults) == 2 and all(g['finished'] for g in defaults)
    groups = outline.stretches([member], now, silence_gap=timedelta(seconds=900), lock_delay=timedelta(seconds=3600))
    assert len(groups) == 1 and not groups[0]['finished']
    (ready,) = outline.stretches(
        [member], now + timedelta(seconds=600), silence_gap=timedelta(seconds=900), lock_delay=timedelta(seconds=3600)
    )
    assert ready['outline_ready'] and not ready['finished']


def _locked_pair(at=AT):
    from utils.conversations.v3 import planner

    left, right = at, at + timedelta(seconds=30)
    middle, end = at + timedelta(seconds=10), at + timedelta(seconds=20)
    segments = [
        {'id': 'a', 'start': 0, 'end': 20, 'text': 'first synthetic segment'},
        {'id': 'b', 'start': 10, 'end': 30, 'text': 'second synthetic segment'},
    ]
    recording = {
        'id': 'r',
        'started_at': left,
        'finished_at': right,
        'transcript_segments': segments,
        'audio_files': [{'id': 'audio', 'duration': 30}],
    }
    group = outline.stretches([recording], right + timedelta(minutes=10))[0]
    first, second = group['lines']
    window = {'kind': 'conversation', 'finished': True, 'lines': [first, second], 'line': ''}
    older = {
        'id': 'early',
        'status': 'completed',
        'v3_derived': True,
        'v3_recording_ids': ['r'],
        'started_at': left,
        'finished_at': end,
        'summary_covers_through': end,
        'kind': 'conversation',
        'transcript_segments': [segments[0]],
        'structured': {'title': 'Early', 'sections': [{'heading': 'A', 'body_markdown': 'First'}]},
        'recording_pieces': [{'recording_id': 'r', 'audio_file_id': 'audio', 'start': 0, 'end': 20}],
        'title_locked': True,
    }
    later = {
        **older,
        'id': 'late',
        'started_at': middle,
        'finished_at': right,
        'summary_covers_through': right,
        'transcript_segments': [{**segments[1], 'start': 0, 'end': 20}],
        'structured': {'title': 'Late', 'overview': 'Recap', 'sections': [{'heading': 'B', 'body_markdown': 'Second'}]},
        'recording_pieces': [{'recording_id': 'r', 'audio_file_id': 'audio', 'start': 10, 'end': 30}],
    }
    recording['claims'] = [
        {'conversation_id': row['id'], 'start': row['started_at'], 'end': row['finished_at']} for row in (older, later)
    ]
    assert planner.is_unlocked(older) is False
    return window, {'late': later, 'early': older}, {'r': recording}


def test_locked_refinement_keeps_earliest_id_notes_and_single_copy_of_audio():
    from utils.conversations.v3 import planner, refinement

    window, existing, recordings = _locked_pair()
    _, merged = refinement.candidate([window], existing, recordings)
    assert merged['id'] == 'early'
    assert merged['_v3_absorbed'] == ['late']
    assert merged['summary_covers_through'] == merged['finished_at'] == existing['late']['finished_at']
    assert [section['heading'] for section in merged['structured']['sections']] == ['A', 'Late', 'B']
    summary = select_primary_summary(merged)
    assert summary.kind == 'sections'
    assert 'Recap' in summary.content and 'Second' in summary.content
    assert merged['_v3_claims'] == {'r': [{'start': AT, 'end': AT + timedelta(seconds=30)}]}
    assert [(piece['start'], piece['end']) for piece in merged['recording_pieces']] == [(0, 20), (20, 30)]

    recorded_claims = [{'conversation_id': 'early', **claim} for claim in merged['_v3_claims']['r']]
    recordings['r']['claims'] = recorded_claims
    existing = {
        'early': merged,
        'late': {**existing['late'], 'deleted': True, 'v3_refined': True, 'v3_claims_transferred_to': 'early'},
    }
    split = [{**window, 'lines': [line]} for line in window['lines']]
    retained = planner.preserve_finished_windows(split, existing, recordings)
    assert [piece['existing_id'] for piece in retained] == ['early']
    rebuilt = planner.build('synthetic', retained[0], recordings, merged)
    assert rebuilt['recording_pieces'] == merged['recording_pieces']


@pytest.mark.parametrize('field', ['manual_end', 'v3_open_locked', 'v3_unlocked', 'v3_process_pending'])
def test_locked_refinement_respects_finalization_barriers(field):
    from utils.conversations.v3 import refinement

    window, existing, recordings = _locked_pair()
    existing['late'][field] = True
    assert refinement.candidate([window], existing, recordings) is None


def test_locked_refinement_does_not_join_distinct_planned_stretches():
    from utils.conversations.v3 import refinement

    window, existing, recordings = _locked_pair()
    split = [{**window, 'lines': [line]} for line in window['lines']]
    assert refinement.candidate(split, existing, recordings) is None


def test_joining_provisional_cards_preserves_their_claims_until_lock():
    from utils.conversations.v3 import planner

    window, existing, recordings = _locked_pair()
    for row in existing.values():
        row['v3_unlocked'] = True
    window['finished'] = False
    preview = planner.preserve_finished_windows([window], existing, recordings, protect_provisional=True)
    assert [piece['existing_id'] for piece in preview] == ['early', 'late']
    assert [piece['finished'] for piece in preview] == [True, False]
    for piece in preview:
        row = planner.build('synthetic', piece, recordings, existing[piece['existing_id']])
        assert row['_v3_claims']['r'] == [
            {'start': claim['start'], 'end': claim['end']}
            for claim in recordings['r']['claims']
            if claim['conversation_id'] == row['id']
        ]


def test_locked_refinement_preserves_an_opened_survivor():
    from utils.conversations.v3 import refinement

    window, existing, recordings = _locked_pair()
    existing['early']['v3_open_locked'] = True
    _, merged = refinement.candidate([window], existing, recordings)
    assert merged['id'] == 'early' and merged['v3_open_locked']


def test_locked_refinement_refuses_a_downgrade_after_source_protection_changes():
    from utils.conversations.v3 import refinement

    window, existing, recordings = _locked_pair()
    recordings['r']['data_protection_level'] = 'enhanced'
    assert refinement.candidate([window], existing, recordings) is None


def test_outline_prompt_uses_configured_silence_threshold():
    window, _, recordings = _locked_pair()
    group = {
        'lines': window['lines'],
        'end': recordings['r']['finished_at'],
        'fingerprint': 'synthetic',
    }
    # A gap at or under five minutes keeps the hard boundary; a longer one cuts at sit-downs instead.
    configured = outline.messages(group, timezone.utc, cohesion=True, silence_gap=timedelta(seconds=240))
    baseline = outline.messages(group, timezone.utc, cohesion=True)
    assert '240 seconds of recorded silence' in configured[0][1]
    assert 'Five minutes of recorded silence' in baseline[0][1]
    assert context.cache_key(group, configured) != context.cache_key(group, baseline)


def test_provisional_title_and_emoji_are_refreshed_at_lock():
    from utils.conversations.v3 import planner

    window, existing, recordings = _locked_pair()
    window.update(title='Revised', line='Revised preview', emoji='🌲')
    prior = {**existing['early'], 'v3_unlocked': True}
    row = planner.build('synthetic', window, recordings, prior)
    assert row['structured']['title'] == 'Revised'
    assert row['structured']['overview'] == 'Revised preview'
    assert row['structured']['emoji'] == '🌲'


def test_preview_anchors_skip_model_sections_without_line_numbers():
    window, _, _ = _locked_pair()
    group = {'lines': window['lines']}
    entries = [
        {
            'first_line': 1,
            'sections': [
                {'title': 'missing'},
                {'title': 'unusable', 'first_line': '1'},
                {'title': 'valid', 'first_line': 2},
            ],
        }
    ]
    anchors = outline.preview_anchors(group, entries)
    assert set(anchors) == {'1', '2'}
    [rebased] = outline.reuse_preview(group, {'entries': entries, 'anchors': anchors})
    assert rebased['sections'] == [{'title': 'valid', 'first_line': 2}]


@pytest.mark.parametrize('segment_ids', [('first', 'second'), (None, None)])
def test_preview_anchors_disambiguate_lines_with_the_same_clock(segment_ids):
    first, second = [{'conversation_id': 'r', 'start': AT, 'segment': {'id': segment_id}} for segment_id in segment_ids]
    leading = {'conversation_id': 'r', 'start': AT - timedelta(seconds=1), 'segment': {}}
    entries = [
        {'first_line': 1, 'sections': [{'title': 'first', 'first_line': 1}]},
        {'first_line': 2, 'sections': [{'title': 'second', 'first_line': 2}]},
    ]
    anchors = outline.preview_anchors({'lines': [first, second]}, entries)

    rebased = outline.reuse_preview({'lines': [leading, first, second]}, {'entries': entries, 'anchors': anchors})

    assert [entry['first_line'] for entry in rebased] == [1, 3]
    assert [entry['sections'][0]['first_line'] for entry in rebased] == [2, 3]


def test_preview_skips_topic_whose_anchor_was_deleted():
    window, _, _ = _locked_pair()
    first, second = window['lines']
    entries = [{'first_line': 1, 'title': 'Removed'}, {'first_line': 2, 'title': 'Remaining'}]
    anchors = outline.preview_anchors({'lines': [first, second]}, entries)

    [rebased] = outline.reuse_preview({'lines': [second]}, {'entries': entries, 'anchors': anchors})

    assert rebased['first_line'] == 1
    assert rebased['title'] == 'Remaining'


def test_locked_refinement_keeps_overview_only_card_in_place():
    from utils.conversations.v3 import refinement

    window, existing, recordings = _locked_pair()
    existing['late']['structured'].pop('sections')
    assert refinement.candidate([window], existing, recordings) is None


def test_locked_refinement_keeps_both_generated_notes_in_the_primary_summary():
    from utils.conversations.v3 import refinement

    window, existing, recordings = _locked_pair()
    for row in existing.values():
        row['structured']['overview'] = render_sections_markdown(row['structured']['sections'])
    _, merged = refinement.candidate([window], existing, recordings)
    summary = select_primary_summary(merged)
    assert summary.kind == 'sections'
    assert summary.content.count('First') == summary.content.count('Second') == 1


def test_locked_refinement_does_not_absorb_a_card_owning_open_loop_extractions():
    from utils.conversations.v3 import refinement

    window, existing, recordings = _locked_pair()
    existing['late']['open_loop_extractions'] = 'synthetic-protected-payload'
    assert refinement.candidate([window], existing, recordings) is None


@pytest.mark.parametrize(
    'flag',
    [
        'sync_relevance_user_kept',
        'has_photos',
        'folder_user_set',
        'has_transcript_corrections',
        'user_corrections',
        'capture_group',
    ],
)
def test_locked_refinement_preserves_user_managed_cards(flag):
    from utils.conversations.v3 import refinement

    window, existing, recordings = _locked_pair()
    existing['late'][flag] = True
    assert refinement.candidate([window], existing, recordings) is None


@pytest.mark.parametrize('card', ['early', 'late'])
def test_locked_refinement_does_not_move_note_claim_targets(card):
    from utils.conversations.v3 import refinement

    window, existing, recordings = _locked_pair()
    existing[card]['structured']['note_claims'] = [{'target': '/sections/0/body_markdown'}]

    assert refinement.candidate([window], existing, recordings) is None
