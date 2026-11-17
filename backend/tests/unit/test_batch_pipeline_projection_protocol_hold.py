"""11-16 replay: real prepare, quarantine, assignment, owner walk and release fences."""

from dataclasses import asdict
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.policy import ProjectionPolicy
from database import batch_pipeline_projection_session as sessions
from database import batch_pipeline_projection_release as releases
from database import conversations as conversations_db
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_protocol import ProjectionBlocked, ProjectionSourceMarkerMissing
from database.batch_pipeline_projection_protocol_hold import (
    PROTOCOL_HOLDS,
    PROTOCOL_HOLD_REASON,
    PROTOCOL_REFUSAL_SECONDS,
    bound_protocol_head,
)
from database.batch_pipeline_projection_protocol import missing_canonical_source_marker
from database.sync_ledger import sync_content_ledger_ref
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import chunk
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.projection import Projector
from utils.batch_pipeline.scheduler import owner_key

SWITCH = 'BATCH_PIPELINE_PROJECTION_PROTOCOL_HEAD_BOUND_ENABLED'
NS = 'batch_pipeline_test_protocol_bound'
OWNER = 'u'


@pytest.fixture
def incident(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    monkeypatch.delenv(SWITCH, raising=False)
    monkeypatch.setattr(conversations_db, 'index_sync_assignment', lambda *a: None)
    monkeypatch.setattr(conversations_db, 'find_sync_live_overlap_candidates', lambda *a, **kw: ())
    client = StrictFirestore({('users', OWNER): {'data_protection_level': 'standard'}})
    facade = SimpleNamespace(namespace=NS, client=client)
    store = ProjectionStore(facade)
    store.run = lambda operation, **kw: operation(client.transaction())
    policy = ProjectionPolicy(async_projection=True)
    store.policy = lambda _: policy
    now = [2000.0]
    bindings = {}
    for index, sid in enumerate(('head', 'next', 'tail')):
        binding = ProjectionBinding(OWNER, f'job-{sid}', f'content-{sid}', (sid,), client_device_id='pendant')
        bindings[sid] = binding
        result = {'outcome': 'success', 'result_uri': f'gs://synthetic/{sid}-result'}
        job = {
            'owner_id': OWNER,
            'segment_id': sid,
            'state': 'committed',
            'capture_at': 1000.0 + index * 10,
            'duration_seconds': 10.0,
            'privacy_generation': 0,
            'audio_uri': f'gs://synthetic/{sid}-audio',
            'result': result,
            'projection_binding': asdict(binding),
            'policy_parts': {'projection': policy.to_dict()},
        }
        if sid == 'head':
            job.update(protocol_version=2, source_reuse_version=1, source_reuse_key='synthetic-key')
        client.rows[(f'{NS}_jobs', sid)] = job
        client.rows[(f'{NS}_results', sid)] = {
            'protocol_version': 2 if sid == 'head' else 1,
            'segment_id': sid,
            'owner_key': owner_key(OWNER),
            'capture_at': job['capture_at'],
            'previous_segment_id': ('head', 'next')[index - 1] if index else None,
            'committed_at': 1900.0 + index,
            'projection_state': 'pending',
            'result': result,
        }
        client.rows[sync_content_ledger_ref(client, OWNER, binding.content_id).path] = {
            'dispatch_protocol': 'batch_v1',
            'status': 'processing',
            'job_id': binding.job_id,
            'batch_pipeline': {'protocol_version': 1, 'namespace': NS, 'segment_ids': [sid]},
        }
    client.rows[(f'{NS}_owners', owner_key(OWNER))] = {}

    def read(sid):
        return (store.ref('jobs', sid).get().to_dict(), store.ref('results', sid).get().to_dict(), bindings[sid])

    store.read = read
    facade.projection_successor = lambda key, previous: next(
        (sid for sid in bindings if client.rows[(f'{NS}_results', sid)]['previous_segment_id'] == previous), None
    )
    projector = Projector(facade, Mock(), clock=lambda: now[0])
    projector.store = store

    def persist(sid, job, entry, binding, **_):
        session = store.session(sid, binding, now[0], policy=policy)
        incoming = chunk(sid, job['capture_at'], f'Synthetic {sid} contribution has its own capture interval.')
        conversations_db.assign_sync_conversation(
            OWNER,
            incoming,
            target_id='next',
            firestore_client=client,
            before_assign=session.prepare,
            validate_plan=session.validate_plan,
            after_assign=lambda tx, planned: session.persist(tx, planned),
        )

    # Only payload/manifest construction is replaced; transaction and ordering
    # fences, timestamp merging, hold/release and the owner walk remain real.
    projector._persist_read = persist
    supported = sessions.source_reader_marked
    # Restore the pre-#25597 reader's marker policy to reproduce 11-16 exactly.
    monkeypatch.setattr(sessions, 'source_reader_marked', lambda entry, job: False)
    monkeypatch.setattr(releases, 'source_reader_marked', lambda entry, job: False)
    return SimpleNamespace(
        client=client,
        store=store,
        projector=projector,
        now=now,
        bindings=bindings,
        supported=supported,
        row=lambda sid: client.rows[(f'{NS}_results', sid)],
        watermark=lambda: client.rows[(f'{NS}_owners', owner_key(OWNER))].get('projection_watermark'),
    )


def walk(f):
    return f.projector._walk_rows(
        OWNER,
        recovered=None,
        limit=10,
        budget_seconds=30,
        seed=None,
        drain=False,
        prefetch=None,
        deferred=False,
    )


def test_incident_chain_advances_after_bound_then_recovers_in_capture_order(incident, monkeypatch, caplog):
    f = incident
    counter = PROTOCOL_HOLDS.labels(reason=PROTOCOL_HOLD_REASON)
    before = counter._value.get()
    with pytest.raises(ProjectionSourceMarkerMissing, match='immutable result binding mismatch'):
        f.store.session('head', f.bindings['head'], f.now[0]).prepare(f.client.transaction())
    assert walk(f).advanced == []
    assert f.row('head')['projection_blocked_since'] == f.now[0]
    f.now[0] += PROTOCOL_REFUSAL_SECONDS - 1
    assert walk(f).advanced == []
    assert f.watermark() is None
    f.now[0] += 1
    result = walk(f)
    assert result.advanced == ['head', 'next', 'tail']
    assert result.stop == 'end'
    assert f.watermark() == 'tail'
    held = f.row('head')
    assert held['projection_state'] == 'quarantine_held'
    assert held['projection']['state'] == 'quarantined'
    assert held['projection']['conversation_id'] is None
    assert 'expires_at' not in held
    assert not any(path[0] == f'{NS}_projections' for path in f.client.rows)
    assert counter._value.get() == before + 1
    lines = [r.message for r in caplog.records if 'action=protocol_head_bound' in r.message]
    assert lines == [
        'event=batch_projection action=protocol_head_bound outcome=quarantine_held '
        'reason=missing_source_marker age_seconds=900'
    ]
    # A still-refusing reader cannot release using the administrative version.
    release = releases.ProjectionReleaseStore(f.store)
    assert not release.release('head', f.now[0])
    assert not release.release('head', f.now[0] + 86400)
    monkeypatch.setattr(sessions, 'source_reader_marked', f.supported)
    monkeypatch.setattr(releases, 'source_reader_marked', f.supported)
    assert release.release('head', f.now[0] + 1)
    assert f.row('head')['projection_protocol_hold_reason'] is None
    assert f.watermark() == 'tail'
    job, entry, binding = f.store.read('head')
    f.projector._persist_read('head', job, entry, binding)
    assert f.watermark() == 'tail'
    assert f.row('head')['projection_state'] == 'persisted'
    receipt = f.row('head')['projection']
    row = f.client.rows[('users', OWNER, 'conversations', receipt['conversation_id'])]
    segments = conversations_db.decode_transcript_segments_verified(
        OWNER, row['transcript_segments'], row.get('transcript_segments_compressed', False)
    )
    assert [s['text'].split()[1] for s in segments] == ['head', 'next', 'tail']
    assert [s['start'] for s in segments] == sorted(s['start'] for s in segments)
    assert f.client.rows[(f'{NS}_jobs', 'head')]['audio_uri'] == 'gs://synthetic/head-audio'
    assert counter._value.get() == before + 1


def test_kill_switch_retains_indefinite_block(incident, monkeypatch):
    monkeypatch.setenv(SWITCH, 'false')
    f = incident
    assert walk(f).advanced == []
    f.now[0] += 86400
    assert walk(f).advanced == []
    assert 'projection_blocked_since' not in f.row('head')
    assert f.watermark() is None


def test_unmarked_job_residual_is_bounded_by_current_reader(incident, monkeypatch):
    f = incident
    monkeypatch.setattr(sessions, 'source_reader_marked', f.supported)
    monkeypatch.setattr(releases, 'source_reader_marked', f.supported)
    f.client.rows[(f'{NS}_jobs', 'head')].pop('source_reuse_version')
    assert walk(f).advanced == []
    f.now[0] += PROTOCOL_REFUSAL_SECONDS
    assert walk(f).advanced == ['head', 'next', 'tail']
    release = releases.ProjectionReleaseStore(f.store)
    assert not release.release('head', f.now[0])
    assert not release.release('head', f.now[0], operator=True)
    assert f.row('head')['projection_state'] == 'quarantine_held'
    retained_result = dict(f.row('head')['result'])

    def compatible_reader(entry, job):
        # Stand in for a later reader that understands this synthetic retained
        # format. Administrative versions and operator=True are not that proof.
        return f.supported(entry, job) or (
            missing_canonical_source_marker(entry, job) and entry.get('result') == retained_result
        )

    monkeypatch.setattr(sessions, 'source_reader_marked', compatible_reader)
    monkeypatch.setattr(releases, 'source_reader_marked', compatible_reader)
    assert release.release('head', f.now[0] + 1)
    job, entry, binding = f.store.read('head')
    f.projector._persist_read('head', job, entry, binding)
    assert f.watermark() == 'tail'
    assert f.row('head')['projection_state'] == 'persisted'
    assert f.row('head')['result'] == retained_result
    assert 'source_reuse_version' not in f.client.rows[(f'{NS}_jobs', 'head')]
    receipt = f.row('head')['projection']
    row = f.client.rows[('users', OWNER, 'conversations', receipt['conversation_id'])]
    segments = conversations_db.decode_transcript_segments_verified(
        OWNER, row['transcript_segments'], row.get('transcript_segments_compressed', False)
    )
    assert [s['text'].split()[1] for s in segments] == ['head', 'next', 'tail']


@pytest.mark.parametrize(
    'field,value',
    [
        ('owner_key', 'foreign'),
        ('capture_at', 0),
        ('segment_id', 'foreign'),
        ('result', {'outcome': 'silence'}),
        ('protocol_version', 3),
        ('source_reuse_version', 2),
    ],
)
def test_other_binding_protocol_refusals_never_advance(incident, field, value):
    f = incident
    f.row('head')[field] = value
    assert walk(f).advanced == []
    f.now[0] += 86400
    assert walk(f).advanced == []
    assert f.watermark() is None
    assert f.row('head')['projection_state'] == 'pending'


@pytest.mark.parametrize('fence', ['privacy', 'ledger', 'predecessor', 'changed_result', 'source_owner'])
def test_hold_rechecks_all_fences_at_bound(incident, fence):
    f = incident
    assert walk(f).advanced == []
    f.now[0] += PROTOCOL_REFUSAL_SECONDS
    job, entry, binding = f.store.read('head')
    if fence == 'privacy':
        f.client.rows[('users', OWNER)]['data_protection_level'] = 'e2ee'
    elif fence == 'ledger':
        f.client.rows[sync_content_ledger_ref(f.client, OWNER, binding.content_id).path]['job_id'] = 'foreign'
    elif fence == 'predecessor':
        f.row('head')['previous_segment_id'] = 'missing'
    elif fence == 'changed_result':
        f.row('head')['result'] = {'outcome': 'silence'}
    else:
        f.store.ref('projections', 'source-synthetic-key').create({'owner_id': 'foreign', 'privacy_generation': 0})
    with pytest.raises((ProjectionBlocked, BatchPrivacyBlocked)):
        bound_protocol_head(f.store, 'head', job, entry, binding, f.now[0])
    assert f.watermark() is None
    assert f.row('head')['projection_state'] == 'pending'


def test_protocol_hold_session_cannot_assign_text(incident):
    f = incident
    tx = f.client.transaction()
    session = f.store.session('head', f.bindings['head'], f.now[0])
    session.prepare(tx, protocol_hold=True)
    with pytest.raises(ProjectionBlocked, match='protocol hold cannot assign'):
        session.persist(tx, ({'id': 'foreign'}, False, []))


def test_reader_fix_before_bound_prevents_stale_hold(incident, monkeypatch):
    f = incident
    assert walk(f).advanced == []
    f.now[0] += PROTOCOL_REFUSAL_SECONDS
    job, entry, binding = f.store.read('head')
    monkeypatch.setattr(sessions, 'source_reader_marked', f.supported)
    with pytest.raises(ProjectionBlocked, match='protocol refusal no longer applies'):
        bound_protocol_head(f.store, 'head', job, entry, binding, f.now[0])
    assert f.row('head')['projection_state'] == 'pending'


def test_sweep_also_bounds_the_refused_head(incident):
    f = incident
    f.projector.assignment_discovery = SimpleNamespace(next=lambda **_: ['head'])
    f.projector._sweep_finish = lambda *a: False
    assert f.projector.sweep()['blocked'] == 1
    f.now[0] += PROTOCOL_REFUSAL_SECONDS
    assert f.projector.sweep()['blocked'] == 1
    assert f.watermark() == 'head'
    assert walk(f).advanced == ['next', 'tail']


@pytest.mark.parametrize(
    'field,value', [('owner_id', 'foreign'), ('privacy_generation', 1), ('segment_id', 'duplicate')]
)
def test_release_retains_hold_when_source_ownership_changed(incident, monkeypatch, field, value):
    f = incident
    assert walk(f).advanced == []
    f.now[0] += PROTOCOL_REFUSAL_SECONDS
    assert walk(f).advanced == ['head', 'next', 'tail']
    monkeypatch.setattr(sessions, 'source_reader_marked', f.supported)
    monkeypatch.setattr(releases, 'source_reader_marked', f.supported)
    f.store.ref('projections', 'source-synthetic-key').create(
        {
            'owner_id': OWNER,
            'privacy_generation': 0,
            'segment_id': 'head',
            'expires_at': datetime.fromtimestamp(f.now[0] - 1, timezone.utc),
            field: value,
        }
    )
    release = releases.ProjectionReleaseStore(f.store)
    assert not release.release('head', f.now[0] + 1)
    assert not release.release('head', f.now[0] + 1, operator=True)
    assert f.row('head')['projection_state'] == 'quarantine_held'
    assert f.client.rows[(f'{NS}_jobs', 'head')]['recovery_state'] == 'held'
    assert f.watermark() == 'tail'


def test_post_commit_observation_uses_fresh_age_despite_stale_hint_and_shadow_failure(incident, monkeypatch, caplog):
    f = incident
    job, stale_entry, binding = f.store.read('head')
    assert walk(f).advanced == []
    f.now[0] += PROTOCOL_REFUSAL_SECONDS
    monkeypatch.setattr(f.store, '_mirror', Mock(side_effect=RuntimeError('synthetic shadow failure')))
    counter = PROTOCOL_HOLDS.labels(reason=PROTOCOL_HOLD_REASON)
    before = counter._value.get()
    assert bound_protocol_head(f.store, 'head', job, stale_entry, binding, f.now[0])
    assert counter._value.get() == before + 1
    assert f.watermark() == 'head'
    assert 'reason=missing_source_marker age_seconds=900' in caplog.text
