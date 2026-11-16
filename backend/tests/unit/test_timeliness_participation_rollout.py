"""Operator helper for the SCA-1649 participation control: CLI, plan and refusals.

The real apply/restore/conflict behaviour is proven against a loopback Firestore
emulator in ``tests/integration/test_timeliness_participation_emulator.py``.
These tests cover the argument surface, the lossless typed codec, the plan
bounds and the CAS refusal logic through an explicit in-memory double.
"""

import datetime as dt
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from google.api_core.datetime_helpers import DatetimeWithNanoseconds
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.field_path import FieldPath
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'rollout' / 'timeliness_participation.py'
SPEC = importlib.util.spec_from_file_location('timeliness_participation_rollout', SCRIPT)
assert SPEC is not None and SPEC.loader is not None

NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


@pytest.fixture
def helper(monkeypatch):
    module = importlib.util.module_from_spec(SPEC)
    monkeypatch.setitem(sys.modules, SPEC.name, module)
    SPEC.loader.exec_module(module)
    return module


# --- explicit in-memory double ----------------------------------------------------


class _Doc:
    def __init__(self):
        self.data = None
        self.update_time = None
        self._clock = 0

    def _touch(self):
        self._clock += 1
        moment = NOW + dt.timedelta(seconds=self._clock)
        self.update_time = DatetimeWithNanoseconds(
            moment.year,
            moment.month,
            moment.day,
            moment.hour,
            moment.minute,
            moment.second,
            moment.microsecond,
            tzinfo=dt.timezone.utc,
        )


class _Snapshot:
    def __init__(self, doc):
        self.exists = doc.data is not None
        self.update_time = doc.update_time
        self._doc = doc

    def to_dict(self):
        return dict(self._doc.data or {})


class _Ref:
    def __init__(self, doc):
        self._doc = doc

    def get(self, *, retry=None, timeout=None):
        return _Snapshot(self._doc)

    def _check(self, option):
        if option is None:
            return
        if self._doc.data is None:
            raise RuntimeError('NotFound')
        if option._last_update_time != self._doc.update_time:
            raise RuntimeError('FailedPrecondition: update_time mismatch')

    def update(self, values, option=None, retry=None):
        self._check(option)
        for field_path, value in values.items():
            parts = FieldPath.from_string(field_path).parts
            target = self._doc.data
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            name = parts[-1]
            if value is firestore.DELETE_FIELD:
                target.pop(name, None)
            else:
                target[name] = value
        self._doc._touch()
        return SimpleNamespace(update_time=self._doc.update_time)

    def create(self, values, retry=None):
        if self._doc.data is not None:
            raise RuntimeError('AlreadyExists')
        self._doc.data = dict(values)
        self._doc._touch()
        return SimpleNamespace(update_time=self._doc.update_time)

    def delete(self, option=None, retry=None):
        self._check(option)
        self._doc.data = None
        self._doc._touch()


class _Collection:
    def __init__(self, doc):
        self._doc = doc

    def document(self, name=None):
        return _Ref(self._doc)


class _Client:
    def __init__(self, doc):
        self._doc = doc

    def collection(self, name):
        return _Collection(self._doc)


class _Store:
    def __init__(self, namespace='batch_pipeline_prod', data=None):
        self.namespace = namespace
        self._doc = _Doc()
        self._doc.data = data
        if data is not None:
            self._doc._touch()
        self.client = _Client(self._doc)

    def seed(self, data):
        self._doc.data = dict(data)
        self._doc._touch()


@pytest.fixture
def store():
    return _Store()


def _prior(helper, store, *, plane='prod-omi-backend'):
    return helper.capture(store, plane=plane)


def _plan(helper, prior, *, operation_id='sca1649-op-1', until_seconds=900):
    return helper.build_plan(
        prior,
        operation_id=operation_id,
        created_at=NOW,
        until=NOW + dt.timedelta(seconds=until_seconds),
    )


# --- codec ------------------------------------------------------------------------


@pytest.mark.parametrize(
    'value',
    [
        None,
        True,
        False,
        0,
        -7,
        2**53 + 1,
        0.5,
        float('inf'),
        'text',
        b'\x00\xff',
        [1, 'two', None],
        {'nested': {'flag': True, 'count': 3}},
        dt.datetime(2026, 11, 16, 5, 0, 1, 123456, tzinfo=dt.timezone.utc),
        DatetimeWithNanoseconds(2026, 11, 16, 5, 0, tzinfo=dt.timezone.utc, nanosecond=123),
        firestore.GeoPoint(1.5, -2.5),
    ],
)
def test_tag_round_trip_is_lossless_and_type_preserving(helper, value):
    encoded = helper.tag(value)
    decoded = helper.untag(encoded)
    assert helper.tag(decoded) == encoded
    assert type(decoded) is type(value)


def test_tag_distinguishes_int_from_bool(helper):
    assert helper.tag(1) != helper.tag(True)
    assert helper.tag(True)['t'] == 'bool'


def test_reference_values_round_trip_at_top_level_and_nested_in_collections(helper):
    client = firestore.Client(project='demo-sca1649-unit', credentials=AnonymousCredentials())
    reference = client.document('related/one')
    value = {'top': reference, 'nested': [{'reference': reference}]}

    encoded = helper.tag(value)
    decoded = helper.untag(encoded, client=client)

    assert decoded['top'].path == reference.path
    assert decoded['nested'][0]['reference'].path == reference.path
    assert helper.tag(decoded) == encoded
    client.close()


def test_unsupported_value_is_refused(helper):
    with pytest.raises(TypeError):
        helper.tag(object())


# --- argument surface -------------------------------------------------------------


def test_server_dry_run_is_rejected(helper, capsys):
    with pytest.raises(SystemExit):
        helper.main(['apply', '--plan', 'p.json', '--dry-run=server'])
    assert 'no server-side dry-run' in capsys.readouterr().err


def test_non_loopback_emulator_host_is_refused(helper):
    with pytest.raises(helper.Refused, match='loopback'):
        helper.resolve_store('batch_pipeline_test_x', emulator_host='10.0.0.5:8085')


def test_emulator_mode_requires_a_test_namespace(helper):
    with pytest.raises(helper.Refused, match='batch_pipeline_test_'):
        helper.resolve_store('batch_pipeline_prod', emulator_host='127.0.0.1:8085')


def test_test_namespace_requires_emulator_mode(helper, monkeypatch):
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    with pytest.raises(helper.Refused, match='--dry-run=emulator'):
        helper.resolve_store('batch_pipeline_test_x')


def test_production_namespace_refuses_an_inherited_emulator_endpoint(helper, monkeypatch):
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:8085')
    with pytest.raises(helper.Refused, match='ambient FIRESTORE_EMULATOR_HOST'):
        helper.resolve_store('batch_pipeline_prod')


def test_production_apply_requires_a_receipt(helper, store, tmp_path, monkeypatch):
    prior = _prior(helper, store)
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps(_plan(helper, prior)))
    monkeypatch.setattr(helper, 'resolve_store', lambda namespace, emulator_host=None: store)
    assert helper.main(['apply', '--plan', str(plan_path)]) == helper.EXIT_REFUSED


# --- plan bounds ------------------------------------------------------------------


def test_plan_refuses_a_window_longer_than_1800s(helper, store):
    prior = _prior(helper, store)
    with pytest.raises(helper.Refused, match='1800'):
        _plan(helper, prior, until_seconds=1801)


def test_plan_refuses_a_non_increasing_window(helper, store):
    prior = _prior(helper, store)
    with pytest.raises(helper.Refused, match='after created_at'):
        _plan(helper, prior, until_seconds=0)


def test_plan_refuses_an_oversized_operation_id(helper, store):
    prior = _prior(helper, store)
    with pytest.raises(helper.Refused, match='128'):
        _plan(helper, prior, operation_id='x' * 129)


def test_plan_refuses_a_future_created_at_beyond_skew(helper, store):
    prior = _prior(helper, store)
    with pytest.raises(helper.Refused, match='clock-skew'):
        helper.build_plan(
            prior,
            operation_id='op',
            created_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=61),
            until=dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=900),
        )


# --- apply / restore / verify -----------------------------------------------------


def test_present_prior_apply_and_restore_are_exact(helper, store):
    extra = {
        'operator_note': 'prior',
        'count': 3,
        'flag': True,
        'stamp': DatetimeWithNanoseconds(2026, 1, 1, tzinfo=dt.timezone.utc, nanosecond=42),
        'blob': b'\x01',
        'nested': {'a': [1, None]},
        'a.b': 'literal dotted field',
        'tick`key': 'literal backtick field',
        r'back\\slash': 'literal backslash field',
    }
    store.seed(extra)
    prior = _prior(helper, store)
    plan = _plan(helper, prior)
    applied = helper.apply_plan(store, plan, mode='emulator')
    assert store._doc.data['operation_id'] == 'sca1649-op-1'
    assert store._doc.data['operator_note'] == 'prior'
    restored = helper.restore_prior(store, prior, applied, mode='emulator')
    assert restored['exact'] is True
    assert helper.verify_restored(store, prior)['restored'] is True
    assert store._doc.data == extra


def test_absent_prior_apply_creates_and_restore_deletes(helper, store):
    prior = _prior(helper, store)
    assert prior['exists'] is False
    plan = _plan(helper, prior)
    applied = helper.apply_plan(store, plan, mode='emulator')
    assert store._doc.data['target_plane'] == 'prod-omi-backend'
    restored = helper.restore_prior(store, prior, applied, mode='emulator')
    assert restored['exact'] is True
    assert store._doc.data is None
    assert helper.verify_restored(store, prior)['restored'] is True


def test_restore_removes_fields_added_after_apply(helper, store):
    store.seed({'kept': 1})
    prior = _prior(helper, store)
    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')
    store._doc.data['injected'] = 'concurrent'
    store._doc._touch()
    with pytest.raises(helper.Refused, match='update_time mismatch'):
        helper.restore_prior(store, prior, applied, mode='emulator')
    assert store._doc.data['injected'] == 'concurrent'


def test_apply_refuses_a_concurrent_writer_before_the_write(helper, store):
    store.seed({'kept': 1})
    prior = _prior(helper, store)
    plan = _plan(helper, prior)
    store.seed({'kept': 2})
    with pytest.raises(helper.Refused, match='update_time mismatch'):
        helper.apply_plan(store, plan, mode='production')
    assert store._doc.data == {'kept': 2}


def test_apply_refuses_to_issue_receipt_if_another_write_follows_its_write(helper, store, monkeypatch):
    store.seed({'kept': 1})
    prior = _prior(helper, store)
    plan = _plan(helper, prior)
    real_read = helper._read
    reads = 0

    def read_then_concurrent_write(current_store):
        nonlocal reads
        reads += 1
        if reads == 2:
            current_store._doc.data['concurrent'] = 'writer'
            current_store._doc._touch()
        return real_read(current_store)

    monkeypatch.setattr(helper, '_read', read_then_concurrent_write)
    with pytest.raises(helper.Refused, match='changed after apply'):
        helper.apply_plan(store, plan, mode='emulator')
    assert store._doc.data['concurrent'] == 'writer'
    assert store._doc.data['operation_id'] == 'sca1649-op-1'


def test_apply_refuses_a_create_when_the_document_appeared(helper, store):
    prior = _prior(helper, store)
    plan = _plan(helper, prior)
    store.seed({'kept': 1})
    with pytest.raises(helper.Refused, match='existence changed'):
        helper.apply_plan(store, plan, mode='production')


def test_restore_refuses_an_absent_document(helper, store):
    store.seed({'kept': 1})
    prior = _prior(helper, store)
    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')
    store._doc.data = None
    with pytest.raises(helper.Refused, match='absent'):
        helper.restore_prior(store, prior, applied, mode='emulator')


def test_restore_refuses_a_receipt_paired_with_a_different_capture(helper, store):
    store.seed({'kept': 1})
    original_prior = _prior(helper, store)
    applied = helper.apply_plan(store, _plan(helper, original_prior), mode='emulator')
    mismatched_prior = _prior(helper, store)
    state_after_apply = dict(store._doc.data)

    with pytest.raises(helper.Refused, match='does not match the supplied prior capture'):
        helper.restore_prior(store, mismatched_prior, applied, mode='emulator')

    assert store._doc.data == state_after_apply


def test_restore_refuses_a_receipt_for_a_different_target_or_mode(helper, store):
    store.seed({'kept': 1})
    prior = _prior(helper, store)
    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')
    state_after_apply = dict(store._doc.data)

    wrong_target = dict(applied, namespace='batch_pipeline_dev')
    with pytest.raises(helper.Refused, match='target does not match'):
        helper.restore_prior(store, prior, wrong_target, mode='emulator')

    with pytest.raises(helper.Refused, match='mode does not match'):
        helper.restore_prior(store, prior, applied, mode='production')

    assert store._doc.data == state_after_apply


def test_verify_restored_reports_exact_differences(helper, store):
    store.seed({'kept': 1, 'nested': {'a': True}})
    prior = _prior(helper, store)
    store.seed({'kept': 1, 'nested': {'a': False}})
    result = helper.verify_restored(store, prior)
    assert result['restored'] is False
    assert result['differences'] == ['nested']


def test_verify_restored_detects_existence_drift(helper, store):
    prior = _prior(helper, store)
    store.seed({'kept': 1})
    result = helper.verify_restored(store, prior)
    assert result['restored'] is False
    assert result['differences'] == ['existence']


def test_plan_binds_exactly_the_contracted_field_set(helper, store):
    prior = _prior(helper, store)
    plan = _plan(helper, prior)
    assert set(plan['fields']) == {'version', 'target_plane', 'created_at', 'suppressed_until', 'operation_id'}
    assert plan['fields']['target_plane'] == {'t': 'str', 'v': 'prod-omi-backend'}
    assert plan['prior']['exists'] is False


# --- complete prior capture identity binding --------------------------------------


def _state(store):
    return (store._doc.data, store._doc.update_time)


def test_apply_receipt_binds_the_complete_prior_identity(helper, store):
    store.seed({'kept': 1, 'nested': {'a': True}})
    prior = _prior(helper, store)
    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')

    recorded = applied['prior']
    assert recorded['namespace'] == prior['namespace']
    assert recorded['document'] == prior['document']
    assert recorded['exists'] is True
    assert recorded['update_time'] == prior['update_time']
    assert recorded['fields_sha256'] == prior['fields_sha256']
    assert recorded['identity_sha256'] == prior['identity_sha256']
    assert recorded['identity_sha256'] == helper.capture_identity(
        namespace=prior['namespace'],
        document=prior['document'],
        exists=prior['exists'],
        update_time=prior['update_time'],
        fields_sha256=prior['fields_sha256'],
    )


def test_restore_refuses_a_capture_whose_existence_was_flipped_to_absent(helper, store):
    """A present prior flipped to absent would select the conditional delete."""
    store.seed({'kept': 1})
    prior = _prior(helper, store)
    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')
    before = _state(store)

    # The minimal edit keeps the captured update_time; the identity digest also
    # refuses the stronger edit that clears it to look like a real absence.
    for tampered, reason in (
        (dict(prior, exists=False), 'records an update_time for an absent document'),
        (dict(prior, exists=False, update_time=None), 'identity does not match its own binding'),
    ):
        with pytest.raises(helper.Refused, match=reason):
            helper.restore_prior(store, tampered, applied, mode='emulator')
        assert _state(store) == before
    assert store._doc.data is not None


def test_restore_refuses_a_capture_whose_existence_was_flipped_to_present(helper, store):
    """An absent prior flipped to present would overwrite instead of delete."""
    prior = _prior(helper, store)
    assert prior['exists'] is False
    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')
    before = _state(store)

    tampered = dict(prior, exists=True, update_time=applied['applied_update_time'])
    with pytest.raises(helper.Refused, match='identity does not match its own binding'):
        helper.restore_prior(store, tampered, applied, mode='emulator')

    assert _state(store) == before
    assert store._doc.data is not None


def test_restore_refuses_a_capture_whose_update_time_was_tampered(helper, store):
    store.seed({'kept': 1})
    prior = _prior(helper, store)
    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')
    before = _state(store)

    tampered = dict(prior, update_time=applied['applied_update_time'])
    with pytest.raises(helper.Refused, match='identity does not match its own binding'):
        helper.restore_prior(store, tampered, applied, mode='emulator')

    assert _state(store) == before


def test_restore_refuses_a_capture_whose_fields_were_tampered(helper, store):
    store.seed({'kept': 1})
    prior = _prior(helper, store)
    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')
    before = _state(store)

    tampered = dict(prior, fields={'kept': {'t': 'int', 'v': '2'}})
    with pytest.raises(helper.Refused, match='fields do not match its digest'):
        helper.restore_prior(store, tampered, applied, mode='emulator')

    assert _state(store) == before


def test_restore_refuses_a_receipt_without_a_prior_binding(helper, store):
    store.seed({'kept': 1})
    prior = _prior(helper, store)
    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')
    before = _state(store)

    for stripped in ({k: v for k, v in applied.items() if k != 'prior'}, dict(applied, prior={})):
        with pytest.raises(helper.Refused, match='no prior capture binding'):
            helper.restore_prior(store, prior, stripped, mode='emulator')
        assert _state(store) == before


def test_restore_refuses_a_receipt_whose_prior_existence_disagrees(helper, store):
    store.seed({'kept': 1})
    prior = _prior(helper, store)
    applied = helper.apply_plan(store, _plan(helper, prior), mode='emulator')
    before = _state(store)

    tampered = dict(applied, prior=dict(applied['prior'], exists=False))
    with pytest.raises(helper.Refused, match='prior exists does not match'):
        helper.restore_prior(store, prior, tampered, mode='emulator')

    assert _state(store) == before


def test_plan_refuses_a_tampered_capture_before_any_write(helper, store):
    store.seed({'kept': 1})
    prior = _prior(helper, store)
    before = _state(store)

    with pytest.raises(helper.Refused, match='identity does not match its own binding'):
        _plan(helper, dict(prior, exists=False, update_time=None))

    assert _state(store) == before


def test_verify_restored_refuses_a_tampered_capture(helper, store):
    store.seed({'kept': 1})
    prior = _prior(helper, store)
    before = _state(store)

    with pytest.raises(helper.Refused, match='identity does not match its own binding'):
        helper.verify_restored(store, dict(prior, exists=False, update_time=None))

    assert _state(store) == before
