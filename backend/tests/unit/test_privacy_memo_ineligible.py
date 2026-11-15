"""Attribution of batch privacy decisions the attempt memo cannot certify (metric only)."""

import json

from database import batch_pipeline_privacy as privacy, privacy_check_metrics as metrics
from database.batch_privacy_attempt import batch_privacy_attempt
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

UID = 'ineligible-owner'


def count(reason, caller):
    return metrics.MEMO_INELIGIBLE.labels(reason, caller)._value.get()


def _db():
    return StrictFirestore(
        {
            ('users', UID): {'data_protection_level': 'standard'},
            ('users', UID, 'conversations', 'c'): {
                'record_lane_owner': 'batch_live_v1',
                'private_cloud_sync_enabled': True,
            },
        }
    )


def test_reason_labels_and_unknown_caller_is_other(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps({'bpp_generation_memo': 100}))
    db = _db()
    before = {r: count(r, 'other') for r in ('no_attempt', 'no_transaction', 'snapshots')}
    privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=['c'])  # no attempt scope
    with batch_privacy_attempt():
        privacy.assert_batch_write_allowed(db, None, UID, conversation_ids=['c'])
        privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=['c'], snapshots={})
    # This test module is not an allowlisted call site, so it is attributed to 'other'.
    assert {r: count(r, 'other') - before[r] for r in before} == {'no_attempt': 1, 'no_transaction': 1, 'snapshots': 1}


def test_allowlisted_call_site_is_named(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps({'bpp_generation_memo': 100}))
    db = _db()
    before = count('no_attempt', 'utils.enrichment.redrive')
    # Execute the call from a frame whose module name is an allowlisted call site.
    code = compile(
        'privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=["c"])', 'redrive.py', 'exec'
    )
    exec(code, {'__name__': 'utils.enrichment.redrive', 'privacy': privacy, 'db': db, 'UID': UID})
    assert count('no_attempt', 'utils.enrichment.redrive') == before + 1


def test_metric_failure_never_changes_the_decision(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps({'bpp_generation_memo': 100}))
    monkeypatch.setattr(metrics.MEMO_INELIGIBLE, 'labels', lambda *a: (_ for _ in ()).throw(RuntimeError('boom')))
    db = _db()
    assert privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=['c']) == 0


def test_attribution_does_not_leave_a_frame_cycle(monkeypatch):
    """Luna r1 P2 on #24666: retaining the current frame would keep caller frames alive until cyclic GC."""
    import gc
    import weakref

    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps({'bpp_generation_memo': 100}))

    class Marker:
        pass

    def caller():
        local = Marker()
        ref = weakref.ref(local)
        metrics.memo_ineligible('no_attempt')
        return ref

    gc.disable()
    try:
        ref = caller()
        assert ref() is None  # freed by refcounting alone, no cycle
    finally:
        gc.enable()
