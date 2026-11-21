"""An affirmative native stop belongs to the derived window containing its tail."""

from datetime import datetime, timedelta, timezone

from utils.conversations.v3 import planner, policy

NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)


def line(rid, start, end):
    return {
        'conversation_id': rid,
        'start': NOW + timedelta(seconds=start),
        'end': NOW + timedelta(seconds=end),
        'text': f'{rid} transcript at {start}',
        'segment': {'id': f'{rid}-{start}', 'text': f'{rid} transcript at {start}'},
    }


def entry(first_line, **fields):
    return {
        'first_line': first_line,
        'kind': 'conversation',
        'title': 'Test',
        'line': 'Topic',
        'sections': [],
        'people': [],
        **fields,
    }


def group(lines, *, legacy=False, native=True):
    return {
        'lines': lines,
        'finished': True,
        'legacy_manual_end': legacy,
        'native_manual_end': native,
        'native_manual_source': lines[-1]['conversation_id'] if native else None,
        'manual_end': legacy or native,
    }


def recording(rid, start, end):
    finished_at = NOW + timedelta(seconds=end)
    sealed_at = (NOW + timedelta(seconds=end + 1)).timestamp()
    intent = {'job_id': 'job', 'revision': 1, 'finished_at': finished_at}
    return {
        'id': rid,
        'started_at': NOW + timedelta(seconds=start),
        'finished_at': finished_at,
        'source': 'omi',
        'recording': True,
        'status': 'completed',
        'record_lane_owner': 'batch_live_v1',
        'data_protection_level': 'standard',
        'private_cloud_sync_enabled': True,
        'record_audio_closed': True,
        'record_projection_revision': 1,
        'record_upload_revision': 7,
        'record_sealed_at': sealed_at,
        'finalization_job_id': 'job',
        'finalization_revision': 1,
        'v3_manual_end': True,
        policy.NATIVE_MANUAL_STOP: intent,
        policy.NATIVE_MANUAL_READY: 7,
        policy.NATIVE_MANUAL_PROOF: {'seal': sealed_at, 'intent': intent},
    }


def manual_flags(windows):
    return [(window['manual_end'], window['native_manual_end']) for window in windows]


def test_outline_topics_and_duration_cap_keep_native_stop_on_only_the_exact_tail():
    lines = [line('unrelated', 0, 10), line('recording', 20, 30), line('recording', 7300, 7310)]
    split = planner.windows([group(lines)], [[entry(1), entry(2)]])
    assert manual_flags(split) == [(False, False), (False, False), (True, True)]
    assert split[-1]['lines'] == [lines[-1]]
    assert all(window['finished'] for window in split)


def test_model_resuming_previous_topic_keeps_native_stop_on_combined_tail():
    lines = [line('first', 0, 5), line('recording', 8, 10)]
    (window,) = planner.windows([group(lines)], [[entry(1), entry(2, resumes_previous=True)]])
    assert window['lines'] == lines
    assert manual_flags([window]) == [(True, True)]


def test_preserving_an_existing_window_does_not_move_stop_to_its_earlier_line():
    lines = [line('first', 0, 5), line('recording', 7, 15)]
    planned = planner.windows([group(lines)], [[entry(1)]])
    existing = {
        'previous': {
            'id': 'previous',
            'status': 'completed',
            'started_at': NOW,
            'finished_at': NOW + timedelta(seconds=5),
        }
    }
    preserved = planner.preserve_finished_windows(planned, existing)
    assert manual_flags(preserved) == [(False, False), (True, True)]
    assert preserved[0]['existing_id'] == 'previous'


def test_retain_native_anchor_when_existing_window_accumulates_multiple_topic_parts():
    lines = [line('recording', 0, 5), line('recording', 7, 15)]
    planned = planner.windows([group(lines)], [[entry(1), entry(2)]])
    existing = {'same': {'id': 'same', 'status': 'completed', 'started_at': NOW, 'finished_at': lines[-1]['end']}}
    (preserved,) = planner.preserve_finished_windows(planned, existing)
    assert manual_flags([preserved]) == [(True, True)]
    assert preserved['lines'] == lines


def test_legacy_cut_takes_precedence_and_keeps_current_topic_grouping():
    lines = [line('first', 0, 5), line('recording', 7, 15)]
    split = planner.windows([group(lines, legacy=True)], [[entry(1), entry(2)]])
    assert manual_flags(split) == [(True, False)]


def test_only_native_tail_gets_full_notes_and_its_actual_input_binding():
    lines = [line('first', 0, 5), line('recording', 7, 15)]
    source = recording('recording', 7, 15)
    recordings = {'first': recording('first', 0, 5), 'recording': source}
    first_window, manual_window = planner.windows([group(lines)], [[entry(1), entry(2)]])
    first = planner.build('owner', first_window, recordings)
    manual = planner.build('owner', manual_window, recordings)
    assert first['home_hidden'] and not policy.full_notes(first)
    assert not manual['home_hidden'] and policy.full_notes(manual)
    assert manual[policy.NATIVE_MANUAL_BINDING] == policy.native_manual_binding(source)
    assert manual[policy.NATIVE_MANUAL_BINDING] is not None

    unchanged = planner.build('owner', manual_window, recordings, manual)
    assert unchanged['sync_content_revision'] == manual['sync_content_revision']

    # The ordinary late-content path must never reuse a retired manual proof.
    source['record_upload_revision'] += 1
    stale = planner.build('owner', manual_window, recordings, manual)
    assert not stale['manual_end']
    assert stale[policy.NATIVE_MANUAL_BINDING] is None
    assert stale['transcript_segments'] == manual['transcript_segments']
    assert stale['sync_content_revision'] == manual['sync_content_revision'] + 1

    # An existing genuine legacy stop survives a native proof arriving or disappearing.
    legacy = {**manual, policy.NATIVE_MANUAL_BINDING: None}
    assert planner.build('owner', manual_window, recordings, legacy)['manual_end']


def test_committed_native_notes_keep_only_the_written_window_visible_without_manual_authority():
    capture = recording('recording', 7, 15)
    recordings = {'recording': capture, 'other': recording('other', 0, 5)}
    native_lines = [line('recording', 7, 15)]
    (native_window,) = planner.windows([group(native_lines)], [[entry(1)]])
    prior = planner.build('owner', native_window, recordings)
    receipt = policy.native_manual_notes_receipt(prior)
    assert receipt and receipt['conversation_id'] == prior['id']
    assert receipt['recording_id'] == 'recording'
    prior.update(
        status='completed',
        v3_notes_written=True,
        structured={**prior['structured'], 'overview': 'Already written and visible.'},
    )
    capture['record_upload_revision'] = 8
    (fallback,) = planner.windows([group(native_lines, native=False)], [[entry(1)]])

    # Older natural notes do not establish a native visibility receipt.
    assert planner.build('owner', fallback, recordings, prior)['home_hidden']
    prior[policy.NATIVE_MANUAL_NOTES_VISIBILITY] = receipt
    retained = planner.build('owner', fallback, recordings, prior)
    assert not retained['home_hidden']
    assert not policy.full_notes(retained)
    assert retained[policy.NATIVE_MANUAL_BINDING] is None
    assert retained[policy.NATIVE_MANUAL_NOTES_VISIBILITY] == receipt
    assert retained['structured']['overview'] == 'Already written and visible.'
    assert not planner.build('owner', fallback, recordings, retained)['home_hidden']

    # A split creates no receipt. Copying the receipt to a different row ID
    # or removing the original source from the window cannot grant visibility.
    fresh = planner.build('owner', fallback, recordings)
    assert fresh['home_hidden'] and policy.NATIVE_MANUAL_NOTES_VISIBILITY not in fresh
    copied = planner.build('owner', fallback, recordings, {**retained, 'id': 'different'})
    assert copied['home_hidden'] and copied[policy.NATIVE_MANUAL_NOTES_VISIBILITY] is None
    different_source = planner.build('owner', {**fallback, 'lines': [line('other', 7, 15)]}, recordings, retained)
    assert different_source['home_hidden'] and different_source[policy.NATIVE_MANUAL_NOTES_VISIBILITY] is None

    media = planner.build('owner', {**fallback, 'kind': 'media'}, recordings, retained)
    assert media['home_hidden']
