"""Real loopback Firestore emulator proof for the SCA-1649 participation control.

Forward apply and restoration run against a real emulator and an isolated
``batch_pipeline_test_*`` namespace, using the emulator's own post-write
``update_time`` as the CAS basis. No production transport, credentials or
namespace is reachable from here: ``FirestoreStore`` refuses a test namespace
without a loopback ``FIRESTORE_EMULATOR_HOST``.
"""

import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

from google.api_core.datetime_helpers import DatetimeWithNanoseconds
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database.batch_pipeline_store import FirestoreStore

pytestmark = pytest.mark.integration

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'rollout' / 'timeliness_participation.py'
SPEC = importlib.util.spec_from_file_location('timeliness_participation_emulator_helper', SCRIPT)
assert SPEC is not None and SPEC.loader is not None

NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


@pytest.fixture(scope='session', autouse=True)
def initialize_firebase():
    """The loopback fixture uses anonymous Firestore; no ADC is required."""
    yield


@pytest.fixture
def helper(monkeypatch):
    module = importlib.util.module_from_spec(SPEC)
    monkeypatch.setitem(sys.modules, SPEC.name, module)
    SPEC.loader.exec_module(module)
    return module


@pytest.fixture
def store():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback Firestore emulator required; no cloud fallback')
    project = os.environ.get('GOOGLE_CLOUD_PROJECT', '')
    assert project.startswith('demo-'), 'emulator proofs require a demo project'
    client = firestore.Client(project=project, credentials=AnonymousCredentials())
    namespace = f'batch_pipeline_test_{uuid4().hex[:12]}'
    store = FirestoreStore(namespace, firestore_client=client)
    yield store
    # Only this synthetic namespace is ever touched.
    for doc in client.collection(f'{namespace}_control').stream():
        doc.reference.delete()
    client.close()


def _prior(helper, store):
    return helper.capture(store, plane='prod-omi-backend')


def _plan(helper, prior, *, operation_id='sca1649-emulator-op', seconds=900):
    return helper.build_plan(
        prior,
        operation_id=operation_id,
        created_at=NOW,
        until=NOW + dt.timedelta(seconds=seconds),
    )


def _reference(store):
    return store.client.collection(f'{store.namespace}_control').document('timeliness_metrics_participation')


def _seed(store, fields):
    _reference(store).set(fields)


def _read(store):
    snapshot = _reference(store).get()
    return snapshot.to_dict() if snapshot.exists else None


def test_present_prior_apply_and_restore_are_exact(helper, store):
    prior_fields = {
        'operator_note': 'prior state',
        'count': 3,
        'flag': True,
        'stamp': DatetimeWithNanoseconds(2026, 1, 1, tzinfo=dt.timezone.utc, nanosecond=42),
        'blob': b'\x00\x01',
        'nested': {'a': [1, None, 'x']},
        'empty': None,
        'a.b': 'literal dotted field',
        'tick`key': 'literal backtick field',
        r'back\\slash': 'literal backslash field',
    }
    reference = store.client.document('related/one')
    prior_fields['reference'] = reference
    prior_fields['nested_references'] = {'items': [reference]}
    _seed(store, prior_fields)
    prior = _prior(helper, store)
    assert prior['exists'] is True

    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')
    after_apply = _read(store)
    assert after_apply['operation_id'] == 'sca1649-emulator-op'
    assert after_apply['target_plane'] == 'prod-omi-backend'
    assert after_apply['operator_note'] == 'prior state'
    assert applied['applied_update_time'] == helper.tag(_reference(store).get().update_time)

    restored = helper.restore_prior(store, prior, applied, mode='emulator')
    assert restored['exact'] is True
    assert _read(store) == prior_fields
    assert helper.verify_restored(store, prior)['restored'] is True
    # update_time necessarily advances; it is CAS evidence, not a restorable field.
    assert restored['restored_update_time'] != prior['update_time']


def test_absent_prior_apply_creates_and_restore_deletes(helper, store):
    prior = _prior(helper, store)
    assert prior['exists'] is False
    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')
    assert _read(store)['operation_id'] == 'sca1649-emulator-op'
    restored = helper.restore_prior(store, prior, applied, mode='emulator')
    assert restored['exact'] is True
    assert _read(store) is None
    assert helper.verify_restored(store, prior)['restored'] is True


def test_apply_refuses_a_concurrent_writer_before_the_write(helper, store):
    _seed(store, {'kept': 1})
    prior = _prior(helper, store)
    plan = _plan(helper, prior)
    _seed(store, {'kept': 2})
    with pytest.raises(helper.Refused, match='update_time mismatch'):
        helper.apply_plan(store, plan, mode='emulator')
    assert _read(store) == {'kept': 2}


def test_apply_refuses_a_create_when_the_document_appeared(helper, store):
    prior = _prior(helper, store)
    plan = _plan(helper, prior)
    _seed(store, {'kept': 1})
    with pytest.raises(helper.Refused, match='existence changed'):
        helper.apply_plan(store, plan, mode='emulator')
    assert _read(store) == {'kept': 1}


def test_restore_refuses_a_concurrent_writer_between_apply_and_restore(helper, store):
    _seed(store, {'kept': 1})
    prior = _prior(helper, store)
    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')
    _reference(store).update({'concurrent': 'writer'})
    with pytest.raises(helper.Refused, match='update_time mismatch'):
        helper.restore_prior(store, prior, applied, mode='emulator')
    assert _read(store)['concurrent'] == 'writer'


def test_restore_refuses_a_delete_between_apply_and_restore(helper, store):
    _seed(store, {'kept': 1})
    prior = _prior(helper, store)
    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')
    _reference(store).delete()
    with pytest.raises(helper.Refused, match='absent'):
        helper.restore_prior(store, prior, applied, mode='emulator')


def test_restore_refuses_a_stale_apply_receipt(helper, store):
    _seed(store, {'kept': 1})
    prior = _prior(helper, store)
    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')
    stale = dict(applied)
    stale['applied_update_time'] = prior['update_time']
    with pytest.raises(helper.Refused, match='update_time mismatch'):
        helper.restore_prior(store, prior, stale, mode='emulator')


def test_restore_refuses_tampered_captures_without_mutating(helper, store):
    """A flipped existence flag or a rewritten update_time must not delete or overwrite."""
    _seed(store, {'kept': 1, 'nested': {'a': True}})
    prior = _prior(helper, store)
    assert prior['exists'] is True
    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')
    applied_snapshot = _reference(store).get()
    applied_state = (applied_snapshot.to_dict(), applied_snapshot.update_time)

    tampered_captures = (
        dict(prior, exists=False),
        dict(prior, exists=False, update_time=None),
        dict(prior, update_time=helper.tag(applied_snapshot.update_time)),
        dict(prior, fields={'kept': {'t': 'int', 'v': '2'}}),
    )
    for tampered in tampered_captures:
        with pytest.raises(helper.Refused):
            helper.restore_prior(store, tampered, applied, mode='emulator')
        current = _reference(store).get()
        assert (current.to_dict(), current.update_time) == applied_state

    # The receipt itself must carry the binding; stripping it refuses too.
    with pytest.raises(helper.Refused, match='no prior capture binding'):
        helper.restore_prior(store, prior, {k: v for k, v in applied.items() if k != 'prior'}, mode='emulator')
    current = _reference(store).get()
    assert (current.to_dict(), current.update_time) == applied_state

    # The untampered capture still restores exactly, so the refusals were about
    # the tampering and not about an unrestorable state.
    assert helper.restore_prior(store, prior, applied, mode='emulator')['exact'] is True
    assert _read(store) == {'kept': 1, 'nested': {'a': True}}


def test_emulator_transport_refusals(helper, monkeypatch):
    with pytest.raises(helper.Refused, match='loopback'):
        helper.resolve_store('batch_pipeline_test_x', emulator_host='10.0.0.5:8085')
    with pytest.raises(helper.Refused, match='batch_pipeline_test_'):
        helper.resolve_store('batch_pipeline_prod', emulator_host='127.0.0.1:8085')
    # A test namespace with no explicit host is refused either by the ambient
    # emulator guard or by the missing --dry-run=emulator; both fail closed.
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    with pytest.raises(helper.Refused, match='--dry-run=emulator'):
        helper.resolve_store('batch_pipeline_test_x')
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:8085')
    with pytest.raises(helper.Refused, match='ambient FIRESTORE_EMULATOR_HOST'):
        helper.resolve_store('batch_pipeline_test_x')


def test_cli_emulator_apply_and_restore_round_trip(helper, store, tmp_path, monkeypatch):
    """The literal contract commands, with the emulator transport and namespace."""
    _seed(store, {'kept': 1, 'nested': {'a': True}})
    monkeypatch.setattr(helper, 'resolve_store', lambda namespace, emulator_host=None: store)
    prior_path = tmp_path / 'timeliness-prior.json'
    plan_path = tmp_path / 'timeliness-plan.json'
    assert (
        helper.main(
            ['capture', '--namespace', store.namespace, '--plane', 'prod-omi-backend', '--out', str(prior_path)]
        )
        == 0
    )
    assert (
        helper.main(
            [
                'plan',
                '--prior',
                str(prior_path),
                '--operation-id',
                'sca1649-cli-op',
                '--created-at',
                NOW.isoformat(),
                '--until',
                (NOW + dt.timedelta(seconds=900)).isoformat(),
                '--out',
                str(plan_path),
            ]
        )
        == 0
    )
    assert (
        helper.main(
            [
                'apply',
                '--plan',
                str(plan_path),
                '--dry-run=emulator',
                '--emulator-host',
                '127.0.0.1:8085',
                '--namespace',
                store.namespace,
            ]
        )
        == 0
    )
    assert _read(store)['operation_id'] == 'sca1649-cli-op'
    assert (
        helper.main(
            [
                'restore',
                '--prior',
                str(prior_path),
                '--plan',
                str(plan_path),
                '--dry-run=emulator',
                '--emulator-host',
                '127.0.0.1:8085',
                '--namespace',
                store.namespace,
            ]
        )
        == 0
    )
    assert _read(store) == {'kept': 1, 'nested': {'a': True}}
    assert helper.main(['verify-restored', '--prior', str(prior_path)]) == 0
    receipt = json.loads(Path(plan_path).with_suffix('.applied.json').read_text())
    assert receipt['mode'] == 'emulator'
    assert receipt['operation_id'] == 'sca1649-cli-op'
