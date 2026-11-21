"""Batch privacy checks counted by calling module and shape (SCA-3508, metric only)."""

import json

from database import batch_pipeline_privacy as privacy, privacy_check_metrics as metrics
from database.batch_privacy_attempt import batch_privacy_attempt
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

UID = 'site-owner'
LEVERS = json.dumps({'bpp_generation_memo': 0, 'bpp_owner_memo': 0})


def count(caller, shape):
    return metrics.SITE_CHECKS.labels(caller, shape)._value.get()


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


def _call_from(module, statement, db):
    code = compile(statement, module.replace('.', '/') + '.py', 'exec')
    exec(
        code,
        {'__name__': module, 'privacy': privacy, 'db': db, 'UID': UID, 'batch_privacy_attempt': batch_privacy_attempt},
    )


def test_production_module_is_named_with_each_shape(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', LEVERS)
    db = _db()
    module = 'database.batch_pipeline_projection_session'
    label = module + ':<module>'
    before = {s: count(label, s) for s in ('no_transaction', 'snapshots', 'attempt', 'no_attempt')}
    _call_from(module, 'privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=["c"])', db)
    _call_from(module, 'privacy.assert_batch_write_allowed(db, None, UID, conversation_ids=["c"])', db)
    _call_from(
        module,
        'privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=["c"], snapshots={})',
        db,
    )
    _call_from(
        module,
        'with batch_privacy_attempt():\n'
        '    privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=["c"])',
        db,
    )
    assert {s: count(label, s) - before[s] for s in before} == {
        'no_transaction': 1,
        'snapshots': 1,
        'attempt': 1,
        'no_attempt': 1,
    }


def test_non_production_frame_is_other(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', LEVERS)
    db = _db()
    before = count('other', 'no_attempt')
    # This test module is outside the production packages.
    privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=['c'])
    assert count('other', 'no_attempt') == before + 1


def test_shadow_candidate_is_not_counted_twice(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps({'privacy_checks_shadow': 100, 'bpp_owner_memo': 100}))
    db = _db()
    module = 'utils.enrichment.redrive'
    before = count(module + ':<module>', 'no_attempt')
    _call_from(module, 'privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=["c"])', db)
    assert count(module + ':<module>', 'no_attempt') == before + 1


def test_metric_failure_never_changes_the_decision(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', LEVERS)
    monkeypatch.setattr(metrics.SITE_CHECKS, 'labels', lambda *a: (_ for _ in ()).throw(RuntimeError('boom')))
    db = _db()
    assert privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=['c']) == 0


def test_attribution_does_not_leave_a_frame_cycle():
    import gc
    import weakref

    class Marker:
        pass

    def caller():
        local = Marker()
        ref = weakref.ref(local)
        metrics.check_site('no_attempt')
        return ref

    gc.disable()
    try:
        ref = caller()
        assert ref() is None
    finally:
        gc.enable()


def test_unknown_shape_is_bounded():
    before = count('other', 'no_attempt')
    metrics.check_site('surprise')
    assert count('other', 'no_attempt') == before + 1


def test_forwarding_wrapper_is_attributed_to_its_caller(monkeypatch):
    """store.check_privacy fronts intake, policy, shadow and others; name the loop, not the wrapper."""
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', LEVERS)
    db = _db()
    source = (
        'def check_privacy(uid):\n'
        '    return privacy.assert_batch_write_allowed(db, db.transaction(), uid, conversation_ids=["c"])\n'
    )
    wrapper = {'__name__': 'database.batch_pipeline_store', 'privacy': privacy, 'db': db}
    exec(compile(source, 'database/batch_pipeline_store.py', 'exec'), wrapper)
    loop = {'__name__': 'database.batch_pipeline_intake', 'check_privacy': wrapper['check_privacy'], 'UID': UID}
    exec(compile('def admit():\n    check_privacy(UID)\n', 'database/batch_pipeline_intake.py', 'exec'), loop)
    before = count('database.batch_pipeline_intake:admit', 'no_attempt')
    wrapped_before = count('database.batch_pipeline_store:check_privacy', 'no_attempt')
    loop['admit']()
    assert count('database.batch_pipeline_intake:admit', 'no_attempt') == before + 1
    assert count('database.batch_pipeline_store:check_privacy', 'no_attempt') == wrapped_before
