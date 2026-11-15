"""Variant F refusal telemetry preserves the pre-instrumentation gate and its read budget."""

import ast
import random
from pathlib import Path
from collections.abc import Mapping
from datetime import timedelta
from itertools import combinations
from typing import Any

import pytest
from prometheus_client import REGISTRY

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

# Existing F-join fixtures/helpers are shared test seams; pytest resolves fixture names implicitly.
from tests.unit.test_episode_f_join import (
    UID,
    T0,
    FIRST,
    SECOND,
    _env as _env,  # pyright: ignore[reportPrivateUsage]
    store as store,
    _c,  # pyright: ignore[reportPrivateUsage]
    _store_row,  # pyright: ignore[reportPrivateUsage]
    _first_episode,  # pyright: ignore[reportPrivateUsage]
)
from utils.episodes import f_join, metrics, policy


# Frozen predicate from fcd29a74: an independent oracle for this metrics-only change.
def _original_gate(uid: str, row: Mapping[str, Any]) -> bool:
    """The privacy gate for any conversation whose speech F may send to Jev, as predecessor or candidate.

    Fail-closed: a missing required field is not permission (``is_locked`` and ``discarded`` must be False).
    """
    # Reuse the episode composer/build visibility predicates. Missing required processing metadata
    # is unknown, not permission; optional tombstone/redirect fields retain their schema defaults.
    if row.get('owner_uid', uid) != uid or row.get('uid', uid) != uid:
        return False
    if row.get('data_protection_level') not in {'standard', 'enhanced'}:
        return False
    # Private cloud sync is the user's retention consent. Only an explicit True permits speech to reach Jev;
    # an absent or false value keeps today's join (the same explicit-opt-in rule as the batch attach gate).
    if row.get('private_cloud_sync_enabled') is not True:
        return False
    if row.get('is_locked') is not False or row.get('discarded') is not False:
        return False
    if any(row.get(key, False) is not False for key in ('deleted', 'deferred', 'processing_deferred')):
        return False
    if row.get('status') not in {'completed', 'processing', 'in_progress'}:
        return False
    if (
        row.get('processing_state') == 'local_pending'
        or row.get('terminal_no_derived_effects')
        or row.get('client_processing')
    ):
        return False
    if row.get('summary_blocked_reason') == 'local_only':
        return False
    hold = row.get(f_join.HOLD_FIELD, {})
    if not isinstance(hold, Mapping) or hold.get('held', False) is not False:
        return False
    return not f_join.hidden_member(dict(row)) and f_join.conversations_db.is_visible_conversation(row)


def _sample(name: str, **labels: str) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    assert value is not None
    return value


REFUSALS = [
    ('owner', {'owner_uid': 'someone-else'}),
    ('owner', {'uid': 'someone-else'}),
    ('row_consent', {'data_protection_level': 'private'}),
    ('row_consent', {'private_cloud_sync_enabled': False}),
    ('locked_discarded', {'is_locked': True}),
    ('locked_discarded', {'discarded': True}),
    ('deferred', {'deleted': True}),
    ('deferred', {'deferred': True}),
    ('deferred', {'processing_deferred': True}),
    ('status', {'status': 'failed'}),
    ('local_pending', {'processing_state': 'local_pending'}),
    ('other', {'terminal_no_derived_effects': True}),
    ('client_processing', {'client_processing': {'state': 'pending'}}),
    ('local_only', {'summary_blocked_reason': 'local_only'}),
    ('held', {f_join.HOLD_FIELD: {'held': True}}),
    ('held', {f_join.HOLD_FIELD: None}),
    ('hidden', {'sync_merged_into': 'survivor'}),
    ('hidden', {'dream_duplicate_of': 'survivor'}),
    ('user_consent', {}),
]


@pytest.mark.parametrize('supplied_row', [False, True], ids=['snapshot', 'supplied'])
@pytest.mark.parametrize('reason,change', REFUSALS)
def test_refusal_counts_only_first_reason_and_keeps_join_without_extra_reads(
    store, monkeypatch, reason, change, supplied_row
):
    first = _first_episode(store)
    assert first is not None
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    row.update(change)
    if reason == 'user_consent':
        store.rows[('users', UID)]['private_cloud_sync_enabled'] = False
    expected_allowed = reason == 'user_consent'
    assert _original_gate(UID, row) == f_join.may_feed_llm(UID, row) == expected_allowed
    assert f_join.gate_refusal_reason(UID, row) == (None if expected_allowed else reason)
    reads = []
    original_get = StrictFirestoreDocument.get

    def get(ref, *a, **kw):
        reads.append(ref.path)
        return original_get(ref, *a, **kw)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    before = {r: _sample('omi_episode_f_gate_total', reason=r) for r in metrics.F_GATE_REASONS}
    boundary_before = _sample('omi_episode_boundary_total', outcome='f_no_answer')
    decision = f_join.settle(
        UID,
        first,
        'c2',
        {'previous': 'c1', 'gap_seconds': 720},
        [],
        _c(store, minutes=13, ask=lambda *a, **kw: pytest.fail('refused speech reached Jev')),
        started_at=T0 + timedelta(minutes=12),
        candidate_row=row if supplied_row else None,
    )
    assert decision == policy.Boundary(policy.CONTINUE, gap_seconds=720, source_changed=False)
    assert _sample('omi_episode_boundary_total', outcome='f_no_answer') == boundary_before + 1
    assert {r: _sample('omi_episode_f_gate_total', reason=r) - before[r] for r in before} == {
        r: int(r == reason) for r in before
    }
    expected_reads: list[tuple[str, ...]] = [('users', UID, 'conversations', 'c1')]
    if not supplied_row:
        expected_reads.append(('users', UID, 'conversations', 'c2'))
    if reason == 'user_consent':
        expected_reads.append(('users', UID))
    assert reads == expected_reads


def test_refusal_reason_is_none_exactly_when_original_gate_allows(store):
    _store_row(store, 'c1', FIRST, minutes=0)
    base = store.rows[('users', UID, 'conversations', 'c1')]
    values = [None, False, True, 0, 1, '', 'false', [], {}, {'held': False}, {'held': None}]
    fields = {
        'owner_uid': [UID, 'other'],
        'uid': [UID, 'other'],
        'data_protection_level': ['standard', 'enhanced', 'private'],
        'private_cloud_sync_enabled': [],
        'is_locked': [],
        'discarded': [],
        'deleted': [],
        'deferred': [],
        'processing_deferred': [],
        'status': ['completed', 'processing', 'in_progress', 'failed'],
        'processing_state': ['local_pending'],
        'terminal_no_derived_effects': [],
        'client_processing': [],
        'summary_blocked_reason': ['local_only'],
        f_join.HOLD_FIELD: [{'held': True}, {'held': False}, {}],
        'sync_merged_into': ['survivor'],
        'dream_duplicate_of': ['survivor'],
    }
    rows = [dict(base), {}]
    for field, specific in fields.items():
        missing = dict(base)
        missing.pop(field, None)
        rows.append(missing)
        for value in values + specific:
            row = dict(base)
            row[field] = value
            # Membership in the original set predicates requires hashable metadata.
            if field in {'data_protection_level', 'status'} and isinstance(value, (dict, list)):
                continue
            rows.append(row)
    # Check first-failure precedence whenever two independent refusal conditions coexist.
    for (_, left), (_, right) in combinations(REFUSALS, 2):
        if not left or not right:
            continue
        row = dict(base, **left, **{k: v for k, v in right.items() if k not in left})
        assert f_join.gate_refusal_reason(UID, row) == f_join.gate_refusal_reason(UID, dict(base, **left))
        rows.append(row)
    rng = random.Random(20261110)
    for _ in range(2000):
        row = dict(base)
        for field in rng.sample(list(fields), rng.randrange(1, 6)):
            choices = values + fields[field]
            if field in {'data_protection_level', 'status'}:
                choices = [v for v in choices if not isinstance(v, (dict, list))]
            row[field] = rng.choice(choices)
        rows.append(row)
    for row in rows:
        allowed = _original_gate(UID, row)
        reason = f_join.gate_refusal_reason(UID, row)
        assert (reason is None) == f_join.may_feed_llm(UID, row) == allowed, row
        assert reason is None or reason in metrics.F_GATE_REASONS


@pytest.mark.parametrize('outcome', ['allowed', 'missing_candidate', 'gate_error', 'empty_previous'])
def test_only_gate_refusals_increment_the_new_counter(store, monkeypatch, outcome):
    first = _first_episode(store)
    assert first is not None
    _store_row(store, 'c2', SECOND, minutes=12)
    if outcome == 'missing_candidate':
        del store.rows[('users', UID, 'conversations', 'c2')]
    elif outcome == 'gate_error':

        def broken(*a, **kw):
            raise RuntimeError('read failed')

        monkeypatch.setattr(f_join, '_candidate_refusal_reason', broken)
    elif outcome == 'empty_previous':
        monkeypatch.setattr(f_join, 'previous_transcript', lambda *a, **kw: '')
    before = sum(_sample('omi_episode_f_gate_total', reason=r) for r in metrics.F_GATE_REASONS)
    f_join.settle(
        UID, first, 'c2', {'previous': 'c1'}, [], _c(store, minutes=13), started_at=T0 + timedelta(minutes=12)
    )
    after = sum(_sample('omi_episode_f_gate_total', reason=r) for r in metrics.F_GATE_REASONS)
    assert after - before == int(outcome == 'missing_candidate')


FALLBACK_SITES = {
    'pending_conflict': 'other',
    'pending_error': 'other',
    'synced_failed': 'other',
    'recheck_failed': 'other',
    'previous_failed': 'other',
    'gate_failed': 'other',
    'unknown_previous': 'unknown',
    'recheck_failed_settle': 'other',
    'unknown_jev': 'unknown',
}


def test_every_fallback_call_site_has_a_distinct_covered_label_and_unchanged_reason():
    tree = ast.parse(Path(f_join.__file__).read_text())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == '_fallback'
    ]
    sites = [next(ast.literal_eval(kw.value) for kw in node.keywords if kw.arg == 'site') for node in calls]
    assert len(sites) == len(set(sites)) == len(FALLBACK_SITES)
    assert {site: ast.literal_eval(node.args[0]) for site, node in zip(sites, calls)} == FALLBACK_SITES
    assert set(sites) | {'other'} == metrics.F_FALLBACK_SITES


@pytest.mark.parametrize('site,reason', FALLBACK_SITES.items())
def test_each_fallback_call_site_increments_exactly_its_own_label(store, monkeypatch, site, reason):
    first = _first_episode(store)
    assert first is not None
    _store_row(store, 'c2', SECOND, minutes=12)
    pending = {'previous': 'c1', 'gap_seconds': 720}
    c = _c(store, minutes=13)
    recorded = []
    original_fallback = f_join.record_fallback

    def record(**kwargs):
        recorded.append(kwargs)
        original_fallback(**kwargs)

    def broken(*a, **kw):
        raise RuntimeError('injected failure')

    monkeypatch.setattr(f_join, 'record_fallback', record)
    before = {s: _sample('omi_episode_f_fallback_total', site=s) for s in metrics.F_FALLBACK_SITES}
    if site in {'pending_conflict', 'pending_error'}:

        def fail_commit(*a, **kw):
            if site == 'pending_conflict':
                raise f_join.EpisodeConflict('injected conflict')
            raise RuntimeError('injected failure')

        monkeypatch.setattr(f_join.episodes_db, 'commit_moment', fail_commit)
        monkeypatch.setattr(f_join.episodes_db, 'get_episode', lambda *a, **kw: None)
        f_join.mark_pending(UID, first, first, 'c2', policy.Boundary(policy.ASK), {}, store)
    elif site == 'synced_failed':
        f_join.synced_failed(RuntimeError('injected failure'))
    elif site == 'recheck_failed':
        monkeypatch.setattr(f_join.episodes_db, 'get_episode_membership_snapshot', broken)
        # Exercise the private post-answer read failure at its owning test seam.
        assert not f_join._split_still_clear(UID, first, 'c2', T0, c)  # pyright: ignore[reportPrivateUsage]
    else:
        if site == 'previous_failed':
            monkeypatch.setattr(f_join, 'previous_transcript', broken)
        elif site == 'gate_failed':
            monkeypatch.setattr(f_join, '_candidate_refusal_reason', broken)
        elif site == 'unknown_previous':
            monkeypatch.setattr(f_join, 'previous_transcript', lambda *a, **kw: '')
        elif site == 'recheck_failed_settle':
            monkeypatch.setattr(f_join.episodes_db, 'get_episode_owner_snapshot', broken)
        decision = f_join.settle(
            UID,
            first,
            'c2',
            pending,
            [],
            c,
            started_at=T0 + timedelta(minutes=12),
            member=site != 'recheck_failed_settle',
        )
        assert decision == policy.Boundary(policy.CONTINUE, gap_seconds=720, source_changed=False)
    assert {s: _sample('omi_episode_f_fallback_total', site=s) - before[s] for s in before} == {
        s: int(s == site) for s in before
    }
    assert len(recorded) == 1
    assert recorded[0] == dict(
        component='episode_f_join',
        from_mode='jev_f',
        to_mode='time_join',
        reason=reason,
        outcome='degraded',
        log=f_join.logger,
    )
