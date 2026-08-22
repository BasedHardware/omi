"""Dual-backend contract for fair-use enforcement (ADR-0044 facade + ADR-0002 store port).

`database/fair_use.py` is the record of who has been caught abusing the service, what was done about
it, and how a person disputes it. Its one at-risk shape is the one that has to reach ACROSS USERS:

    collection_group   get_flagged_users sweeps every user's `fair_use_state` subcollection to build
                       the admin dashboard, and lookup_fair_use_event_by_case_ref sweeps every user's
                       `fair_use_events` to resolve a case reference. Both are cross-parent by nature:
                       neither caller knows the uid — finding it IS the query.

                       A parent the sweep misses is a throttled or restricted user who never appears
                       on the dashboard: nobody can see the enforcement, so nobody can lift it, and
                       the person stays degraded with no route back. A sweep that reaches too far is
                       the mirror image — a clean user shown as flagged, and an admin resetting an
                       account that never did anything.

                       The case-reference lookup is worse, because it is the PUBLIC unauthenticated
                       path: the case ref is the only thing the affected person holds. Fail to find
                       it and their appeal 404s. Reconstruct the wrong uid from the document path and
                       the status of somebody else's case is handed to them.

The rest of the module is per-user reads and writes — not ratcheted shapes, but they are what decides
whether somebody gets throttled, so they route through the same facade and are covered here too: the
merge-not-replace state write, the look-back windows that drive escalation, and the reset that has to
actually take a user off the dashboard.

Cross-user note: this suite queries collection groups that span the whole rig, which is SHARED. Every
assertion is therefore scoped to this run's uids (a subset check, never an equality on the whole
sweep), and the fixture deletes exactly what it created.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def enforcement(bind_store):
    """Four users: warning, throttle, restrict — and one clean. Distinct, ordered `updated_at`.

    The timestamps are seeded explicitly rather than left to ``datetime.now()``: Firestore keeps
    microseconds and BSON keeps milliseconds, so two state writes issued back to back can TIE on the
    Mongo leg and the ordering assertion would be deciding by luck.
    """
    run = uuid.uuid4().hex[:8]
    uids = [f'fu{index}-{run}' for index in range(4)]
    stages = ['warning', 'throttle', 'restrict', 'none']
    # newest first: fu1 (throttle), fu0 (warning), fu2 (restrict); fu3 is clean.
    stamps = [NOW - timedelta(hours=2), NOW - timedelta(hours=1), NOW - timedelta(hours=3), NOW - timedelta(hours=4)]
    paths: list[str] = []

    def _track(path: str) -> str:
        paths.append(path)
        return path

    for uid, stage, stamp in zip(uids, stages, stamps):
        bind_store.set(
            _track(f'users/{uid}/fair_use_state/current'),
            {'stage': stage, 'updated_at': stamp, 'violation_count_30d': 3, 'last_classifier_score': 0.9},
        )

    yield {'uids': uids, 'run': run, 'store': bind_store, 'track': _track}

    for path in paths:
        bind_store.delete(path)


def _mine(rows, uids):
    """The sweep restricted to this run — the rig is shared, so never assert on the whole result."""
    return [row for row in rows if row.get('uid') in set(uids)]


def _state(enforcement, uid):
    stored = enforcement['store'].get(f'users/{uid}/fair_use_state/current')
    return stored.data if stored is not None and stored.exists else None


# --- collection group: the admin dashboard ----------------------------------------------------------


def test_the_dashboard_finds_every_flagged_user_and_only_those(enforcement):
    """The `in` filter over the group. Three of the four users are under enforcement and one is clean.

    Miss a parent and a throttled user is invisible to the only screen that can lift the throttle.
    Reach too far and an admin is looking at somebody who never did anything."""
    import database.fair_use as fair_use_db

    found = _mine(fair_use_db.get_flagged_users(), enforcement['uids'])

    assert {row['uid'] for row in found} == set(enforcement['uids'][:3])
    assert enforcement['uids'][3] not in {row['uid'] for row in found}, 'a clean user is not flagged'


def test_the_row_names_the_user_it_came_from(enforcement):
    """The uid is not stored in the document — the module reconstructs it from the group hit's PATH
    (`users/{uid}/fair_use_state/current`). Get that wrong and every admin action on the dashboard
    lands on the wrong account."""
    import database.fair_use as fair_use_db

    (row,) = _mine(fair_use_db.get_flagged_users(stage_filter='restrict'), enforcement['uids'])

    assert row['uid'] == enforcement['uids'][2]
    assert row['id'] == 'current'
    assert row['stage'] == 'restrict'
    assert row['last_classifier_score'] == 0.9, 'the row carries the document, not just the pointer'


def test_filtering_by_stage_narrows_the_sweep(enforcement):
    """The dashboard's stage tabs. A filter that did not apply would show every enforcement level under
    the 'restricted' tab and an admin would act on the wrong severity."""
    import database.fair_use as fair_use_db

    throttled = _mine(fair_use_db.get_flagged_users(stage_filter='throttle'), enforcement['uids'])

    clean = _mine(fair_use_db.get_flagged_users(stage_filter='none'), enforcement['uids'])

    assert [row['uid'] for row in throttled] == [enforcement['uids'][1]]
    assert [row['uid'] for row in clean] == [enforcement['uids'][3]], 'an explicit filter can still ask for the clean'


def test_the_dashboard_is_ordered_by_most_recently_enforced(enforcement):
    """`order_by('updated_at', DESCENDING)` on a collection-group query — the ordering an admin triages
    by. Lose it and the newest enforcement sinks below months of old ones."""
    import database.fair_use as fair_use_db

    found = _mine(fair_use_db.get_flagged_users(), enforcement['uids'])

    assert [row['uid'] for row in found] == [
        enforcement['uids'][1],
        enforcement['uids'][0],
        enforcement['uids'][2],
    ]


def test_the_limit_bounds_the_sweep(enforcement):
    """A cross-parent sweep with no cap reads the whole deployment. Asserted as a length rather than an
    identity because the group spans the shared rig."""
    import database.fair_use as fair_use_db

    assert len(fair_use_db.get_flagged_users(limit=1)) == 1


def test_a_reset_user_leaves_the_dashboard(enforcement):
    """Where the write side and the sweep meet: a reset that stored the stage anywhere the group query
    cannot see would leave the user pinned on the dashboard forever."""
    import database.fair_use as fair_use_db

    fair_use_db.reset_fair_use_state(enforcement['uids'][1], admin_uid='admin-1')

    found = _mine(fair_use_db.get_flagged_users(), enforcement['uids'])
    assert enforcement['uids'][1] not in {row['uid'] for row in found}
    assert set(enforcement['uids'][:1] + enforcement['uids'][2:3]) == {row['uid'] for row in found}


# --- collection group: the public case-reference lookup ---------------------------------------------


@pytest.fixture
def cases(bind_store, enforcement):
    """One fair-use event per enforced user, created through the module so each gets a real case ref."""
    import database.fair_use as fair_use_db

    created = {}
    for uid in enforcement['uids'][:2]:
        event_id = fair_use_db.create_fair_use_event(uid, {'reason': 'burst', 'score': 0.91})
        path = enforcement['track'](f'users/{uid}/fair_use_events/{event_id}')
        stored = bind_store.get(path)
        created[uid] = {'event_id': event_id, 'case_ref': stored.data['case_ref']}

    return created


def test_a_case_reference_resolves_to_the_user_who_owns_it(cases, enforcement):
    """The public appeal path. The caller has a case ref and nothing else; the sweep is what turns it
    into a user. It must land on the SECOND user's account, not the first one found."""
    import database.fair_use as fair_use_db

    owner = enforcement['uids'][1]

    found = fair_use_db.lookup_fair_use_event_by_case_ref(cases[owner]['case_ref'])

    assert found is not None
    assert found['uid'] == owner
    assert found['event_id'] == cases[owner]['event_id']
    assert found['reason'] == 'burst', 'the event body comes back, not just the pointer'


def test_an_unknown_case_reference_resolves_to_nothing(cases, enforcement):
    """A mistyped reference must answer 'no such case', not the first event in the deployment."""
    import database.fair_use as fair_use_db

    assert fair_use_db.lookup_fair_use_event_by_case_ref(f"FU-NOSUCHCASE{enforcement['run'][:2].upper()}") is None


def test_two_users_events_do_not_collide_on_their_references(cases, enforcement):
    """Each event gets its own reference, and each reference resolves to its own owner — otherwise one
    person's appeal shows another person's case status."""
    import database.fair_use as fair_use_db

    first, second = enforcement['uids'][0], enforcement['uids'][1]
    assert cases[first]['case_ref'] != cases[second]['case_ref']

    assert fair_use_db.lookup_fair_use_event_by_case_ref(cases[first]['case_ref'])['uid'] == first
    assert fair_use_db.lookup_fair_use_event_by_case_ref(cases[second]['case_ref'])['uid'] == second


# --- the per-user record ----------------------------------------------------------------------------


@pytest.fixture
def history(bind_store, enforcement):
    """One user's violation history: yesterday, ten days ago, forty days ago."""
    uid = enforcement['uids'][0]
    ages = [1, 10, 40]
    ids = []
    for age in ages:
        event_id = f'ev{age}-{enforcement["run"]}'
        bind_store.set(
            enforcement['track'](f'users/{uid}/fair_use_events/{event_id}'),
            {
                'created_at': datetime.now(timezone.utc) - timedelta(days=age),
                'reason': f'{age}d ago',
                'resolved': False,
            },
        )
        ids.append(event_id)
    return {'uid': uid, 'ids': ids}


def test_the_lookback_windows_count_only_as_far_back_as_they_claim(history):
    """The numbers that decide escalation: 7 days and 30 days. A window that leaked would escalate a
    user to 'restrict' on violations they were already forgiven for."""
    import database.fair_use as fair_use_db

    assert fair_use_db.get_violation_counts(history['uid']) == {'violation_count_7d': 1, 'violation_count_30d': 2}


def test_a_users_events_come_back_newest_first(history):
    """The history an admin reads before deciding. Reversed, the oldest incident looks like the latest
    one and the decision is made on stale evidence."""
    import database.fair_use as fair_use_db

    found = fair_use_db.get_fair_use_events(history['uid'])

    assert [event['reason'] for event in found][:3] == ['1d ago', '10d ago', '40d ago']
    assert found[0]['id'] == history['ids'][0], 'the document id rides along for the resolve action'


def test_resolving_an_event_annotates_it_without_erasing_it(history):
    """An update, not a set. Overwrite the document and the evidence the decision was based on is gone
    — the audit trail is the whole point of keeping the event."""
    import database.fair_use as fair_use_db

    fair_use_db.resolve_fair_use_event(history['uid'], history['ids'][1], 'admin-1', notes='false positive')

    found = {event['id']: event for event in fair_use_db.get_fair_use_events(history['uid'])}
    resolved = found[history['ids'][1]]
    assert resolved['resolved'] is True
    assert resolved['resolved_by'] == 'admin-1'
    assert resolved['admin_notes'] == 'false positive'
    assert resolved['reason'] == '10d ago', 'the original evidence must survive the annotation'


def test_a_state_write_merges_instead_of_replacing(enforcement):
    """`set(..., merge=True)`. The stage, the counts and the throttle deadline are written by different
    code paths at different times; a non-merging write would drop whichever one it did not carry — a
    throttle that silently expires, or a violation count reset to nothing."""
    import database.fair_use as fair_use_db

    uid = enforcement['uids'][3]
    fair_use_db.update_fair_use_state(uid, {'throttle_until': NOW + timedelta(hours=6)})
    fair_use_db.set_fair_use_stage(uid, 'throttle', violation_count_7d=2)

    state = _state(enforcement, uid)
    assert state['stage'] == 'throttle'
    assert state['violation_count_7d'] == 2
    assert state['throttle_until'] is not None, 'the earlier write must survive the later one'
    assert state['violation_count_30d'] == 3, 'and so must the field neither write mentioned'


def test_a_state_write_stamps_when_it_happened(enforcement):
    """`updated_at` is what the dashboard orders by, so a write that does not stamp it sinks the user
    out of the admin's view even though the enforcement just changed."""
    import database.fair_use as fair_use_db

    uid = enforcement['uids'][3]
    before = _state(enforcement, uid)['updated_at']

    fair_use_db.set_fair_use_stage(uid, 'warning')

    assert _state(enforcement, uid)['updated_at'] > before


def test_reading_the_state_of_a_user_who_has_none_is_empty_not_missing(enforcement):
    """Every request path checks the state first. Raising instead of answering `{}` would fail the
    request for anybody who has never been flagged, which is nearly everybody."""
    import database.fair_use as fair_use_db

    assert fair_use_db.get_fair_use_state(f"fu-never-{enforcement['run']}") == {}


def test_a_reset_clears_the_counters_and_records_who_did_it(enforcement):
    """An admin lifting an enforcement. Leave a counter behind and the next single violation escalates
    the user straight back to where they were."""
    import database.fair_use as fair_use_db

    uid = enforcement['uids'][2]

    fair_use_db.reset_fair_use_state(uid, admin_uid='admin-7')

    state = _state(enforcement, uid)
    assert state['stage'] == 'none'
    assert state['violation_count_7d'] == 0 and state['violation_count_30d'] == 0
    assert state['throttle_until'] is None and state['restrict_until'] is None
    assert state['reset_by'] == 'admin-7'
