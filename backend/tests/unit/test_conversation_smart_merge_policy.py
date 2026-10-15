"""Deterministic smart-merge rules: eligibility, gap window, caps, stretch, and absorb payloads."""

from datetime import datetime, timedelta, timezone

import pytest

from config import conversation_smart_merge as config
from utils.conversations import smart_merge_policy as policy
from utils.conversations.smart_merge_state import Fragment

T0 = datetime(2026, 9, 28, 23, 0, tzinfo=timezone.utc)
WORDS = ' '.join(['word'] * 30)


def _segments(count=2, *, speaker=0, text=WORDS, length=10.0, first_start=0.0):
    return [
        {
            'id': f'seg-{speaker}-{i}',
            'text': text,
            'speaker': f'SPEAKER_{speaker:02d}',
            'speaker_id': speaker,
            'is_user': False,
            'start': first_start + i * length,
            'end': first_start + (i + 1) * length,
        }
        for i in range(count)
    ]


def _row(cid, start_min, end_min, **extra):
    row = {
        'id': cid,
        'source': 'omi',
        'client_device_id': 'pendant-1',
        'status': 'completed',
        'discarded': False,
        'created_at': T0 + timedelta(minutes=start_min),
        'started_at': T0 + timedelta(minutes=start_min),
        'finished_at': T0 + timedelta(minutes=end_min),
        'structured': {'title': f'title {cid}', 'overview': f'overview {cid}'},
    }
    row.update(extra)
    return row


def _pair(gap_minutes=5.0, *, survivor_minutes=10, new_minutes=10):
    survivor = _row('p', 0, survivor_minutes)
    start = survivor_minutes + gap_minutes
    new = _row('n', start, start + new_minutes)
    # Speech fills each wall window so the speech gap equals the recorded gap.
    s_segments = _segments(count=1, first_start=0.0) + _segments(count=1, first_start=survivor_minutes * 60 - 10.0)
    s_segments[1]['id'] = 'seg-0-last'
    n_segments = _segments(first_start=0.0)
    return survivor, s_segments, new, n_segments


def test_new_conversation_exclusions(monkeypatch):
    good = _row('n', 0, 5)
    segments = _segments()
    assert policy.new_conversation_skip(good, segments, capture_end=True) is None

    assert (
        policy.new_conversation_skip(dict(good, uses_custom_stt=True), segments, capture_end=True)
        == 'refresh_unavailable'
    )
    assert (
        policy.new_conversation_skip(dict(good, source='desktop'), segments, capture_end=True) == 'not_eligible_source'
    )
    assert policy.new_conversation_skip(good, segments, capture_end=False) == 'not_capture_end'
    for change in (
        {'status': 'processing'},
        {'discarded': True},
        {'deleted': True},
        {'smart_merge': {'role': 'donor'}},
        {'smart_merge': {'role': 'survivor', 'revision': 1}},  # a merge target never becomes a donor
    ):
        assert (
            policy.new_conversation_skip(dict(good, **change), segments, capture_end=True)
            == 'conversation_not_eligible'
        )
    bridged = dict(good, sync_merged_from=['bridge-donor'])
    assert policy.new_conversation_skip(bridged, segments, capture_end=True) is None
    monkeypatch.setenv(config.SMART_MERGE_FLATTEN_ENV, 'off')
    assert policy.new_conversation_skip(bridged, segments, capture_end=True) == 'conversation_not_eligible'
    monkeypatch.delenv(config.SMART_MERGE_FLATTEN_ENV, raising=False)
    assert policy.new_conversation_skip(good, [], capture_end=True) == 'conversation_not_eligible'
    wake = [dict(segments[0], text='hey omi what is on my calendar')]
    assert policy.new_conversation_skip(good, wake, capture_end=True) == 'wake_word'


def test_fragment_metadata_is_bounded_before_it_reaches_jev_or_the_ledger():
    row = _row('n', 0, 5, structured={'title': 'T' * 10000, 'overview': 'O' * 10000})
    fragment = policy.fragment_of(row)
    assert fragment is not None
    assert len(fragment.title) <= config.LEDGER_TITLE_CHARS
    assert len(fragment.overview) <= config.LEDGER_OVERVIEW_CHARS


@pytest.mark.parametrize(
    'change',
    [
        {'user_title': 'Mine'},
        {'starred': True},
        {'folder_user_set': True},
        {'sync_relevance_user_kept': True},
        {'visibility': 'shared'},
        {'has_photos': True},
        {'manual_speaker_assignments': {'0': 'self'}},
        {'is_locked': True},
        {'capture_group': {'id': 'g'}},
        {'external_data': {'duplicate_capture_of': 'other'}},
    ],
)
def test_every_user_managed_exclusion_applies_to_both_sides(change):
    survivor, s_segments, new, n_segments = _pair()
    assert policy.new_conversation_skip(dict(new, **change), n_segments, capture_end=True) == 'user_managed'
    assert policy.check_pair(dict(survivor, **change), s_segments, new, n_segments).reason == 'user_managed'


def test_predecessor_state_exclusions():
    survivor, s_segments, new, n_segments = _pair()
    assert policy.check_pair(survivor, s_segments, new, n_segments).reason is None
    assert (
        policy.check_pair(dict(survivor, uses_custom_stt=True), s_segments, new, n_segments).reason
        == 'refresh_unavailable'
    )
    for status in ('in_progress', 'processing', 'merging', 'failed'):
        assert policy.predecessor_status_skip(dict(survivor, status=status)) == 'predecessor_not_completed'
    assert policy.predecessor_status_skip(dict(survivor, discarded=True)) == 'predecessor_not_completed'
    ended = dict(survivor, relevance_decision={'trigger': 'client_finalize'})
    assert policy.check_pair(ended, s_segments, new, n_segments).reason == 'predecessor_user_ended'
    owed = dict(survivor, smart_merge={'role': 'survivor', 'revision': 2, 'refreshed_revision': 1})
    assert policy.check_pair(owed, s_segments, new, n_segments).reason == 'predecessor_refresh_pending'
    wake = [dict(s_segments[0], text='hey omi remind me later')] + s_segments
    assert policy.check_pair(survivor, wake, new, n_segments).reason == 'wake_word'


def test_partition_treats_unknown_device_as_its_own_partition():
    survivor, s_segments, new, n_segments = _pair()
    assert (
        policy.check_pair(dict(survivor, client_device_id=None), s_segments, new, n_segments).reason == 'no_predecessor'
    )
    assert (
        policy.check_pair(
            dict(survivor, client_device_id=None), s_segments, dict(new, client_device_id=None), n_segments
        ).reason
        is None
    )
    assert policy.check_pair(survivor, s_segments, dict(new, is_locked=True), n_segments).reason == 'no_predecessor'


@pytest.mark.parametrize(
    'gap_seconds, allowed',
    [(119, False), (120, True), (121, True), (3599, True), (3600, True), (3601, False), (-30, False)],
)
def test_recorded_gap_window_edges(gap_seconds, allowed):
    survivor, s_segments, new, n_segments = _pair(gap_minutes=gap_seconds / 60)
    check = policy.check_pair(survivor, s_segments, new, n_segments)
    assert (check.reason is None) is allowed
    if not allowed:
        assert check.reason == 'gap_out_of_window'
    assert check.gap_seconds == pytest.approx(gap_seconds)


def test_speech_gap_below_120_seconds_is_a_shard_even_when_the_recorded_gap_is_wide():
    survivor, s_segments, new, n_segments = _pair(gap_minutes=5)
    # The new conversation's first word lands 3 minutes *before* its recorded start (drifted origin).
    drifted = _segments(first_start=-190.0)
    check = policy.check_pair(survivor, s_segments, new, drifted)
    assert check.reason == 'gap_out_of_window'
    assert check.speech_gap_seconds < 120


def test_both_sides_need_25_words():
    survivor, s_segments, new, n_segments = _pair()
    few = _segments(count=1, text=' '.join(['w'] * 24), first_start=0.0)
    assert policy.check_pair(survivor, s_segments, new, few).reason == 'too_few_words'
    short = _segments(count=1, text='a b c', first_start=580.0)
    assert policy.check_pair(survivor, short, new, n_segments).reason == 'too_few_words'


def test_snowball_caps(monkeypatch):
    survivor, s_segments, new, n_segments = _pair()
    monkeypatch.setattr(policy, 'MAX_MERGED_SPAN_SECONDS', 60)
    assert policy.check_pair(survivor, s_segments, new, n_segments).reason == 'span_cap'
    monkeypatch.setattr(policy, 'MAX_MERGED_SPAN_SECONDS', config.MAX_MERGED_SPAN_SECONDS)
    monkeypatch.setattr(policy, 'MAX_MERGED_SEGMENTS', 3)
    assert policy.check_pair(survivor, s_segments, new, n_segments).reason == 'segment_cap'
    monkeypatch.setattr(policy, 'MAX_MERGED_SEGMENTS', config.MAX_MERGED_SEGMENTS)
    ledger = [
        Fragment(f'f{i}', T0 - timedelta(minutes=60 - i), T0 - timedelta(minutes=59 - i), 't', 'o').as_ledger_entry()
        for i in range(config.MAX_FRAGMENTS - 1)
    ] + [policy.fragment_of(survivor).as_ledger_entry()]
    full = dict(
        survivor, smart_merge={'role': 'survivor', 'revision': 11, 'refreshed_revision': 11, 'fragments': ledger}
    )
    assert policy.check_pair(full, s_segments, new, n_segments).reason == 'fragment_cap'


def test_three_hour_default_span_cap_rejects_a_long_chain():
    survivor, s_segments, new, n_segments = _pair(gap_minutes=30, survivor_minutes=160)
    assert policy.check_pair(survivor, s_segments, new, n_segments).reason == 'span_cap'


def test_stretch_links_under_30_minutes_and_keeps_the_four_most_recent():
    a = Fragment('a', T0, T0 + timedelta(minutes=5), 'A', 'a')
    chain = [
        Fragment(f'c{i}', T0 - timedelta(minutes=10 * (i + 1)), T0 - timedelta(minutes=10 * (i + 1) - 5), 't', 'o')
        for i in range(6)
    ]
    stretch = policy.stretch_before(a, chain)
    assert [f.id for f in stretch] == ['c3', 'c2', 'c1', 'c0']
    # A link of exactly 30 minutes breaks the stretch (strictly under, as benchmarked).
    far = Fragment('far', T0 - timedelta(minutes=40), T0 - timedelta(minutes=30), 't', 'o')
    assert policy.stretch_before(a, [far]) == []
    near = Fragment('near', T0 - timedelta(minutes=40), T0 - timedelta(minutes=30) + timedelta(seconds=1), 't', 'o')
    assert [f.id for f in policy.stretch_before(a, [near])] == ['near']


def test_absorb_payloads_rebase_reallocate_speakers_and_tombstone_the_donor():
    survivor, s_segments, new, n_segments = _pair(gap_minutes=5)
    survivor['private_cloud_sync_enabled'] = False
    new['private_cloud_sync_enabled'] = True
    decision = {'decision': 'merged', 'p_same': 0.4}
    merged_at = T0 + timedelta(hours=1)
    survivor_update, donor_update = policy.absorb_payloads(
        survivor, s_segments, new, n_segments, merged_at=merged_at, decision=decision
    )
    segments = survivor_update['transcript_segments']
    assert len(segments) == 4
    offset = (new['started_at'] - survivor['started_at']).total_seconds()
    assert segments[2]['start'] == pytest.approx(n_segments[0]['start'] + offset)
    # Both sides used speaker 0; the donor voice gets a new conversation-local number.
    assert {s['speaker_id'] for s in segments[:2]} == {0}
    assert {s['speaker_id'] for s in segments[2:]} == {1}
    assert segments[2]['speaker_id_scope'] == 'legacy-conversation:n:0'
    assert [s['id'] for s in segments[2:]] == [s['id'] for s in n_segments]
    assert survivor_update['finished_at'] == new['finished_at']
    assert survivor_update['private_cloud_sync_enabled'] is True
    assert survivor_update['sync_merged_from'] == ['n']
    assert survivor_update['data_protection_level'] == 'enhanced'
    state = survivor_update['smart_merge']
    assert state['role'] == 'survivor' and state['revision'] == 1 and state['refreshed_revision'] == 0
    assert [entry['id'] for entry in state['fragments']] == ['p', 'n']
    assert survivor_update['sync_content_revision'] == 1  # fences pre-absorb processors
    assert donor_update == {
        'deleted': True,
        'discarded': True,
        'sync_merged_into': 'p',
        'sync_content_revision': 1,
        'smart_merge': {'role': 'donor', 'survivor_id': 'p', 'survivor_revision': 1, 'merged_at': merged_at},
        'smart_merge_decision': decision,
    }


def test_absorb_bumps_an_existing_sync_revision_and_keeps_the_ledger():
    survivor, s_segments, new, n_segments = _pair()
    ledger = [Fragment('p0', T0 - timedelta(minutes=30), T0 - timedelta(minutes=20), 't', 'o').as_ledger_entry()]
    survivor.update(
        sync_content_revision=4,
        data_protection_level='standard',
        smart_merge={'role': 'survivor', 'revision': 3, 'refreshed_revision': 3, 'fragments': ledger},
    )
    new['data_protection_level'] = 'standard'
    survivor_update, _ = policy.absorb_payloads(survivor, s_segments, new, n_segments, merged_at=T0, decision={})
    assert survivor_update['sync_content_revision'] == 5
    assert survivor_update['data_protection_level'] == 'standard'
    assert [entry['id'] for entry in survivor_update['smart_merge']['fragments']] == ['p0', 'n']
    assert survivor_update['smart_merge']['revision'] == 4


def test_fragment_segments_select_the_last_fragment_by_absolute_time():
    survivor, s_segments, new, n_segments = _pair(gap_minutes=5)
    survivor_update, _ = policy.absorb_payloads(survivor, s_segments, new, n_segments, merged_at=T0, decision={})
    merged = dict(survivor, **survivor_update)
    last = policy.ledger_fragments(merged)[-1]
    assert last.id == 'n'
    selected = policy.fragment_segments(merged, survivor_update['transcript_segments'], last)
    assert [s['id'] for s in selected] == [s['id'] for s in n_segments]
