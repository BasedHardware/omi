"""Pure smart-merge wall-clock gap policy: live-recording lineage proof and wall-gap rules.

The wall-clock gap policy replaces the speech-bound gap check only when both
sides of the pair carry live ``recording_origin_id`` lineage that proves they
are generations of the same client recording. Everything else — partition,
predecessor gates, word/segment/fragment caps — is unchanged.
"""

from datetime import datetime, timedelta, timezone

import pytest

from config import conversation_smart_merge as config
from utils.conversations import smart_merge_policy as policy

T0 = datetime(2026, 9, 28, 23, 0, tzinfo=timezone.utc)
WORDS = ' '.join(['word'] * 30)
ORIGIN = 'recording-1'
SESSION = 'session-1'

WALL_ENV = 'CONVERSATION_SMART_MERGE_WALLCLOCK_GAP_MODE'


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


def _stamps(origin=ORIGIN, session=SESSION):
    return {'recording_session_id': session, 'recording_origin_id': origin}


def _row(cid, created_s, started_s, finished_s, **extra):
    row = {
        'id': cid,
        'source': 'omi',
        'client_device_id': 'pendant-1',
        'status': 'completed',
        'discarded': False,
        'created_at': T0 + timedelta(seconds=created_s),
        'started_at': T0 + timedelta(seconds=started_s),
        'finished_at': T0 + timedelta(seconds=finished_s),
        'structured': {'title': f'title {cid}', 'overview': f'overview {cid}'},
    }
    row.update(extra)
    return row


def _live_row(cid, created_s, started_s, finished_s, origin=ORIGIN, **extra):
    extra.setdefault('external_data', _stamps(origin))
    return _row(cid, created_s, started_s, finished_s, **extra)


def _drifted_pair():
    """Same-origin live pair whose legacy gap is negative: wall gap is 120 s."""
    survivor = _live_row('p', 0, 0, 600)
    new = _live_row('n', 720, 400, 1020)
    s_segments = _segments(count=1, first_start=0.0) + _segments(count=1, first_start=595.0)
    n_segments = _segments()
    return survivor, s_segments, new, n_segments


@pytest.mark.parametrize(
    'raw, mode',
    [
        ('', 'off'),
        ('   ', 'off'),
        ('off', 'off'),
        (' OFF ', 'off'),
        ('shadow', 'shadow'),
        (' SHADOW ', 'shadow'),
        ('on', 'on'),
        ('On', 'on'),
        ('merge', 'off'),
        ('true', 'off'),
        ('bogus', 'off'),
    ],
)
def test_wallclock_gap_mode_parsing(monkeypatch, raw, mode):
    monkeypatch.setenv(WALL_ENV, raw)
    assert config.smart_merge_wallclock_gap_mode().value == mode


def test_wallclock_gap_mode_unset_defaults_off(monkeypatch):
    monkeypatch.delenv(WALL_ENV, raising=False)
    assert config.smart_merge_wallclock_gap_mode() is config.SmartMergeWallclockGapMode.OFF


def test_newest_wallclock_fragment_picks_max_finish_not_max_start():
    fragments = [
        policy.Fragment('late-finish', T0 - timedelta(minutes=30), T0 + timedelta(minutes=40), 't', 'o'),
        policy.Fragment('older', T0 - timedelta(minutes=10), T0 - timedelta(minutes=5), 't', 'o'),
    ]
    row = _live_row('s', -40 * 60, -40 * 60, -20 * 60)
    row['smart_merge'] = {
        'role': 'survivor',
        'revision': 1,
        'refreshed_revision': 1,
        'fragments': [f.as_ledger_entry() for f in fragments],
    }
    assert policy.newest_wallclock_fragment(row).id == 'late-finish'


def test_newest_wallclock_fragment_unmerged_row_is_itself():
    row = _live_row('p', 0, 0, 600)
    fragment = policy.newest_wallclock_fragment(row)
    assert fragment is not None and fragment.id == 'p' and fragment.finished_at == row['finished_at']


def test_newest_wallclock_fragment_malformed_ledger_proves_nothing():
    row = _live_row('s', 0, 0, 600)
    row['smart_merge'] = {
        'role': 'survivor',
        'revision': 1,
        'refreshed_revision': 1,
        'fragments': [{'id': 'bad'}, 'junk'],
    }
    assert policy.newest_wallclock_fragment(row) is None


def test_newest_wallclock_fragment_over_budget_ledger_proves_nothing():
    row = _live_row('s', 0, 0, 600)
    row['smart_merge'] = {
        'role': 'survivor',
        'revision': 1,
        'refreshed_revision': 1,
        'fragments': [
            policy.Fragment(
                f'f{i}', T0 + timedelta(minutes=i), T0 + timedelta(minutes=i + 1), 't', 'o'
            ).as_ledger_entry()
            for i in range(config.MAX_FRAGMENTS + 1)
        ],
    }
    assert policy.newest_wallclock_fragment(row) is None


def test_wallclock_pair_with_negative_legacy_gap_is_eligible():
    survivor, s_segments, new, n_segments = _drifted_pair()
    legacy = policy.check_pair(survivor, s_segments, new, n_segments)
    assert legacy.reason == 'gap_out_of_window' and legacy.gap_seconds < 0
    check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True, last_fragment_row=survivor)
    assert check.reason is None
    assert check.same_recording is True
    assert check.gap_seconds == 120.0
    assert check.speech_gap_seconds is None


@pytest.mark.parametrize('gap_seconds', [0, 60, 119, 120, 3600])
def test_wallclock_gap_window_allows_zero_to_max(gap_seconds):
    survivor, s_segments, new, n_segments = _drifted_pair()
    new['created_at'] = survivor['finished_at'] + timedelta(seconds=gap_seconds)
    new['finished_at'] = new['created_at'] + timedelta(seconds=300)
    check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True, last_fragment_row=survivor)
    assert check.reason is None and check.same_recording is True
    assert check.gap_seconds == float(gap_seconds)


def test_wallclock_gap_over_max_is_out_of_window():
    survivor, s_segments, new, n_segments = _drifted_pair()
    new['created_at'] = survivor['finished_at'] + timedelta(seconds=3601)
    new['finished_at'] = new['created_at'] + timedelta(seconds=300)
    check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True, last_fragment_row=survivor)
    assert check.reason == 'gap_out_of_window' and check.same_recording is True


def test_wallclock_gap_negative_is_a_bounded_reason():
    survivor, s_segments, new, n_segments = _drifted_pair()
    new['created_at'] = survivor['finished_at'] - timedelta(seconds=1)
    check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True, last_fragment_row=survivor)
    assert check.reason == 'wallclock_gap_negative' and check.same_recording is True
    assert check.gap_seconds == -1.0


@pytest.mark.parametrize('field', ['created_at', 'finished_at'])
def test_wallclock_missing_wall_time_is_invalid_not_legacy(field):
    survivor, s_segments, new, n_segments = _drifted_pair()
    new[field] = None
    check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True, last_fragment_row=survivor)
    assert check.reason == 'wallclock_time_invalid' and check.same_recording is True


def test_wallclock_finish_before_created_is_invalid():
    survivor, s_segments, new, n_segments = _drifted_pair()
    new['created_at'], new['finished_at'] = new['finished_at'], new['created_at']
    check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True, last_fragment_row=survivor)
    assert check.reason == 'wallclock_time_invalid'


@pytest.mark.parametrize(
    'survivor_ext, new_ext',
    [
        (None, _stamps()),
        (_stamps(), None),
        ({'recording_origin_id': ORIGIN}, _stamps()),
        (_stamps(), {'recording_session_id': SESSION}),
        (_stamps('other-recording'), _stamps()),
        (_stamps(session='  '), _stamps()),
    ],
)
def test_missing_or_mismatched_live_stamps_run_exact_legacy(survivor_ext, new_ext):
    survivor, s_segments, new, n_segments = _drifted_pair()
    survivor['external_data'] = survivor_ext
    new['external_data'] = new_ext
    legacy = policy.check_pair(survivor, s_segments, new, n_segments)
    check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True, last_fragment_row=survivor)
    assert check.same_recording is False
    assert check.reason == legacy.reason
    assert check.gap_seconds == legacy.gap_seconds
    assert check.speech_gap_seconds == legacy.speech_gap_seconds


def test_sync_row_without_stamps_matches_legacy_eligible_result():
    """A sync-origin-like pair (no live stamps) behaves byte-identically to legacy."""
    survivor, s_segments, new, n_segments = _drifted_pair()
    survivor['external_data'] = None
    new['external_data'] = None
    new['started_at'] = T0 + timedelta(seconds=800)
    new['created_at'] = new['started_at']
    new['finished_at'] = T0 + timedelta(seconds=1400)
    legacy = policy.check_pair(survivor, s_segments, new, n_segments)
    check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True)
    assert check.reason == legacy.reason
    assert check.gap_seconds == legacy.gap_seconds
    assert check.speech_gap_seconds == legacy.speech_gap_seconds
    assert check.same_recording is False


def test_legacy_branch_is_byte_identical_when_wallclock_flag_off():
    survivor, s_segments, new, n_segments = _drifted_pair()
    a = policy.check_pair(survivor, s_segments, new, n_segments)
    b = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=False)
    assert a == b and a.same_recording is False


@pytest.mark.parametrize('created_s', [599, 1600])
def test_legacy_accepted_pair_never_enters_the_wall_path(monkeypatch, created_s):
    """Legacy-first: a pass returns the legacy PairCheck untouched, so a wall
    clock that is negative (599) or invalid (1600 > finished) stays unseen."""
    survivor, s_segments, new, n_segments = _drifted_pair()
    new['created_at'] = T0 + timedelta(seconds=created_s)
    new['started_at'] = T0 + timedelta(seconds=900)
    new['finished_at'] = T0 + timedelta(seconds=1500)
    legacy = policy.check_pair(survivor, s_segments, new, n_segments)
    assert legacy.reason is None and legacy.same_recording is False

    def forbidden(*args, **kwargs):
        raise AssertionError('a legacy-accepted pair must not reach the wall-clock path')

    monkeypatch.setattr(policy, '_check_pair_wallclock', forbidden)
    check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True, last_fragment_row=survivor)
    assert check == legacy


def _ledger_survivor(donor_fragment, **extra):
    survivor = _live_row('s', -3600, -3600, -3000, **extra)
    survivor['smart_merge'] = {
        'role': 'survivor',
        'revision': 1,
        'refreshed_revision': 1,
        'fragments': [
            policy.fragment_of(survivor).as_ledger_entry(),
            donor_fragment.as_ledger_entry(),
        ],
    }
    return survivor


def test_ledger_donor_fragment_requires_the_supplied_row():
    donor = _live_row('d', -1800, -2000, -1500)
    donor['transcript_segments'] = _segments()
    survivor = _ledger_survivor(policy.fragment_of(donor))
    s_segments = _segments()
    new = _live_row('n', -1400, -3200, -1000)
    n_segments = _segments()

    check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True)
    assert check.same_recording is False and check.reason == 'gap_out_of_window'
    for bad in (
        dict(donor, id='other'),
        dict(donor, external_data=_stamps('other-recording')),
        dict(donor, client_device_id='pendant-2'),
        dict(donor, external_data={'recording_origin_id': ORIGIN}),
    ):
        check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True, last_fragment_row=bad)
        assert check.same_recording is False, bad.get('id')
        assert check.reason == 'gap_out_of_window'

    check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True, last_fragment_row=donor)
    assert check.same_recording is True and check.reason is None
    assert check.gap_seconds == 100.0


def test_ledger_donor_fragment_row_must_be_completed_or_a_real_tombstone():
    donor = _live_row('d', -1800, -2000, -1500)
    donor['transcript_segments'] = _segments()
    survivor = _ledger_survivor(policy.fragment_of(donor))
    s_segments = _segments()
    new = _live_row('n', -1400, -3200, -1000)
    n_segments = _segments()

    tombstone = dict(
        donor,
        deleted=True,
        discarded=True,
        sync_merged_into='s',
        smart_merge={'role': 'donor', 'survivor_id': 's'},
    )
    check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True, last_fragment_row=tombstone)
    assert check.same_recording is True and check.reason is None

    for bad in (
        dict(donor, status='processing'),
        dict(
            donor,
            deleted=True,
            discarded=True,
            sync_merged_into='other',
            smart_merge={'role': 'donor', 'survivor_id': 'other'},
        ),
        dict(donor, deleted=True, discarded=True, sync_merged_into='s', smart_merge={'role': 'survivor'}),
        dict(donor, deleted=True, discarded=True, sync_merged_into='s'),
    ):
        check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True, last_fragment_row=bad)
        assert check.same_recording is False
        assert check.reason == 'gap_out_of_window'


def test_newest_fragment_word_count_uses_the_donor_rows_own_transcript():
    donor = _live_row('d', -2000, -2000, -1500)
    donor['transcript_segments'] = [dict(_segments(count=1)[0], text='tiny')]
    survivor = _ledger_survivor(policy.fragment_of(donor))
    s_segments = _segments()
    new = _live_row('n', -1400, -3200, -1000)
    n_segments = _segments()
    check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True, last_fragment_row=donor)
    assert check.same_recording is True and check.reason == 'too_few_words'


def test_survivor_missing_stamps_is_fine_when_last_fragment_is_a_proven_donor():
    donor = _live_row('d', -2000, -2000, -1500)
    donor['transcript_segments'] = _segments()
    survivor = _ledger_survivor(policy.fragment_of(donor))
    survivor['external_data'] = None
    new = _live_row('n', -1400, -3200, -1000)
    check = policy.check_pair(survivor, _segments(), new, _segments(), wallclock_gap=True, last_fragment_row=donor)
    assert check.same_recording is True and check.reason is None


def test_wall_span_cap_uses_created_and_finished_not_speech_bounds():
    survivor = _live_row('p', 0, -4 * 3600, 600)
    s_segments = _segments()
    new = _live_row('n', 720, 400, 1020)
    n_segments = _segments()
    check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True, last_fragment_row=survivor)
    assert check.same_recording is True and check.reason is None


def test_wall_span_cap_rejects_a_real_over_three_hour_span():
    survivor = _live_row('p', 0, 0, 600)
    new = _live_row('n', 720, 400, 4 * 3600)
    check = policy.check_pair(survivor, _segments(), new, _segments(), wallclock_gap=True, last_fragment_row=survivor)
    assert check.same_recording is True and check.reason == 'span_cap'


def test_wallclock_path_keeps_every_unchanged_gate():
    survivor, s_segments, new, n_segments = _drifted_pair()
    for mutate, reason in [
        (lambda s, n: s.update(starred=True), 'user_managed'),
        (lambda s, n: s.update(relevance_decision={'trigger': 'client_finalize'}), 'predecessor_user_ended'),
        (lambda s, n: s.update(status='processing'), 'predecessor_not_completed'),
        (
            lambda s, n: s.update(smart_merge={'role': 'survivor', 'revision': 2, 'refreshed_revision': 1}),
            'predecessor_refresh_pending',
        ),
        (lambda s, n: n.update(client_device_id='pendant-2'), 'no_predecessor'),
    ]:
        s2, n2 = dict(survivor), dict(new)
        mutate(s2, n2)
        check = policy.check_pair(s2, s_segments, n2, n_segments, wallclock_gap=True, last_fragment_row=s2)
        assert check.reason == reason, reason


def test_fragment_cap_still_applies_on_the_wall_path():
    ledger = [
        policy.Fragment(
            f'f{i}', T0 - timedelta(minutes=60 - i), T0 - timedelta(minutes=59 - i), 't', 'o'
        ).as_ledger_entry()
        for i in range(config.MAX_FRAGMENTS - 1)
    ]
    survivor, s_segments, new, n_segments = _drifted_pair()
    ledger.append(policy.fragment_of(survivor).as_ledger_entry())
    survivor['smart_merge'] = {
        'role': 'survivor',
        'revision': 11,
        'refreshed_revision': 11,
        'fragments': ledger,
    }
    check = policy.check_pair(survivor, s_segments, new, n_segments, wallclock_gap=True, last_fragment_row=survivor)
    assert check.same_recording is True and check.reason == 'fragment_cap'
