"""Restore redrive: a held record unit re-enters projection only when its target returns.

The quarantined receipt is replay-fenced, so the reset is a deliberate
transaction: it must refuse everything except a genuinely restorable record
target, clear the held disposition without touching audio, and stamp
``projection_redriven_at`` so the re-assignment cannot drag the owner
watermark backward onto already-terminal rows.
"""

from dataclasses import asdict
from unittest.mock import Mock

import pytest

from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_release import ProjectionReleaseStore, release_page, release_page_settled
from database.batch_pipeline_store import FirestoreStore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.scheduler import owner_key

OWNER = 'synthetic-owner'
TARGET = 'rec-target'
BINDING = ProjectionBinding(OWNER, 'bp_upload', 'content', ('held',), target_conversation_id=TARGET, record_origin=True)


@pytest.fixture(autouse=True)
def runtime_stage(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_COHORT', raising=False)
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')


def rows(*, discarded=False, target_missing=False, **result_extra):
    conversation = (
        {}
        if target_missing
        else {
            'record_lane_owner': 'batch_sync_v1',
            'status': 'completed',
            **({'discarded': True} if discarded else {}),
        }
    )
    seeded = {
        ('users', OWNER): {},
        ('users', OWNER, 'conversations', TARGET): conversation,
        ('batch_pipeline_prod_jobs', 'held'): {
            'owner_id': OWNER,
            'projection_binding': asdict(BINDING),
            'recovery_state': 'held',
            'audio_uri': 'gs://synthetic/audio',
        },
        ('batch_pipeline_prod_results', 'held'): {
            'segment_id': 'held',
            'owner_key': owner_key(OWNER),
            'projection_state': 'quarantine_held',
            'protocol_version': 2,
            'lineage_quarantine_version': 1,
            'projection': {
                'state': 'quarantined',
                'disposition': 'ambiguous_generation',
                'quarantine_version': 1,
                'held_speech_seconds': 3.0,
            },
            **result_extra,
        },
        ('batch_pipeline_prod_owners', owner_key(OWNER)): {'projection_watermark': 'later-row'},
    }
    return seeded


def store_for(seeded):
    client = StrictFirestore(seeded)
    store = FirestoreStore('batch_pipeline_prod', firestore_client=client)
    return client, ProjectionStore(store)


def test_release_refuses_still_discarded_target():
    client, store = store_for(rows(discarded=True))
    assert ProjectionReleaseStore(store).release('held', 500.0) is False
    result = client.rows[('batch_pipeline_prod_results', 'held')]
    job = client.rows[('batch_pipeline_prod_jobs', 'held')]
    assert result['projection_state'] == 'quarantine_held'
    assert result['projection']['state'] == 'quarantined'
    assert job['recovery_state'] == 'held'


def test_release_resets_held_unit_when_target_restored():
    client, store = store_for(rows(projection_blocked_since=100.0, projection_block_type='ValueError'))
    assert ProjectionReleaseStore(store).release('held', 500.0) is True
    result = client.rows[('batch_pipeline_prod_results', 'held')]
    job = client.rows[('batch_pipeline_prod_jobs', 'held')]
    assert result['projection_state'] == 'pending'
    assert result['projection_redriven_at'] == 500.0
    assert result['projection'] == {}
    assert result['projection_blocked_since'] is None
    assert result['projection_block_type'] is None
    assert result['lineage_quarantine_version'] == 0
    assert result['protocol_version'] == 2
    assert result['projection_release_version'] == 1
    assert job['recovery_state'] is None
    # Audio is never touched by the reset.
    assert job['audio_uri'] == 'gs://synthetic/audio'
    # The owner watermark stays where the chain already is.
    assert client.rows[('batch_pipeline_prod_owners', owner_key(OWNER))]['projection_watermark'] == 'later-row'


@pytest.mark.parametrize(
    'mutation',
    [
        lambda seeded: seeded.pop(('users', OWNER, 'conversations', TARGET)),
        lambda seeded: seeded[('batch_pipeline_prod_jobs', 'held')].pop('recovery_state'),
        lambda seeded: seeded[('batch_pipeline_prod_results', 'held')].update(projection_state='pending'),
        lambda seeded: seeded[('batch_pipeline_prod_results', 'held')].update(projection={'state': 'ready'}),
        lambda seeded: seeded[('batch_pipeline_prod_results', 'held')].update(projection_release_attempts=3),
        lambda seeded: seeded[('users', OWNER, 'conversations', TARGET)].update(status='processing'),
        lambda seeded: seeded[('users', OWNER, 'conversations', TARGET)].update(deleted=True),
    ],
)
def test_release_refuses_everything_but_a_restored_held_record_unit(mutation):
    seeded = rows()
    mutation(seeded)
    client, store = store_for(seeded)
    assert ProjectionReleaseStore(store).release('held', 500.0) is False
    result = client.rows[('batch_pipeline_prod_results', 'held')]
    # No reset side effects: the held receipt survives untouched.
    assert result.get('projection', {}).get('state') in {'quarantined', 'ready'}
    assert result.get('projection_redriven_at') in (None, 499.0)


def test_release_is_idempotent_after_one_reset():
    client, store = store_for(rows())
    release = ProjectionReleaseStore(store)
    assert release.release('held', 500.0) is True
    assert release.release('held', 501.0) is False
    assert client.rows[('batch_pipeline_prod_results', 'held')]['projection_redriven_at'] == 500.0


def test_release_page_releases_only_restorable_rows_and_wraps(monkeypatch):
    from database.batch_pipeline_projection_release import held_page_ids

    client, store = store_for(rows())
    page = ['stale-legacy', 'held', 'still-discarded']
    monkeypatch.setattr(
        'database.batch_pipeline_projection_release.held_page_ids',
        lambda *args, **kwargs: list(page),
    )
    counts, next_after = release_page(store, limit=3, after_id=None, now=500.0)
    assert counts['examined'] == 3
    assert counts['released'] == 1
    assert counts['waiting'] == 2
    assert counts['error'] == 0
    assert next_after == 'still-discarded'
    # A short page wraps the cursor for the next pass.
    monkeypatch.setattr(
        'database.batch_pipeline_projection_release.held_page_ids',
        lambda *args, **kwargs: ['one'],
    )
    counts, next_after = release_page(store, limit=3, after_id='x', now=500.0)
    assert next_after is None


def test_redriven_reassignment_does_not_regress_the_watermark():
    """The fake-session mirror of ProjectionSession.persist's guard: a released
    unit behind the watermark persists its receipt without moving the chain."""
    from tests.unit.test_batch_pipeline_owner_chain_projection import BURST, ResultLog, projector_for

    log = ResultLog()
    ids = [f'd-{n}' for n in range(2)]
    for sid in ids:
        log.commit(BURST, 'd', sid, ids)
    projector = projector_for(log)
    projector.project_owner(BURST)
    assert log.projection_watermark(owner_key(BURST)) == ids[-1]
    # A released held row behind the watermark re-assigns.
    log.results[ids[0]]['projection_redriven_at'] = 123.0
    log.results[ids[0]].pop('projection')
    log.results[ids[0]]['projection_state'] = 'pending'
    log.session(ids[0], log.bindings[ids[0]], 124.0).persist_empty()
    assert log.results[ids[0]]['projection']['state'] == 'persisted'
    assert log.projection_watermark(owner_key(BURST)) == ids[-1]


def test_held_page_query_is_bounded_and_keyset():
    from database.batch_pipeline_projection_release import held_page_ids

    def fresh_client():
        query = Mock()
        query.stream.return_value = iter([])
        query.order_by.return_value = query
        query.limit.return_value = query
        query.start_after.return_value = query
        collection = Mock()
        collection.where.return_value = query
        collection.document.return_value = 'cursor-doc'
        client = Mock()
        client.collection.return_value = collection
        return client, collection, query

    client, collection, _ = fresh_client()
    assert held_page_ids(client, 'ns', 5, None) == []
    client.collection.assert_called_once_with('ns_results')
    collection.where.assert_called_once_with('projection_state', '==', 'quarantine_held')

    client, _, query = fresh_client()
    assert held_page_ids(client, 'ns', 5, 'after') == []
    query.start_after.assert_called_once_with({'__name__': 'cursor-doc'})


def _scanner(store):
    from types import SimpleNamespace

    from utils.batch_pipeline.projection import Projector

    scanner = SimpleNamespace(store=store, clock=lambda: 500.0, release_after=None)
    return lambda limit: Projector.release_held_scan(scanner, limit=limit)


def test_release_scan_resumes_from_the_durable_cursor_after_an_instance_restart(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'false')
    # Prod 11-02: an in-memory cursor restarted at page one on every instance
    # start, so 8 of 10 deciles of 16,932 held rows were never examined.
    import database.batch_pipeline_projection_release as release

    order = [f'held-{n:02d}' for n in range(6)]
    seen = []

    def page(_client, _namespace, limit, after_id):
        start = order.index(after_id) + 1 if after_id else 0
        seen.append(after_id)
        return order[start : start + limit]

    monkeypatch.setattr(release, 'held_page_ids', page)
    monkeypatch.setattr(release.ProjectionReleaseStore, 'release', lambda *a: False)
    _, store = store_for(rows())
    _scanner(store)(2)
    _scanner(store)(2)  # a fresh instance
    _scanner(store)(2)
    assert seen == [None, 'held-01', 'held-03']
    # The empty page past the end wraps: the next instance starts from the top.
    _scanner(store)(2)
    _scanner(store)(2)
    assert seen[-2:] == ['held-05', None]


def test_release_scan_cursor_failures_never_stop_the_scan(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'false')
    import database.batch_pipeline_projection_release as release

    monkeypatch.setattr(release, 'held_page_ids', lambda *a: ['held'])
    monkeypatch.setattr(release.ProjectionReleaseStore, 'release', lambda *a: False)
    broken = Mock()
    broken.ref.side_effect = RuntimeError('synthetic')
    broken.run.side_effect = RuntimeError('synthetic')
    assert _scanner(broken)(1)['examined'] == 1


@pytest.mark.parametrize('summary', ['quarantined', 'persisted'])
@pytest.mark.parametrize('blocked', [None, 'target', 'attempts', 'privacy', 'operator'])
def test_persisted_multipart_release_preserves_proven_suffix(monkeypatch, summary, blocked):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'true')
    held_part = {'state': 'quarantined', 'disposition': 'ambiguous_generation'}
    suffix = {'state': 'persisted', 'conversation_id': 'proven-suffix', 'audio_required': True}
    seeded = rows(
        projection_state='persisted',
        projection={'state': summary, **({'disposition': 'ambiguous_generation'} if summary == 'quarantined' else {})},
        projection_parts={'0': held_part, '1': suffix},
    )
    if blocked == 'target':
        seeded[('users', OWNER, 'conversations', TARGET)]['discarded'] = True
    elif blocked == 'attempts':
        seeded[('batch_pipeline_prod_results', 'held')]['projection_release_attempts'] = 3
    elif blocked == 'privacy':
        seeded[('batch_pipeline_prod_results', 'held')]['projection_privacy_refusal'] = True
    elif blocked == 'operator':
        from database.batch_pipeline_projection import OPERATOR_INTENTS

        seeded[('batch_pipeline_prod_jobs', 'held')][next(iter(OPERATOR_INTENTS))] = {'state': 'pending'}
    client, store = store_for(seeded)
    assert ProjectionReleaseStore(store).release('held', 500.0) is (blocked is None)
    if blocked:
        assert client.rows == seeded
    else:
        result = client.rows[('batch_pipeline_prod_results', 'held')]
        assert result['projection_state'] == 'pending'
        assert result['projection_parts'] == {'1': suffix}
        assert result['projection_release_attempts'] == 1
        assert client.rows[('batch_pipeline_prod_jobs', 'held')]['recovery_state'] is None


def test_persisted_release_requires_ambiguous_quarantine_and_enabled_recovery(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'true')
    for receipt in ({'state': 'ready'}, {'state': 'quarantined', 'disposition': 'other'}):
        client, store = store_for(rows(projection_state='persisted', projection=receipt))
        assert not ProjectionReleaseStore(store).release('held', 500.0)
        assert not client.transactions[-1].updates
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'false')
    client, store = store_for(rows(projection_state='persisted'))
    assert not ProjectionReleaseStore(store).release('held', 500.0)
    assert not client.transactions[-1].updates


def test_recovery_off_refuses_ready_summary_with_ambiguous_quarantined_part(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'false')
    seeded = rows(
        projection={'state': 'ready'},
        projection_parts={'0': {'state': 'quarantined', 'disposition': 'ambiguous_generation'}},
    )
    client, store = store_for(seeded)
    assert not ProjectionReleaseStore(store).release('held', 500.0)
    assert client.rows == seeded
    assert not client.transactions[-1].updates


def test_recovery_off_releases_former_summary_shape(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'false')
    client, store = store_for(rows())
    assert ProjectionReleaseStore(store).release('held', 500.0)
    result = client.rows[('batch_pipeline_prod_results', 'held')]
    assert result['projection_state'] == 'pending'
    assert result['protocol_version'] == 1
    assert 'projection_release_version' not in result
    assert client.rows[('batch_pipeline_prod_jobs', 'held')]['recovery_state'] is None


def test_assignment_held_query_is_bounded_and_keyset():
    from database.batch_pipeline_projection_release import assignment_held_page_ids, RELEASE_PAGE

    query = Mock()
    for name in ('where', 'order_by', 'limit', 'start_after'):
        getattr(query, name).return_value = query
    query.stream.return_value = []
    client = Mock()
    client.collection.return_value = query
    assert assignment_held_page_ids(client, 'ns', 999, 'after') == []
    client.collection.assert_called_once_with('ns_jobs')
    assert query.where.call_args_list == [
        (('state', '==', 'committed'),),
        (('recovery_state', '==', 'held'),),
    ]
    query.order_by.assert_called_once_with('__name__')
    query.limit.assert_called_once_with(RELEASE_PAGE)
    query.start_after.assert_called_once_with({'__name__': query.document.return_value})


def test_assignment_scan_reaches_persisted_held_job(monkeypatch):
    import database.batch_pipeline_projection_release as release

    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'true')
    client, store = store_for(rows(projection_state='persisted'))
    client.rows[('batch_pipeline_prod_jobs', 'held')]['state'] = 'committed'
    monkeypatch.setattr(release, 'held_page_ids', lambda *a: [])
    monkeypatch.setattr(release, 'assignment_held_page_ids', lambda *a: ['held'])
    counts, _ = release.release_scan_pass(store, limit=2, after_id=None, now=500.0)
    assert {key: counts[key] for key in ('released', 'waiting', 'error', 'examined', 'expired')} == {
        'released': 1,
        'waiting': 0,
        'error': 0,
        'examined': 1,
        'expired': 0,
    }
    assert client.rows[('batch_pipeline_prod_results', 'held')]['projection_state'] == 'pending'


def test_two_cursors_resume_and_wrap_independently_with_one_row_budget(monkeypatch):
    import database.batch_pipeline_projection_release as release

    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'true')
    seen = []

    def page(leg):
        def fetch(_client, _ns, limit, after):
            seen.append((leg, after))
            return [] if after else [leg]

        return fetch

    monkeypatch.setattr(release, 'held_page_ids', page('result'))
    monkeypatch.setattr(release, 'assignment_held_page_ids', page('job'))
    monkeypatch.setattr(release.ProjectionReleaseStore, 'release', lambda *a: False)
    _, store = store_for(rows())
    for _ in range(6):
        assert _scanner(store)(1)['examined'] <= 1
    assert seen == [
        ('result', None),
        ('job', None),
        ('result', 'result'),
        ('job', 'job'),
        ('result', None),
        ('job', None),
    ]


def test_scan_shares_page_and_deadline_budgets(monkeypatch):
    import database.batch_pipeline_projection_release as release

    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'true')
    clock = [0.0]
    monkeypatch.setattr(release.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(release, 'held_page_ids', lambda *a: ['r1', 'r2', 'r3', 'r4'][: a[2]])
    monkeypatch.setattr(release, 'assignment_held_page_ids', lambda *a: ['j1', 'j2', 'j3', 'j4'][: a[2]])
    seen = []

    def attempt(_store, segment_id, _now):
        seen.append(segment_id)
        clock[0] += 1
        return False

    monkeypatch.setattr(release.ProjectionReleaseStore, 'release', attempt)
    client, store = store_for(rows())
    counts, after = release.release_scan_pass(store, limit=8, after_id=None, now=500, deadline=3)
    assert counts['examined'] == 3
    assert seen == ['r1', 'r2', 'j1']
    assert after == 'r2'
    assert client.rows[('batch_pipeline_prod_control', release.ASSIGNMENT_RELEASE_CURSOR_KEY)]['after_id'] == 'j1'
    counts, _ = release.release_scan_pass(store, limit=8, after_id=None, now=500, deadline=3)
    assert counts['examined'] == 0


def test_assignment_cursor_disabled_by_existing_kill_switch(monkeypatch):
    import database.batch_pipeline_projection_release as release

    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'false')
    monkeypatch.setattr(release, 'held_page_ids', lambda *a: ['held'])
    fetch = Mock(side_effect=AssertionError('assignment scan disabled'))
    monkeypatch.setattr(release, 'assignment_held_page_ids', fetch)
    _, store = store_for(rows())
    assert _scanner(store)(1)['released'] == 1
    fetch.assert_not_called()


GHOST_FLAG = 'BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED'
GHOST_NOW = 40 * 86400.0
RESULT_KEY = ('batch_pipeline_prod_results', 'held')
JOB_KEY = ('batch_pipeline_prod_jobs', 'held')


def ghost_rows(*, age=86400, recovery=None):
    seeded = rows(projection={'state': 'ready'}, committed_at=GHOST_NOW - age)
    seeded[JOB_KEY].update(state='committed', recovery_state=recovery)
    return seeded


@pytest.mark.parametrize('mode', ['shadow', 'serve'])
@pytest.mark.parametrize(
    'raw,enabled',
    [(None, False), ('false', False), ('off', False), ('1', False), ('bad', False), ('', False), (' TRUE ', True)],
)
def test_ghost_flag_is_strict_opt_in_in_every_parser_mode(monkeypatch, mode, raw, enabled):
    from config.batch_pipeline import projection_ghost_settle_enabled

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    if raw is None:
        monkeypatch.delenv(GHOST_FLAG, raising=False)
    else:
        monkeypatch.setenv(GHOST_FLAG, raw)
    assert projection_ghost_settle_enabled() is enabled


@pytest.mark.parametrize('recovery', [None, 'recovered'])
@pytest.mark.parametrize('enabled', [False, True])
def test_ghost_repair_is_hint_only_and_reads_target_only_when_enabled(monkeypatch, recovery, enabled):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

    monkeypatch.setenv(GHOST_FLAG, str(enabled).lower())
    seeded = ghost_rows(recovery=recovery)
    client, store = store_for(seeded)
    read_paths = []
    original = StrictFirestoreDocument.get

    def get(ref, *args, **kwargs):
        read_paths.append(ref.path)
        return original(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    release = ProjectionReleaseStore(store)
    assert release.release('held', GHOST_NOW) is False
    assert release.ghost_settled is enabled
    assert release.ghost_skip == (None if enabled else 'count_only')
    assert read_paths == [JOB_KEY, RESULT_KEY] + ([('users', OWNER, 'conversations', TARGET)] if enabled else [])
    assert client.rows == {
        **seeded,
        RESULT_KEY: {
            **seeded[RESULT_KEY],
            **({'projection_state': 'ready', 'ghost_settled_cohort': 'g1'} if enabled else {}),
        },
    }
    assert client.transactions[-1].updates == (
        [(RESULT_KEY, {'projection_state': 'ready', 'ghost_settled_cohort': 'g1'})] if enabled else []
    )
    if enabled:
        assert not release.release('held', GHOST_NOW + 1)
        assert not release.ghost_settled and release.ghost_skip == 'hint_changed'


@pytest.mark.parametrize(
    'kind,changes,expected',
    [
        ('result', {'projection_state': 'persisted'}, 'hint_changed'),
        ('result', {'projection': {'state': 'persisted'}}, 'receipt_not_ready'),
        ('result', {'projection_parts': {'0': {'state': 'quarantined'}}}, 'part_quarantined'),
        ('target', None, 'target_not_restorable'),
        ('target', {'deleted': True}, 'target_not_restorable'),
        ('target', {'discarded': True}, 'target_not_restorable'),
        ('target', {'status': 'in_progress'}, 'target_not_restorable'),
        ('target', {'status': 'processing'}, 'target_not_restorable'),
        ('target', {'uses_custom_stt': True}, 'target_not_restorable'),
        ('target', {'data_protection_level': 'private'}, 'target_not_restorable'),
        ('target', {'record_lane_owner': 'foreign'}, 'target_not_restorable'),
        ('result', {'projection_privacy_refusal': {'version': 1}}, 'privacy'),
        ('result', {'projection': {'state': 'ready', 'privacy_reason': 'conversation_deleted'}}, 'privacy'),
        (
            'result',
            {'projection_parts': {'0': {'state': 'ready', 'privacy_reason': 'conversation_deleted'}}},
            'privacy',
        ),
        ('result', {'owner_key': 'wrong'}, 'binding'),
        ('result', {'segment_id': 'other'}, 'binding'),
        ('job', {'projection_binding': None}, 'binding'),
        ('job', {'owner_id': 'other'}, 'binding'),
        ('job', {'recovery_state': 'held'}, 'job_held'),
        ('job', {'state': 'quarantined'}, 'job_not_committed'),
        ('job', {'state': 'result_ready'}, 'job_not_committed'),
        ('result', {'committed_at': None}, 'invalid_age'),
        ('result', {'committed_at': float('nan')}, 'invalid_age'),
        ('result', {'committed_at': True}, 'invalid_age'),
        ('result', {'committed_at': GHOST_NOW - 86400 + 1}, 'young'),
        ('result', {'committed_at': GHOST_NOW + 1}, 'young'),
    ],
)
def test_ghost_safety_fences_are_rechecked_in_transaction(monkeypatch, kind, changes, expected):
    monkeypatch.setenv(GHOST_FLAG, 'true')
    seeded = ghost_rows()
    key = {'job': JOB_KEY, 'result': RESULT_KEY, 'target': ('users', OWNER, 'conversations', TARGET)}[kind]
    if changes is None:
        seeded.pop(key)
    else:
        seeded[key].update(changes)
    client, store = store_for(seeded)
    release = ProjectionReleaseStore(store)
    assert not release.release('held', GHOST_NOW)
    assert not release.ghost_settled and release.ghost_skip == expected
    assert client.rows == seeded
    assert not client.transactions[-1].updates


def test_nightly_expiry_helper_cannot_bypass_ghost_pass_cap(monkeypatch):
    monkeypatch.setenv(GHOST_FLAG, 'true')
    client, store = store_for(ghost_rows())
    release = ProjectionReleaseStore(store)
    assert not release.release('held', GHOST_NOW, dead_before=GHOST_NOW)
    assert release.ghost_skip == 'expiry_scan'
    assert not client.transactions[-1].updates


@pytest.mark.parametrize('enabled', [False, True])
def test_scan_caps_ghost_repairs_across_both_legs_and_counts_age_buckets(monkeypatch, enabled):
    from copy import deepcopy
    from database import batch_pipeline_projection_release as release

    monkeypatch.setenv(GHOST_FLAG, str(enabled).lower())
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'true')
    seeded = ghost_rows()
    ids = [f'ghost-{index:02d}' for index in range(24)]
    for index, sid in enumerate(ids):
        job = deepcopy(seeded[JOB_KEY])
        job['projection_binding']['segment_ids'] = (sid,)
        seeded[('batch_pipeline_prod_jobs', sid)] = job
        seeded[('batch_pipeline_prod_results', sid)] = {
            **deepcopy(seeded[RESULT_KEY]),
            'segment_id': sid,
            'committed_at': GHOST_NOW - (1, 7, 30)[index % 3] * 86400,
        }
    client, store = store_for(seeded)
    # Even if a stale assignment page returns ghosts, it shares the pass cap.
    monkeypatch.setattr(release, 'held_page_ids', lambda *a: ids[:12])
    monkeypatch.setattr(release, 'assignment_held_page_ids', lambda *a: ids[12:])
    counts, _, settled = release.release_scan_pass_settled(store, limit=24, after_id=None, now=GHOST_NOW)
    assert settled == (ids[:16] if enabled else [])
    assert counts['error'] == 0 and counts['examined'] == counts['ghost_classified'] == 24
    assert counts['ghost_settled'] == (16 if enabled else 0)
    assert counts['ghost_skipped_cap'] == (8 if enabled else 0)
    assert counts['ghost_skipped_count_only'] == (0 if enabled else 24)
    assert [counts[f'ghost_age_{bucket}'] for bucket in release.GHOST_AGE_BUCKETS] == [8, 8, 8]
    assert sum(counts[f'ghost_skipped_{name}'] for name in release.GHOST_SKIP_CLASSES) + counts['ghost_settled'] == 24
    assert sum(client.rows[('batch_pipeline_prod_results', sid)]['projection_state'] == 'ready' for sid in ids) == (
        16 if enabled else 0
    )


def test_ghost_summary_contains_only_fixed_aggregate_classes(monkeypatch, caplog):
    from database import batch_pipeline_projection_release as release

    monkeypatch.setenv(GHOST_FLAG, 'false')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'false')
    monkeypatch.setattr(release, 'held_page_ids', lambda *a: ['held'])
    _, store = store_for(ghost_rows(age=30 * 86400))
    from types import SimpleNamespace
    from utils.batch_pipeline.projection import Projector

    scanner = SimpleNamespace(store=store, clock=lambda: GHOST_NOW, release_after=None)
    with caplog.at_level('INFO'):
        counts = Projector.release_held_scan(scanner, limit=1)
    summary = next(record.getMessage() for record in caplog.records if 'outcome=summary' in record.getMessage())
    assert 'ghost_settled=0 classified=1 skipped_by_class=' in summary
    assert 'count_only:1' in summary and 'age_buckets=1d:0,7d:0,30d_plus:1' in summary
    assert OWNER not in summary and TARGET not in summary and 'gs://' not in summary
    assert counts['ghost_skipped_count_only'] == 1


@pytest.mark.parametrize('label', ['g1', 'G_2-drain', 'a' * 16])
def test_cohort_is_written_only_with_the_single_ghost_update(monkeypatch, label):
    monkeypatch.setenv(GHOST_FLAG, 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_COHORT', label)
    client, store = store_for(ghost_rows())
    assert not ProjectionReleaseStore(store).release('held', GHOST_NOW)
    assert client.transactions[-1].updates == [
        (RESULT_KEY, {'projection_state': 'ready', 'ghost_settled_cohort': label})
    ]


@pytest.mark.parametrize('label', ['', 'a' * 17, ' g1', 'g1\n', 'bad/row', 'é', 'private-owner'])
def test_invalid_cohort_falls_back_and_counts_without_logging_value_or_row(monkeypatch, caplog, label):
    monkeypatch.setenv(GHOST_FLAG, 'true')
    # private-owner is a valid label, used as the control for no diagnostic.
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_COHORT', label)
    client, store = store_for(ghost_rows())
    with caplog.at_level('INFO'):
        ProjectionReleaseStore(store).release('held', GHOST_NOW)
    valid = label == 'private-owner'
    assert client.rows[RESULT_KEY]['ghost_settled_cohort'] == (label if valid else 'g1')
    diagnostics = [r.getMessage() for r in caplog.records if 'event=batch_projection_ghost_cohort' in r.getMessage()]
    assert diagnostics == ([] if valid else ['event=batch_projection_ghost_cohort outcome=invalid_fallback count=1'])
    assert label not in '\n'.join(diagnostics) if label else True
    assert OWNER not in '\n'.join(diagnostics) and 'held' not in '\n'.join(diagnostics)


def test_flag_off_does_not_read_cohort_setting_or_write(monkeypatch):
    from database import batch_pipeline_projection_release as release

    monkeypatch.setenv(GHOST_FLAG, 'false')
    monkeypatch.setattr(release, 'projection_ghost_settle_cohort', Mock(side_effect=AssertionError('flag off')))
    client, store = store_for(ghost_rows())
    assert not ProjectionReleaseStore(store).release('held', GHOST_NOW)
    assert not client.transactions[-1].updates


def test_real_hold_never_gets_a_cohort_marker(monkeypatch):
    monkeypatch.setenv(GHOST_FLAG, 'true')
    client, store = store_for(rows())
    assert ProjectionReleaseStore(store).release('held', GHOST_NOW)
    assert 'ghost_settled_cohort' not in client.rows[RESULT_KEY]


@pytest.mark.parametrize('enabled', [False, True])
def test_release_page_returns_only_successfully_settled_ids(monkeypatch, enabled):
    from database import batch_pipeline_projection_release as release

    monkeypatch.setenv(GHOST_FLAG, str(enabled).lower())
    _, store = store_for(ghost_rows())
    monkeypatch.setattr(release, 'held_page_ids', lambda *a: ['missing', 'held'])
    counts, after, settled = release_page_settled(store, limit=3, after_id=None, now=GHOST_NOW)
    assert settled == (['held'] if enabled else [])
    assert counts['ghost_settled'] == len(settled)
    assert after is None
    # A stale page on the next scan must not wake an already settled row.
    assert release_page_settled(store, limit=3, after_id=None, now=GHOST_NOW)[2] == []


def test_release_page_fetch_failure_returns_no_settled_ids(monkeypatch):
    from database import batch_pipeline_projection_release as release

    monkeypatch.setattr(release, 'held_page_ids', Mock(side_effect=RuntimeError('fetch failed')))
    _, store = store_for(ghost_rows())
    counts, after, settled = release_page_settled(store, limit=3, after_id='resume')
    assert counts['examined'] == 0 and after == 'resume' and settled == []


@pytest.mark.parametrize('wake', [None, 'true', 'false'])
def test_release_scan_hands_settled_ids_to_followup_tail_only_when_enabled(monkeypatch, wake):
    from database import batch_pipeline_projection_release as release
    from utils.batch_pipeline.projection import Projector

    monkeypatch.setenv(GHOST_FLAG, 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'false')
    flag = 'BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_WAKE_ENABLED'
    monkeypatch.delenv(flag, raising=False) if wake is None else monkeypatch.setenv(flag, wake)
    _, store = store_for(ghost_rows())
    monkeypatch.setattr(release, 'held_page_ids', lambda *a: ['held'])
    projector = Projector(store.store, Mock(), projection_store=store, clock=lambda: GHOST_NOW)
    handoff = Mock(wraps=projector.owe_followups)
    monkeypatch.setattr(projector, 'owe_followups', handoff)
    assert projector.release_held_scan()['ghost_settled'] == 1
    if wake == 'false':
        handoff.assert_not_called()
        assert projector.chain_followups == []
    else:
        handoff.assert_called_once_with(['held'])
        assert projector.chain_followups == ['held']
        # A repeated scan/handoff coalesces without moving the existing tail.
        projector.owe_followups(['held'])
        assert projector.chain_followups == ['held']
    assert projector.release_held_scan()['ghost_settled'] == 0


def test_ghost_target_failure_is_counted_in_release_summary_without_wake(monkeypatch, caplog):
    from database import batch_pipeline_projection_release as release
    from utils.batch_pipeline.projection import Projector

    monkeypatch.setenv(GHOST_FLAG, 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'false')
    seeded = ghost_rows()
    seeded.pop(('users', OWNER, 'conversations', TARGET))
    client, store = store_for(seeded)
    monkeypatch.setattr(release, 'held_page_ids', lambda *a: ['held'])
    projector = Projector(store.store, Mock(), projection_store=store, clock=lambda: GHOST_NOW)
    handoff = Mock(side_effect=AssertionError('unrestorable target must not wake'))
    monkeypatch.setattr(projector, 'owe_followups', handoff)
    with caplog.at_level('INFO'):
        counts = projector.release_held_scan()
    assert counts['ghost_skipped_target_not_restorable'] == 1
    assert counts['ghost_classified'] == 1 and counts['ghost_settled'] == 0
    assert 'target_not_restorable:1' in caplog.text
    handoff.assert_not_called()
    assert client.rows[RESULT_KEY] == seeded[RESULT_KEY]
