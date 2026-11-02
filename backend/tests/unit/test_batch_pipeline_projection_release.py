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


def _restarted_scans(monkeypatch, restarts: int) -> set[str]:
    """Held ids examined when every pass runs on a fresh process (one page each)."""
    import hashlib
    import secrets

    import database.batch_pipeline_projection_release as release
    from utils.batch_pipeline import projection

    ids = sorted(hashlib.sha256(str(n).encode()).hexdigest() for n in range(200))
    examined: list[str] = []
    monkeypatch.setattr(release, 'RELEASE_PAGE', 10)
    monkeypatch.setattr(
        release,
        'held_page_ids',
        lambda client, namespace, limit, after_id: [i for i in ids if after_id is None or i > after_id][:limit],
    )
    monkeypatch.setattr(release.ProjectionReleaseStore, 'release', lambda self, sid, now: examined.append(sid) or False)
    seeds = iter(hashlib.sha256(f'seed-{n}'.encode()).hexdigest() for n in range(restarts))
    monkeypatch.setattr(secrets, 'token_hex', lambda nbytes: next(seeds))
    for _ in range(restarts):
        projection.Projector(Mock(), Mock()).release_held_scan()
    return set(examined)


def test_restarted_release_scans_reach_rows_past_the_first_page(monkeypatch):
    """Serving instances restart and trade the lease long before one pass wraps.

    A scan that always restarted at the first document name re-examined the
    same prefix forever (prod 11-02: every release retry sat in the first 20%
    of name order); a fresh process starts at a random point instead.
    """
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', raising=False)
    examined = _restarted_scans(monkeypatch, restarts=20)
    assert len(examined) >= 100


def test_release_scan_starts_at_the_first_name_when_hold_recovery_is_off(monkeypatch):
    from utils.batch_pipeline import projection

    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'false')
    assert projection.Projector(Mock(), Mock()).release_after is None


def test_release_scan_seed_stays_inside_the_hex_id_keyspace(monkeypatch):
    from utils.batch_pipeline import projection

    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', raising=False)
    seed = projection.Projector(Mock(), Mock()).release_after
    assert isinstance(seed, str) and len(seed) == 64
    assert set(seed) <= set('0123456789abcdef')


def test_release_scan_counts_rows_by_outcome(monkeypatch):
    import database.batch_pipeline_projection_release as release
    from utils.batch_pipeline import correctness_metrics

    def outcome(self, segment_id, now):
        if segment_id == 'broken':
            raise RuntimeError('synthetic')
        return segment_id == 'restored'

    monkeypatch.setenv('BATCH_PIPELINE_CORRECTNESS_METRICS_ENABLED', 'true')
    monkeypatch.setattr(release, 'held_page_ids', lambda *args: ['restored', 'waiting', 'broken'])
    monkeypatch.setattr(release.ProjectionReleaseStore, 'release', outcome)
    before = {o: correctness_metrics.RELEASE_ROWS.labels(o)._value.get() for o in ('released', 'waiting', 'error')}
    release.release_page_counted(Mock(), limit=3, after_id=None, now=100)
    after = {o: correctness_metrics.RELEASE_ROWS.labels(o)._value.get() for o in ('released', 'waiting', 'error')}
    assert {o: after[o] - before[o] for o in after} == {'released': 1, 'waiting': 1, 'error': 1}
