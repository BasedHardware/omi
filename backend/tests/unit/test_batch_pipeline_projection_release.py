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
from database.batch_pipeline_projection_release import ProjectionReleaseStore, release_page
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
    assert counts == {'released': 1, 'waiting': 0, 'error': 0, 'examined': 1, 'expired': 0}
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
