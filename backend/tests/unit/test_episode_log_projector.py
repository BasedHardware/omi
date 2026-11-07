"""Step-C prototype battery: pure projector vs today's attach path, same inputs.

Every scenario drives BOTH:
  - the oracle: episode_timeline.attach_recorded over StrictFirestore (today's
    production code, exactly how backend/tests/unit/test_recorded_span.py drives it), and
  - the projector: replay of FactLog facts through utils.episodes.log.projector.
and compares placement (window bounds/ids), membership and windows. Divergences
fail loudly with the normalized diff.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from itertools import permutations

import pytest

from tests.unit.episode_log_support.facts import FactLog
from utils.episodes.log.projector import replay
from utils.episodes.log.fold import Fold
from database import episode_log as fact_store
from tests.unit.episode_log_support.oracle import Oracle

pytestmark = pytest.mark.usefixtures('isolated_episode_capture')


T0 = datetime(2026, 11, 4, tzinfo=timezone.utc)
UID = 'proto-u'


@pytest.fixture(autouse=True)
def capture_enabled(monkeypatch):
    monkeypatch.setenv('EPISODES_LOG_ENABLED', 'on')


def S(sec: float):
    return T0 + timedelta(seconds=sec)


# --------------------------------------------------------------------- compare
def _norm_member_activity(activity: dict) -> dict:
    return {cid: at for cid, at in sorted((activity or {}).items())}


def _norm_members(members) -> dict:
    out = {}
    for cid, f in (members or {}).items():
        if isinstance(f, dict):
            out[cid] = (f['start'], f['end'], f.get('source'))
        else:
            out[cid] = tuple(f)
    return dict(sorted(out.items()))


def normalize(view: dict) -> dict:
    return {
        'windows': [
            {
                'id': w['id'],
                'started_at': w['started_at'],
                'last_activity_at': w['last_activity_at'],
                'close_reason': w['close_reason'],
                'conversation_ids': sorted(w['conversation_ids']),
                'member_activity': _norm_member_activity(w['member_activity']),
                'recorded_members': _norm_members(w['recorded_members']),
                'sources': sorted(w['sources'] or []),
                'discarded_conversation_ids': sorted(w['discarded_conversation_ids'] or []),
            }
            for w in sorted(view['windows'], key=lambda w: (w['started_at'], w['id']))
        ],
        'redirects': dict(sorted(view['redirects'].items())),
        'membership': dict(sorted(view['membership'].items())),
    }


def compare(scenario: str, oracle_view: dict, projector_view: dict) -> None:
    left, right = normalize(oracle_view), normalize(projector_view)
    for field in ('windows', 'redirects', 'membership'):
        if left[field] != right[field]:
            pytest.fail(
                f'{scenario}: projector diverges from today on {field}\n'
                f'--- oracle ---\n{_fmt(left[field])}\n--- projector ---\n{_fmt(right[field])}\n'
                f'projector events: {projector_view.get("events")}'
            )


def _fmt(value):
    import pprint

    return pprint.pformat(value, width=120)


def run_scenario(name, ops, fixed_episodes=()):
    """ops: list of ('span', cid, start_off, end_off) | ('discard', cid) | ('repoint', donor, survivor)."""
    with Oracle(UID) as oracle:
        for op in ops:
            if op[0] == 'span':
                oracle.attach(op[1], S(op[2]), S(op[3]))
            elif op[0] == 'discard':
                oracle.discard(op[1])
            elif op[0] == 'repoint':
                oracle.repoint(op[1], op[2])
        oracle_view = oracle.snapshot()
        state = fact_store.state(UID, firestore_client=oracle.store)
        fold = Fold(UID)
        while state.get('cursor', 0) < state.get('next_seq', 0):
            events, cursor = fact_store.read_batch(UID, {'state': state}, firestore_client=oracle.store)
            for event in events:
                fold.apply(event)
            state['cursor'] = cursor
        actual = fold.rows()
        windows = [row for row in actual.values() if not row.get('recorded_merged_into')]
        committed_view = {
            'windows': windows,
            'redirects': {
                eid: row['recorded_merged_into'] for eid, row in actual.items() if row.get('recorded_merged_into')
            },
            'membership': {cid: row['id'] for row in windows for cid in row.get('conversation_ids', [])},
        }
        compare(name + '-atomic-facts', oracle_view, committed_view)

    log = FactLog()
    for op in ops:
        if op[0] == 'span':
            log.span(UID, op[1], S(op[2]), S(op[3]), 'omi')
        elif op[0] == 'discard':
            log.discarded(UID, op[1])
        elif op[0] == 'repoint':
            log.merged(UID, op[1], op[2])
    projector_view = replay(UID, log.facts(UID), fixed_episodes=fixed_episodes)
    compare(name, oracle_view, projector_view)
    return oracle_view, projector_view


# ------------------------------------------------------------------ scenarios
def test_s0_partition_anchor_from_existing_unit_test():
    """test_recorded_span.py::test_cap_successor_uses_its_own_members_recorded_span facts."""
    log = FactLog()
    log.span(UID, 'long', S(0), S(5 * 3600), 'omi')
    log.span(UID, 'next', S(4 * 3600 + 600), S(4 * 3600 + 660), 'omi')
    view = replay(UID, log.facts(UID))
    assert [(w['started_at'], w['last_activity_at'], w['conversation_ids']) for w in view['windows']] == [
        (S(0), S(4 * 3600), ['long']),
        (S(4 * 3600 + 600), S(4 * 3600 + 660), ['next']),
    ]


@pytest.mark.parametrize('order', list(permutations(range(3))))
def test_s1_quiet_gap_windows(order):
    spans = [('c0', 0, 20), ('c1', 30, 60), ('c2', 3600, 3620)]
    ops = [('span', spans[i][0], spans[i][1], spans[i][2]) for i in order]
    oracle_view, projector_view = run_scenario('s1', ops)
    assert [(w['started_at'], w['last_activity_at'], w['conversation_ids']) for w in projector_view['windows']] == [
        (S(0), S(60), ['c0', 'c1']),
        (S(3600), S(3620), ['c2']),
    ]


@pytest.mark.parametrize('order', list(permutations(range(3))))
def test_s2_late_bridge_coalesces(order):
    spans = [('c0', 0, 60), ('c1', 1200, 2500), ('c2', 3600, 3660)]
    ops = [('span', spans[i][0], spans[i][1], spans[i][2]) for i in order]
    oracle_view, projector_view = run_scenario('s2', ops)
    assert len(projector_view['windows']) == 1
    w = projector_view['windows'][0]
    assert (w['started_at'], w['last_activity_at'], sorted(w['conversation_ids'])) == (
        S(0),
        S(3660),
        ['c0', 'c1', 'c2'],
    )
    assert projector_view['membership'] == {c: w['id'] for c in ('c0', 'c1', 'c2')}


@pytest.mark.parametrize('order', [list(range(5)), list(reversed(range(5))), [2, 4, 0, 3, 1]])
def test_s3_four_hour_cap(order):
    ops = [('span', f'c{i}', 3600 * i, 3600 * i + 3600) for i in order]
    oracle_view, projector_view = run_scenario('s3', ops)
    assert [
        (w['started_at'], w['last_activity_at'], w['conversation_ids'], w['close_reason'])
        for w in projector_view['windows']
    ] == [
        (S(0), S(4 * 3600), ['c0', 'c1', 'c2', 'c3'], 'hard_cap'),
        (S(4 * 3600), S(5 * 3600), ['c4'], 'gap'),
    ]


@pytest.mark.parametrize('order', [list(range(2)), list(reversed(range(2)))])
def test_s4_span_growth_merges_components(order):
    ops = [('span', 'c0', 0, 20), ('span', 'c1', 3600, 3620)]
    ops = [ops[i] for i in order] + [('span', 'c0', 0, 3700)]
    oracle_view, projector_view = run_scenario('s4', ops)
    assert len(projector_view['windows']) == 1
    w = projector_view['windows'][0]
    assert (w['started_at'], w['last_activity_at'], w['conversation_ids']) == (S(0), S(3700), ['c0', 'c1'])
    # the pre-growth window for c1 redirected into the grown window
    assert len(oracle_view['redirects']) == 1
    compare('s4-redirects', oracle_view, projector_view)


def test_s5_donor_repoint():
    ops = [
        ('span', 'c0', 0, 20),
        ('span', 'c1', 30, 60),
        ('repoint', 'c0', 'c1'),
        ('span', 'c2', 7200, 7260),
    ]
    oracle_view, projector_view = run_scenario('s5', ops)
    assert len(projector_view['windows']) == 2
    w0 = projector_view['windows'][0]
    assert w0['conversation_ids'] == ['c1']
    assert _norm_members(w0['recorded_members']) == _norm_members({'c1': (S(0), S(60), 'omi')})
    assert projector_view['membership']['c1'] == w0['id']


def test_s6_discard_freezes_and_absorbs():
    ops = [
        ('span', 'c0', 0, 20),
        ('span', 'c1', 30, 60),
        ('discard', 'c1'),
        ('span', 'c2', 120, 180),  # near: must join the frozen window
        ('span', 'c3', 3600, 3660),  # far: must take the canonical path
    ]
    oracle_view, projector_view = run_scenario('s6', ops)
    frozen, fresh = projector_view['windows']
    assert frozen['conversation_ids'] == ['c0', 'c1', 'c2']
    assert frozen['discarded_conversation_ids'] == ['c1']
    assert (frozen['started_at'], frozen['last_activity_at']) == (S(0), S(180))
    assert fresh['conversation_ids'] == ['c3']
    assert projector_view['membership'] == {
        'c0': frozen['id'],
        'c1': frozen['id'],
        'c2': frozen['id'],
        'c3': fresh['id'],
    }


def test_s7_fifty_one_member_component():
    ops = [('span', f'c{i:02d}', 30 * i, 30 * i + 20) for i in range(51)]
    oracle_view, projector_view = run_scenario('s7', ops)
    assert len(projector_view['windows']) == 1
    w = projector_view['windows'][0]
    assert len(w['conversation_ids']) == 51
    assert (w['started_at'], w['last_activity_at']) == (S(0), S(30 * 50 + 20))


def test_s8_repeat_delivery_is_a_noop_on_the_log_side():
    log = FactLog()
    assert log.span(UID, 'c0', S(0), S(20), 'omi') is True
    assert log.span(UID, 'c1', S(30), S(60), 'omi') is True
    before = replay(UID, log.facts(UID))
    assert log.span(UID, 'c0', S(0), S(20), 'omi') is False  # same key: rejected
    assert log.span(UID, 'c1', S(30), S(60), 'omi') is False
    after = replay(UID, log.facts(UID))
    assert normalize(before) == normalize(after)

    # Today's path re-runs the full attach for a repeat delivery: same placement
    # result, but it pays the transaction again (writes counted in s9).
    with Oracle(UID) as oracle:
        oracle.attach('c0', S(0), S(20))
        oracle.attach('c1', S(30), S(60))
        mid = oracle.snapshot()
        oracle.attach('c0', S(0), S(20))  # identical redelivery
        end = oracle.snapshot()
    assert normalize(mid) == normalize(end)


def test_s9_repeat_delivery_oracle_pays_writes():
    with Oracle(UID) as oracle:
        oracle.attach('c0', S(0), S(20))
        oracle.attach('c1', S(30), S(60))
        first = oracle.writes()
        oracle.attach('c0', S(0), S(20))
        second = oracle.writes()
    assert second > first  # today: identical redrive still re-bills the attach transaction


def test_s10_order_invariance_random_pure_domain():
    rng = random.Random(20261104)
    spans = [
        (f'r{i}', offset, offset + length)
        for i, (offset, length) in enumerate(
            [(0, 900), (2000, 3000), (2600, 2900), (15000, 600), (17000, 2000), (32000, 600)]
        )
    ]
    shapes = []
    for _ in range(12):
        order = spans[:]
        rng.shuffle(order)
        ops = [('span', c, a, b) for c, a, b in order]
        oracle_view, projector_view = run_scenario('s10', ops)  # oracle equality, per order
        # Window IDs and redirect tombstones are deliberately delivery-order
        # dependent (displaced-id rule, same as today); placement, membership
        # and window shapes must not be.
        stripped = normalize(projector_view)
        for w in stripped['windows']:
            w.pop('id')
        stripped['membership'] = {}
        stripped['redirects'] = {}
        shapes.append(stripped)
    assert all(s == shapes[0] for s in shapes), 'projector placement changed with delivery order'


def test_s11_fence_block_extends_automatic_window():
    """A discard-frozen gap fence blocks the canonical path; choose() then picks
    the AUTOMATIC window, which today extends in place (grown override), and a
    later span extends it again (id stable, no redirect)."""
    ops = [
        ('span', 'cd', 2900, 2935),
        ('discard', 'cd'),  # frozen gap window at (2900,2900)
        ('span', 'ca', 4800, 4860),  # canonical window (fence 1900s away: unblocked)
        ('span', 'cx', 4100, 4160),  # blocked by fence; automatic window is closer -> extend
    ]
    oracle_view, projector_view = run_scenario('s11-extend', ops)
    grown = next(w for w in projector_view['windows'] if 'ca' in w['conversation_ids'])
    assert (grown['started_at'], grown['last_activity_at'], grown['conversation_ids']) == (
        S(4100),
        S(4860),
        ['ca', 'cx'],
    )

    ops2 = ops + [('span', 'cy', 4900, 4960)]  # still fence-connected at the envelope: extends again
    oracle_view2, projector_view2 = run_scenario('s11-extend2', ops2)
    grown2 = next(w for w in projector_view2['windows'] if 'ca' in w['conversation_ids'])
    assert (grown2['started_at'], grown2['last_activity_at']) == (S(4100), S(4960))
    assert projector_view2['membership']['cy'] == grown2['id']


def test_s12_discard_position_is_deterministic_per_log():
    """Discard before vs after a sibling: both orders must match today's path
    in THAT order (each is a different, deterministic state)."""
    for ops in [
        [('span', 'c0', 0, 20), ('discard', 'c0'), ('span', 'c1', 30, 60)],
        [('span', 'c0', 0, 20), ('span', 'c1', 30, 60), ('discard', 'c0')],
    ]:
        run_scenario('s12', ops)


def test_s13_double_replay_is_identical():
    log = FactLog()
    for c, a, b in [('c0', 0, 20), ('c1', 30, 60), ('c2', 120, 180)]:
        log.span(UID, c, S(a), S(b), 'omi')
    log.discarded(UID, 'c1')
    log.span(UID, 'c3', S(3600), S(3660), 'omi')
    first = replay(UID, log.facts(UID))
    second = replay(UID, log.facts(UID))
    assert normalize(first) == normalize(second)


def test_growing_repeat_span_reaches_fixed_fence_like_legacy():
    run_scenario(
        'growth-fence',
        [('span', 'f', 2900, 2935), ('discard', 'f'), ('span', 'a', 4800, 4860), ('span', 'a', 4100, 4860)],
    )


def test_discard_after_repoint_does_not_duplicate_the_window():
    run_scenario('repoint-discard', [('span', 'a', 0, 60), ('repoint', 'a', 'b'), ('discard', 'b')])


def test_fixed_extension_stamps_end_and_rejects_zero_progress():
    from utils.episodes.log.projector import ProjectedEpisode

    row = ProjectedEpisode(id='e', started_at=S(0), last_activity_at=S(60), close_reason='gap', fixed=False)
    assert row.extend('c', S(30), S(200), 'omi', [S(100)]) == 'attached'
    assert row.close_reason == 'boundary' and row.fixed and row.recorded_end == S(100)
    assert row.extend('tail', S(100), S(120), 'omi', []) == 'no_progress'
    assert 'tail' not in row.conversation_ids
    capped = ProjectedEpisode(id='cap', started_at=S(0), last_activity_at=S(60), close_reason='gap', fixed=False)
    assert capped.extend('long', S(30), S(15000), 'omi', []) == 'attached'
    assert capped.recorded_end == S(14400) and capped.close_reason == 'hard_cap' and not capped.fixed
