"""Contract (c) STT route fields on BatchUnitPolicy: additive, id-stable and rollback-safe (#22536)."""

from dataclasses import replace

import pytest

from config.policy import BatchUnitPolicy
from tests.unit.fixtures.pre_lane8_batch_unit_policy import PreLane8BatchUnitPolicy

ROUTE_FIELDS = ('stt_route', 'provider_reason', 'provider_service')

# An in-flight job['policy'] stamped by main 4f43b2d7 (E1, before #22536), verbatim.
PRE_LANE8_ROW = {
    'batch_allowlisted': False,
    'batch_enabled': True,
    'batch_percent': 25.0,
    'final_pass_authoritative': False,
    'final_pass_enabled': False,
    'live_admission_enabled': True,
    'live_record_enabled': True,
    'live_stt_retired': True,
    'policy_id': 'e5df36ea2c9aab0964bd630bcd13e5ce7b96cd7c0ab69ab6daf9248edce9f38d',
    'retire_percent': 10.0,
    'schema_version': 1,
    'source_role': 'sync',
}


def test_a_pre_field_row_keeps_its_stored_policy_id_and_decisions():
    policy = BatchUnitPolicy.from_dict(PRE_LANE8_ROW)
    assert policy.policy_id == PRE_LANE8_ROW['policy_id']
    assert tuple(getattr(policy, key) for key in ROUTE_FIELDS) == ('parakeet', 'none', 'none')
    old = PreLane8BatchUnitPolicy.from_dict(PRE_LANE8_ROW)
    assert {key: value for key, value in policy.to_dict().items() if key not in ROUTE_FIELDS} == old.to_dict()


@pytest.mark.parametrize(
    'values',
    [{}, {'batch_enabled': True, 'batch_percent': 100.0}, {'batch_enabled': True, 'batch_percent': 5.0}],
)
def test_default_route_hashes_exactly_like_the_pre_field_shape(values):
    assert BatchUnitPolicy(**values).policy_id == PreLane8BatchUnitPolicy(**values).policy_id


def test_a_set_route_field_changes_the_identity():
    base = BatchUnitPolicy(batch_enabled=True, batch_percent=100.0)
    ids = {
        base.policy_id,
        replace(base, provider_reason='byok').policy_id,
        replace(
            base, stt_route='provider', provider_reason='unsupported_language', provider_service='modulate'
        ).policy_id,
        replace(base, stt_route='provider', provider_reason='byok', provider_service='modulate').policy_id,
    }
    assert len(ids) == 4
    stamped = replace(base, provider_reason='byok')
    assert BatchUnitPolicy.from_dict(stamped.to_dict()).policy_id == stamped.policy_id


def test_rollback_reader_ignores_the_new_fields_and_keeps_a_default_row_id():
    """A revert to 4f43b2d7 reads rows #22536 wrote: unknown keys are ignored, decisions are kept."""
    written = BatchUnitPolicy(batch_enabled=True, batch_percent=25.0, source_role='sync')
    old = PreLane8BatchUnitPolicy.from_dict(written.to_dict())
    assert old.policy_id == written.policy_id
    assert old.to_dict() == {key: value for key, value in written.to_dict().items() if key not in ROUTE_FIELDS}
    byok = PreLane8BatchUnitPolicy.from_dict(replace(written, provider_reason='byok').to_dict())
    assert byok.batch_enabled and byok.batch_percent == 25.0  # admission decisions survive the rollback
