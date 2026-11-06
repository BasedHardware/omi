"""Materialized stage-by-stage anchor-pin matrix.

`test_batch_anchor_stage_pin_parity.py` states the pin contract once with
parametrized tables; this file materializes every (stage, scenario) cell as an
explicit test definition so each stage's policy part — its own fields, own
defaults, own provenance — is pinned by a named test. The shared helpers and
the fixtures live in the parity module.
"""

import pytest

from config.policy.stages import STAGE_TYPES
from dataclasses import replace
from database.batch_pipeline_policy import PROCESS_ENVIRONMENT, AnchorStagePin
from tests.unit.test_batch_anchor_stage_pin_parity import (
    commit_policy,
    commit_stage,
    flags_for,
    make_store,
    pin_broken_store,
    policy_buffered,
    stage_buffered,
)

STAGES = ('first_summary', 'projection', 'recovery', 'scheduler')


def test_first_summary_sibling_stage_write_set_is_the_job_row_only(unit):
    writes, _, pins, _ = stage_buffered(unit, 'tail', 'first_summary')
    assert set(writes) == {('jobs', 'tail')}, 'the anchor row stays out of the transition write set'
    assert pins[0].segment_id == 'head'
    assert pins[0].stage == 'first_summary'


def test_first_summary_descriptor_part_equals_the_resolved_policy(unit):
    _, _, pins, policy = stage_buffered(unit, 'tail', 'first_summary')
    assert pins[0].part == policy.to_dict()
    assert pins[0].source == 'fallback'
    assert pins[0].part['source_role'] == policy.to_dict()['source_role']


def test_first_summary_anchor_self_stage_writes_one_row_with_no_descriptor(unit):
    writes, _, pins, _ = stage_buffered(unit, 'head', 'first_summary')
    assert set(writes) == {('jobs', 'head')}
    assert pins == []


def test_first_summary_flush_pins_the_canonical_anchor_row(unit):
    _, _, pins, policy = stage_buffered(unit, 'tail', 'first_summary')
    assert policies_flush(unit, pins) == 1
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts']['first_summary'] == policy.to_dict()
    assert anchor['policy_part_sources']['first_summary'] == 'fallback'


def test_first_summary_second_flush_of_a_pinned_anchor_never_overwrites(unit):
    _, _, first, _ = stage_buffered(unit, 'tail', 'first_summary')
    assert policies_flush(unit, list(first)) == 1
    rewritten = replace(STAGE_TYPES['first_summary'](), source_role='later-env')
    duplicate = AnchorStagePin('head', 'first_summary', rewritten.to_dict(), 'fallback')
    before = unit.get('jobs', 'head')['policy_parts']['first_summary']
    assert policies_flush(unit, [duplicate]) == 0
    assert unit.get('jobs', 'head')['policy_parts']['first_summary'] == before


def test_first_summary_flush_defers_when_the_anchor_holds_a_partial_stamp(unit):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'first_summary': {}}
    _, _, pins, _ = stage_buffered(unit, 'tail', 'first_summary')
    assert policies_flush(unit, pins) == 0
    assert unit.get('jobs', 'head')['policy_parts']['first_summary'] == {}


def test_first_summary_pinned_anchor_copies_to_the_sibling_without_a_descriptor(unit):
    pinned = replace(STAGE_TYPES['first_summary'](), source_role='pin-canonical')
    unit.rows[('jobs', 'head')]['policy_parts'] = {'first_summary': pinned.to_dict()}
    writes, _, pins, policy = stage_buffered(unit, 'tail', 'first_summary')
    assert set(writes) == {('jobs', 'tail')}
    assert pins == []
    assert policy.to_dict() == pinned.to_dict()


def test_first_summary_pinned_part_converges_later_siblings_without_resolution(unit, monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'pin-serving')
    _, _, pins, first = stage_buffered(unit, 'tail', 'first_summary')
    assert policies_flush(unit, pins) == 1
    monkeypatch.setenv('K_SERVICE', 'later-role')
    monkeypatch.setattr(
        IMPORTED_POLICIES,
        'resolve_stage_policy',
        lambda *a, **k: pytest.fail('re-resolved after the pin existed'),
    )
    _, _, _, second = stage_buffered(unit, 'mid', 'first_summary')
    assert second.to_dict() == first.to_dict()


def test_first_summary_recorded_whole_unit_policy_guards_the_pin_provenance(unit):
    recorded = replace(STAGE_TYPES['first_summary'](), source_role='recorded-owner')
    unit.rows[('jobs', 'head')]['policy'] = recorded.to_dict()
    unit.rows[('jobs', 'head')]['policy_source'] = 'recorded'
    _, _, pins, _ = stage_buffered(unit, 'tail', 'first_summary')
    assert policies_flush(unit, pins) == 1
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts']['first_summary']
    assert 'policy_part_sources' not in anchor


def test_first_summary_pin_failure_is_deferred_and_names_the_stage(unit, caplog):
    pins = []

    def body(tx):
        job = tx.get('jobs', 'tail')
        return IMPORTED_POLICIES.stage_in_transaction(tx, job, 'first_summary', pins=pins)

    unit.run(body)
    witness = pin_broken_store(unit)
    with caplog.at_level('WARNING', logger='database.batch_pipeline_policy'):
        assert policies_flush(witness, pins) == 0
    assert any('outcome=deferred' in r.getMessage() and 'stage=first_summary' in r.getMessage() for r in caplog.records)
    assert unit.get('jobs', 'tail')['policy_parts']['first_summary'], 'the transition row stays durable'


def test_first_summary_wrapper_refuses_an_absent_part_without_server_flags(unit):
    from database.batch_pipeline_policy import UnpinnedPolicyRefused, load_stage_policy

    with pytest.raises(UnpinnedPolicyRefused) as refused:
        load_stage_policy(unit, 'tail', 'first_summary', server_flags=None)
    assert refused.value.stage == 'first_summary'
    assert unit.get('jobs', 'tail').get('policy_parts') is None


def test_first_summary_wrapper_stages_the_job_and_pins_the_anchor(unit, monkeypatch):
    from database.batch_pipeline_policy import load_stage_policy

    monkeypatch.setenv('K_SERVICE', 'pin-serving')
    _, policy = load_stage_policy(unit, 'tail', 'first_summary')
    assert unit.get('jobs', 'tail')['policy_parts']['first_summary'] == policy.to_dict()
    assert unit.get('jobs', 'head')['policy_parts']['first_summary'] == policy.to_dict()


def test_first_summary_recorded_job_part_returns_before_any_anchor_read(unit):
    own = replace(STAGE_TYPES['first_summary'](), source_role='own-row')
    unit.rows[('jobs', 'tail')]['policy_parts'] = {'first_summary': own.to_dict()}
    _, gets, pins, policy = stage_buffered(unit, 'tail', 'first_summary')
    assert pins == []
    assert policy.to_dict() == own.to_dict()
    assert all(key[1] != 'head' for key in gets)


def test_first_summary_candidate_cache_resolves_once_per_anchor_and_stage(unit, monkeypatch):
    resolve = IMPORTED_POLICIES.resolve_stage_policy
    calls = []
    monkeypatch.setattr(
        IMPORTED_POLICIES, 'resolve_stage_policy', lambda uid, st, **k: calls.append(st) or resolve(uid, st, **k)
    )
    candidates = {}
    stage_buffered(unit, 'tail', 'first_summary', candidates=candidates)
    stage_buffered(unit, 'mid', 'first_summary', candidates=candidates)
    assert calls == ['first_summary']


def test_first_summary_caller_without_pins_keeps_the_in_transaction_anchor_write(unit):
    writes, _, _, _ = stage_buffered(unit, 'tail', 'first_summary', pins=None)
    assert set(writes) == {('jobs', 'head'), ('jobs', 'tail')}
    for sid in ('head', 'tail'):
        assert writes[('jobs', sid)]['policy_parts']['first_summary']


def test_first_summary_partial_anchor_stamp_uses_defaults_without_env_or_descriptor(unit, monkeypatch):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'first_summary': {}}
    monkeypatch.setattr(IMPORTED_POLICIES, 'resolve_stage_policy', lambda *a, **k: pytest.fail('re-resolved'))
    writes, _, pins, policy = stage_buffered(unit, 'tail', 'first_summary')
    assert set(writes) == {('jobs', 'tail')}
    assert pins == []
    assert policy == STAGE_TYPES['first_summary']()


def test_first_summary_matrix_absent_part_serving_resolution_pins_the_anchor(unit, monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'matrix-serving')
    policy, pinned, pins = commit_stage(unit, 'tail', 'first_summary')
    assert pinned == 1
    assert unit.get('jobs', 'head')['policy_parts']['first_summary'] == policy.to_dict()
    assert unit.get('jobs', 'head')['policy_part_sources']['first_summary'] == 'fallback'


def test_first_summary_matrix_absent_part_operator_mapping_pins_its_own_provenance(unit):
    flags = {'K_SERVICE': 'operator-role'}
    _, _, pins, policy = stage_buffered(unit, 'tail', 'first_summary', server_flags=flags)
    assert pins[0].source == 'operator_server_flags'
    assert policies_flush(unit, pins) == 1
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts']['first_summary'] == policy.to_dict()
    assert anchor['policy_part_sources']['first_summary'] == 'operator_server_flags'


def test_first_summary_matrix_absent_part_without_authority_is_refused_before_writes(unit):
    import pytest as _pytest

    with _pytest.raises(Exception):
        stage_buffered(unit, 'tail', 'first_summary', server_flags=None)
    assert unit.get('jobs', 'tail').get('policy_parts') is None
    assert unit.get('jobs', 'head').get('policy_parts') is None


def test_first_summary_matrix_pinned_part_serving_copy_keeps_the_stamp(unit):
    pinned = replace(STAGE_TYPES['first_summary'](), source_role='pin-canonical')
    unit.rows[('jobs', 'head')]['policy_parts'] = {'first_summary': pinned.to_dict()}
    unit.rows[('jobs', 'head')]['policy_part_sources'] = {'first_summary': 'fallback'}
    policy, pinned_count, pins = commit_stage(unit, 'tail', 'first_summary')
    assert pinned_count == 0 and pins == []
    assert policy.to_dict() == pinned.to_dict()
    assert unit.get('jobs', 'tail')['policy_part_sources']['first_summary'] == 'fallback'


def test_first_summary_matrix_partial_stamp_operator_mapping_defaults_without_env(unit, monkeypatch):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'first_summary': {}}
    monkeypatch.setattr(IMPORTED_POLICIES, 'resolve_stage_policy', lambda *a, **k: pytest.fail('re-resolved'))
    flags = {'K_SERVICE': 'operator-role'}
    _, _, pins, _ = stage_buffered(unit, 'tail', 'first_summary', server_flags=flags)
    assert pins == []
    assert unit.get('jobs', 'head')['policy_parts']['first_summary'] == {}


def test_first_summary_flush_defers_when_the_anchor_row_is_gone(unit):
    _, _, pins, _ = stage_buffered(unit, 'tail', 'first_summary')
    unit.rows.pop(('jobs', 'head'))
    assert policies_flush(unit, pins) == 0
    assert pins == []


def test_first_summary_pin_transaction_carries_the_static_label(unit):
    labels = []

    class Witness:
        def run(self, body, *, operation=None):
            labels.append(operation)
            return unit.run(body, operation=operation)

        def __getattr__(self, name):
            return getattr(unit, name)

    _, _, pins, _ = stage_buffered(unit, 'tail', 'first_summary')
    assert policies_flush(Witness(), pins) == 1
    assert labels == ['batch_anchor_stage_pin']


def test_first_summary_duplicate_descriptors_collapse_into_one_pin_transaction(unit):
    _, _, pins, _ = stage_buffered(unit, 'tail', 'first_summary')
    stage_buffered(unit, 'tail', 'first_summary', pins=pins)
    before = unit.transactions
    assert policies_flush(unit, pins) == 1
    assert unit.transactions == before + 1


def test_first_summary_pin_write_respects_the_privacy_fence(unit):
    pins = []

    def body(tx):
        job = tx.get('jobs', 'tail')
        return IMPORTED_POLICIES.stage_in_transaction(tx, job, 'first_summary', pins=pins)

    unit.run(body)
    unit.customer.block_privacy('owner')
    descriptor = AnchorStagePin('head', 'first_summary', replace(STAGE_TYPES['first_summary']()).to_dict(), 'fallback')
    assert policies_flush(unit, [descriptor]) == 0
    assert unit.get('jobs', 'head').get('policy_parts') is None
    assert unit.get('jobs', 'tail')['policy_parts']['first_summary'], 'the transition row stays durable'


def test_first_summary_flush_needs_only_the_store_run_protocol(unit):
    runs = []

    class Tiny:
        def run(self, body, *, operation=None):
            runs.append(operation)
            return unit.run(body, operation=operation)

    _, _, pins, _ = stage_buffered(unit, 'tail', 'first_summary')
    assert policies_flush(Tiny(), pins) == 1
    assert runs == ['batch_anchor_stage_pin']


def test_first_summary_descriptor_is_a_frozen_value_object():
    descriptor = AnchorStagePin('head', 'first_summary', {}, 'fallback')
    assert descriptor == AnchorStagePin('head', 'first_summary', {}, 'fallback')
    with pytest.raises(Exception):
        descriptor.stage = 'other'


def test_first_summary_absent_part_without_authority_refuses_the_sibling_stage(unit):
    with pytest.raises(Exception):
        stage_buffered(unit, 'tail', 'first_summary', server_flags=None)
    assert unit.get('jobs', 'tail').get('policy_parts') is None


def test_first_summary_anchor_self_stage_operator_mapping_records_operator_provenance(unit):
    writes, _, pins, _ = stage_buffered(unit, 'head', 'first_summary', server_flags={'K_SERVICE': 'operator-role'})
    assert set(writes) == {('jobs', 'head')}
    assert writes[('jobs', 'head')]['policy_part_sources']['first_summary'] == 'operator_server_flags'
    assert pins == []


def test_first_summary_pre_pin_siblings_converge_on_their_next_touch(unit, monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'first-role')
    _, _, first_pins, first_part = stage_buffered(unit, 'tail', 'first_summary')
    monkeypatch.setenv('K_SERVICE', 'second-role')
    _, _, second_pins, _ = stage_buffered(unit, 'mid', 'first_summary')
    assert policies_flush(unit, first_pins + second_pins) == 1
    anchor_part = unit.get('jobs', 'head')['policy_parts']['first_summary']
    assert anchor_part == first_part.to_dict(), 'the first emitted pin wins'
    monkeypatch.setattr(IMPORTED_POLICIES, 'resolve_stage_policy', lambda *a, **k: pytest.fail('re-resolved'))
    _, _, _, converged = stage_buffered(unit, 'mid', 'first_summary')
    assert converged.to_dict() == anchor_part


def test_first_summary_pinned_part_keeps_the_stage_stable_default_identity(unit):
    _, _, pins, policy = stage_buffered(unit, 'tail', 'first_summary')
    assert pins[0].part['source_role'] == policy.to_dict()['source_role']
    assert policies_flush(unit, pins) == 1


def test_first_summary_matrix_pinned_part_operator_mapping_copies_the_stamp(unit):
    pinned = replace(STAGE_TYPES['first_summary'](), source_role='pin-canonical')
    unit.rows[('jobs', 'head')]['policy_parts'] = {'first_summary': pinned.to_dict()}
    flags = {'K_SERVICE': 'operator-role'}
    _, _, pins, policy = stage_buffered(unit, 'tail', 'first_summary', server_flags=flags)
    assert pins == []
    assert policy.to_dict() == pinned.to_dict()


def test_first_summary_matrix_partial_stamp_without_authority_still_uses_defaults(unit):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'first_summary': {}}
    _, _, pins, policy = stage_buffered(unit, 'tail', 'first_summary', server_flags=None)
    assert pins == []
    assert policy == STAGE_TYPES['first_summary']()


def test_first_summary_self_stage_serving_end_state(unit, monkeypatch):
    lone = make_store(siblings=('lone',))
    lone.rows[('jobs', 'lone')]['projection_binding']['segment_ids'] = ('lone',)
    monkeypatch.setenv('K_SERVICE', 'matrix-serving')
    policy, pinned, pins = commit_stage(lone, 'lone', 'first_summary', server_flags=flags_for('serving'))
    row = lone.get('jobs', 'lone')
    assert pinned == 0 and pins == []
    assert row['policy_parts']['first_summary'] == policy.to_dict()
    assert row['policy_part_sources']['first_summary'] == 'fallback'


def test_first_summary_self_stage_mapping_end_state(unit):
    lone = make_store(siblings=('lone',))
    lone.rows[('jobs', 'lone')]['projection_binding']['segment_ids'] = ('lone',)
    policy, pinned, pins = commit_stage(lone, 'lone', 'first_summary', server_flags=flags_for('mapping'))
    row = lone.get('jobs', 'lone')
    assert pinned == 0 and pins == []
    assert row['policy_parts']['first_summary'] == policy.to_dict()
    assert row['policy_part_sources']['first_summary'] == 'operator_server_flags'


def test_first_summary_self_stage_none_end_state(unit):
    lone = make_store(siblings=('lone',))
    lone.rows[('jobs', 'lone')]['projection_binding']['segment_ids'] = ('lone',)
    import pytest as _pytest

    with _pytest.raises(Exception):
        stage_buffered(lone, 'lone', 'first_summary', server_flags=None)
    assert lone.get('jobs', 'lone').get('policy_parts') is None


def test_projection_sibling_stage_write_set_is_the_job_row_only(unit):
    writes, _, pins, _ = stage_buffered(unit, 'tail', 'projection')
    assert set(writes) == {('jobs', 'tail')}, 'the anchor row stays out of the transition write set'
    assert pins[0].segment_id == 'head'
    assert pins[0].stage == 'projection'


def test_projection_descriptor_part_equals_the_resolved_policy(unit):
    _, _, pins, policy = stage_buffered(unit, 'tail', 'projection')
    assert pins[0].part == policy.to_dict()
    assert pins[0].source == 'fallback'
    assert pins[0].part['source_role'] == policy.to_dict()['source_role']


def test_projection_anchor_self_stage_writes_one_row_with_no_descriptor(unit):
    writes, _, pins, _ = stage_buffered(unit, 'head', 'projection')
    assert set(writes) == {('jobs', 'head')}
    assert pins == []


def test_projection_flush_pins_the_canonical_anchor_row(unit):
    _, _, pins, policy = stage_buffered(unit, 'tail', 'projection')
    assert policies_flush(unit, pins) == 1
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts']['projection'] == policy.to_dict()
    assert anchor['policy_part_sources']['projection'] == 'fallback'


def test_projection_second_flush_of_a_pinned_anchor_never_overwrites(unit):
    _, _, first, _ = stage_buffered(unit, 'tail', 'projection')
    assert policies_flush(unit, list(first)) == 1
    rewritten = replace(STAGE_TYPES['projection'](), source_role='later-env')
    duplicate = AnchorStagePin('head', 'projection', rewritten.to_dict(), 'fallback')
    before = unit.get('jobs', 'head')['policy_parts']['projection']
    assert policies_flush(unit, [duplicate]) == 0
    assert unit.get('jobs', 'head')['policy_parts']['projection'] == before


def test_projection_flush_defers_when_the_anchor_holds_a_partial_stamp(unit):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'projection': {}}
    _, _, pins, _ = stage_buffered(unit, 'tail', 'projection')
    assert policies_flush(unit, pins) == 0
    assert unit.get('jobs', 'head')['policy_parts']['projection'] == {}


def test_projection_pinned_anchor_copies_to_the_sibling_without_a_descriptor(unit):
    pinned = replace(STAGE_TYPES['projection'](), source_role='pin-canonical')
    unit.rows[('jobs', 'head')]['policy_parts'] = {'projection': pinned.to_dict()}
    writes, _, pins, policy = stage_buffered(unit, 'tail', 'projection')
    assert set(writes) == {('jobs', 'tail')}
    assert pins == []
    assert policy.to_dict() == pinned.to_dict()


def test_projection_pinned_part_converges_later_siblings_without_resolution(unit, monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'pin-serving')
    _, _, pins, first = stage_buffered(unit, 'tail', 'projection')
    assert policies_flush(unit, pins) == 1
    monkeypatch.setenv('K_SERVICE', 'later-role')
    monkeypatch.setattr(
        IMPORTED_POLICIES,
        'resolve_stage_policy',
        lambda *a, **k: pytest.fail('re-resolved after the pin existed'),
    )
    _, _, _, second = stage_buffered(unit, 'mid', 'projection')
    assert second.to_dict() == first.to_dict()


def test_projection_recorded_whole_unit_policy_guards_the_pin_provenance(unit):
    recorded = replace(STAGE_TYPES['projection'](), source_role='recorded-owner')
    unit.rows[('jobs', 'head')]['policy'] = recorded.to_dict()
    unit.rows[('jobs', 'head')]['policy_source'] = 'recorded'
    _, _, pins, _ = stage_buffered(unit, 'tail', 'projection')
    assert policies_flush(unit, pins) == 1
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts']['projection']
    assert 'policy_part_sources' not in anchor


def test_projection_pin_failure_is_deferred_and_names_the_stage(unit, caplog):
    pins = []

    def body(tx):
        job = tx.get('jobs', 'tail')
        return IMPORTED_POLICIES.stage_in_transaction(tx, job, 'projection', pins=pins)

    unit.run(body)
    witness = pin_broken_store(unit)
    with caplog.at_level('WARNING', logger='database.batch_pipeline_policy'):
        assert policies_flush(witness, pins) == 0
    assert any('outcome=deferred' in r.getMessage() and 'stage=projection' in r.getMessage() for r in caplog.records)
    assert unit.get('jobs', 'tail')['policy_parts']['projection'], 'the transition row stays durable'


def test_projection_wrapper_refuses_an_absent_part_without_server_flags(unit):
    from database.batch_pipeline_policy import UnpinnedPolicyRefused, load_stage_policy

    with pytest.raises(UnpinnedPolicyRefused) as refused:
        load_stage_policy(unit, 'tail', 'projection', server_flags=None)
    assert refused.value.stage == 'projection'
    assert unit.get('jobs', 'tail').get('policy_parts') is None


def test_projection_wrapper_stages_the_job_and_pins_the_anchor(unit, monkeypatch):
    from database.batch_pipeline_policy import load_stage_policy

    monkeypatch.setenv('K_SERVICE', 'pin-serving')
    _, policy = load_stage_policy(unit, 'tail', 'projection')
    assert unit.get('jobs', 'tail')['policy_parts']['projection'] == policy.to_dict()
    assert unit.get('jobs', 'head')['policy_parts']['projection'] == policy.to_dict()


def test_projection_recorded_job_part_returns_before_any_anchor_read(unit):
    own = replace(STAGE_TYPES['projection'](), source_role='own-row')
    unit.rows[('jobs', 'tail')]['policy_parts'] = {'projection': own.to_dict()}
    _, gets, pins, policy = stage_buffered(unit, 'tail', 'projection')
    assert pins == []
    assert policy.to_dict() == own.to_dict()
    assert all(key[1] != 'head' for key in gets)


def test_projection_candidate_cache_resolves_once_per_anchor_and_stage(unit, monkeypatch):
    resolve = IMPORTED_POLICIES.resolve_stage_policy
    calls = []
    monkeypatch.setattr(
        IMPORTED_POLICIES, 'resolve_stage_policy', lambda uid, st, **k: calls.append(st) or resolve(uid, st, **k)
    )
    candidates = {}
    stage_buffered(unit, 'tail', 'projection', candidates=candidates)
    stage_buffered(unit, 'mid', 'projection', candidates=candidates)
    assert calls == ['projection']


def test_projection_caller_without_pins_keeps_the_in_transaction_anchor_write(unit):
    writes, _, _, _ = stage_buffered(unit, 'tail', 'projection', pins=None)
    assert set(writes) == {('jobs', 'head'), ('jobs', 'tail')}
    for sid in ('head', 'tail'):
        assert writes[('jobs', sid)]['policy_parts']['projection']


def test_projection_partial_anchor_stamp_uses_defaults_without_env_or_descriptor(unit, monkeypatch):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'projection': {}}
    monkeypatch.setattr(IMPORTED_POLICIES, 'resolve_stage_policy', lambda *a, **k: pytest.fail('re-resolved'))
    writes, _, pins, policy = stage_buffered(unit, 'tail', 'projection')
    assert set(writes) == {('jobs', 'tail')}
    assert pins == []
    assert policy == STAGE_TYPES['projection']()


def test_projection_matrix_absent_part_serving_resolution_pins_the_anchor(unit, monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'matrix-serving')
    policy, pinned, pins = commit_stage(unit, 'tail', 'projection')
    assert pinned == 1
    assert unit.get('jobs', 'head')['policy_parts']['projection'] == policy.to_dict()
    assert unit.get('jobs', 'head')['policy_part_sources']['projection'] == 'fallback'


def test_projection_matrix_absent_part_operator_mapping_pins_its_own_provenance(unit):
    flags = {'K_SERVICE': 'operator-role'}
    _, _, pins, policy = stage_buffered(unit, 'tail', 'projection', server_flags=flags)
    assert pins[0].source == 'operator_server_flags'
    assert policies_flush(unit, pins) == 1
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts']['projection'] == policy.to_dict()
    assert anchor['policy_part_sources']['projection'] == 'operator_server_flags'


def test_projection_matrix_absent_part_without_authority_is_refused_before_writes(unit):
    import pytest as _pytest

    with _pytest.raises(Exception):
        stage_buffered(unit, 'tail', 'projection', server_flags=None)
    assert unit.get('jobs', 'tail').get('policy_parts') is None
    assert unit.get('jobs', 'head').get('policy_parts') is None


def test_projection_matrix_pinned_part_serving_copy_keeps_the_stamp(unit):
    pinned = replace(STAGE_TYPES['projection'](), source_role='pin-canonical')
    unit.rows[('jobs', 'head')]['policy_parts'] = {'projection': pinned.to_dict()}
    unit.rows[('jobs', 'head')]['policy_part_sources'] = {'projection': 'fallback'}
    policy, pinned_count, pins = commit_stage(unit, 'tail', 'projection')
    assert pinned_count == 0 and pins == []
    assert policy.to_dict() == pinned.to_dict()
    assert unit.get('jobs', 'tail')['policy_part_sources']['projection'] == 'fallback'


def test_projection_matrix_partial_stamp_operator_mapping_defaults_without_env(unit, monkeypatch):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'projection': {}}
    monkeypatch.setattr(IMPORTED_POLICIES, 'resolve_stage_policy', lambda *a, **k: pytest.fail('re-resolved'))
    flags = {'K_SERVICE': 'operator-role'}
    _, _, pins, _ = stage_buffered(unit, 'tail', 'projection', server_flags=flags)
    assert pins == []
    assert unit.get('jobs', 'head')['policy_parts']['projection'] == {}


def test_projection_flush_defers_when_the_anchor_row_is_gone(unit):
    _, _, pins, _ = stage_buffered(unit, 'tail', 'projection')
    unit.rows.pop(('jobs', 'head'))
    assert policies_flush(unit, pins) == 0
    assert pins == []


def test_projection_pin_transaction_carries_the_static_label(unit):
    labels = []

    class Witness:
        def run(self, body, *, operation=None):
            labels.append(operation)
            return unit.run(body, operation=operation)

        def __getattr__(self, name):
            return getattr(unit, name)

    _, _, pins, _ = stage_buffered(unit, 'tail', 'projection')
    assert policies_flush(Witness(), pins) == 1
    assert labels == ['batch_anchor_stage_pin']


def test_projection_duplicate_descriptors_collapse_into_one_pin_transaction(unit):
    _, _, pins, _ = stage_buffered(unit, 'tail', 'projection')
    stage_buffered(unit, 'tail', 'projection', pins=pins)
    before = unit.transactions
    assert policies_flush(unit, pins) == 1
    assert unit.transactions == before + 1


def test_projection_pin_write_respects_the_privacy_fence(unit):
    pins = []

    def body(tx):
        job = tx.get('jobs', 'tail')
        return IMPORTED_POLICIES.stage_in_transaction(tx, job, 'projection', pins=pins)

    unit.run(body)
    unit.customer.block_privacy('owner')
    descriptor = AnchorStagePin('head', 'projection', replace(STAGE_TYPES['projection']()).to_dict(), 'fallback')
    assert policies_flush(unit, [descriptor]) == 0
    assert unit.get('jobs', 'head').get('policy_parts') is None
    assert unit.get('jobs', 'tail')['policy_parts']['projection'], 'the transition row stays durable'


def test_projection_flush_needs_only_the_store_run_protocol(unit):
    runs = []

    class Tiny:
        def run(self, body, *, operation=None):
            runs.append(operation)
            return unit.run(body, operation=operation)

    _, _, pins, _ = stage_buffered(unit, 'tail', 'projection')
    assert policies_flush(Tiny(), pins) == 1
    assert runs == ['batch_anchor_stage_pin']


def test_projection_descriptor_is_a_frozen_value_object():
    descriptor = AnchorStagePin('head', 'projection', {}, 'fallback')
    assert descriptor == AnchorStagePin('head', 'projection', {}, 'fallback')
    with pytest.raises(Exception):
        descriptor.stage = 'other'


def test_projection_absent_part_without_authority_refuses_the_sibling_stage(unit):
    with pytest.raises(Exception):
        stage_buffered(unit, 'tail', 'projection', server_flags=None)
    assert unit.get('jobs', 'tail').get('policy_parts') is None


def test_projection_anchor_self_stage_operator_mapping_records_operator_provenance(unit):
    writes, _, pins, _ = stage_buffered(unit, 'head', 'projection', server_flags={'K_SERVICE': 'operator-role'})
    assert set(writes) == {('jobs', 'head')}
    assert writes[('jobs', 'head')]['policy_part_sources']['projection'] == 'operator_server_flags'
    assert pins == []


def test_projection_pre_pin_siblings_converge_on_their_next_touch(unit, monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'first-role')
    _, _, first_pins, first_part = stage_buffered(unit, 'tail', 'projection')
    monkeypatch.setenv('K_SERVICE', 'second-role')
    _, _, second_pins, _ = stage_buffered(unit, 'mid', 'projection')
    assert policies_flush(unit, first_pins + second_pins) == 1
    anchor_part = unit.get('jobs', 'head')['policy_parts']['projection']
    assert anchor_part == first_part.to_dict(), 'the first emitted pin wins'
    monkeypatch.setattr(IMPORTED_POLICIES, 'resolve_stage_policy', lambda *a, **k: pytest.fail('re-resolved'))
    _, _, _, converged = stage_buffered(unit, 'mid', 'projection')
    assert converged.to_dict() == anchor_part


def test_projection_pinned_part_keeps_the_stage_stable_default_identity(unit):
    _, _, pins, policy = stage_buffered(unit, 'tail', 'projection')
    assert pins[0].part['source_role'] == policy.to_dict()['source_role']
    assert policies_flush(unit, pins) == 1


def test_projection_matrix_pinned_part_operator_mapping_copies_the_stamp(unit):
    pinned = replace(STAGE_TYPES['projection'](), source_role='pin-canonical')
    unit.rows[('jobs', 'head')]['policy_parts'] = {'projection': pinned.to_dict()}
    flags = {'K_SERVICE': 'operator-role'}
    _, _, pins, policy = stage_buffered(unit, 'tail', 'projection', server_flags=flags)
    assert pins == []
    assert policy.to_dict() == pinned.to_dict()


def test_projection_matrix_partial_stamp_without_authority_still_uses_defaults(unit):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'projection': {}}
    _, _, pins, policy = stage_buffered(unit, 'tail', 'projection', server_flags=None)
    assert pins == []
    assert policy == STAGE_TYPES['projection']()


def test_projection_self_stage_serving_end_state(unit, monkeypatch):
    lone = make_store(siblings=('lone',))
    lone.rows[('jobs', 'lone')]['projection_binding']['segment_ids'] = ('lone',)
    monkeypatch.setenv('K_SERVICE', 'matrix-serving')
    policy, pinned, pins = commit_stage(lone, 'lone', 'projection', server_flags=flags_for('serving'))
    row = lone.get('jobs', 'lone')
    assert pinned == 0 and pins == []
    assert row['policy_parts']['projection'] == policy.to_dict()
    assert row['policy_part_sources']['projection'] == 'fallback'


def test_projection_self_stage_mapping_end_state(unit):
    lone = make_store(siblings=('lone',))
    lone.rows[('jobs', 'lone')]['projection_binding']['segment_ids'] = ('lone',)
    policy, pinned, pins = commit_stage(lone, 'lone', 'projection', server_flags=flags_for('mapping'))
    row = lone.get('jobs', 'lone')
    assert pinned == 0 and pins == []
    assert row['policy_parts']['projection'] == policy.to_dict()
    assert row['policy_part_sources']['projection'] == 'operator_server_flags'


def test_projection_self_stage_none_end_state(unit):
    lone = make_store(siblings=('lone',))
    lone.rows[('jobs', 'lone')]['projection_binding']['segment_ids'] = ('lone',)
    import pytest as _pytest

    with _pytest.raises(Exception):
        stage_buffered(lone, 'lone', 'projection', server_flags=None)
    assert lone.get('jobs', 'lone').get('policy_parts') is None


def test_recovery_sibling_stage_write_set_is_the_job_row_only(unit):
    writes, _, pins, _ = stage_buffered(unit, 'tail', 'recovery')
    assert set(writes) == {('jobs', 'tail')}, 'the anchor row stays out of the transition write set'
    assert pins[0].segment_id == 'head'
    assert pins[0].stage == 'recovery'


def test_recovery_descriptor_part_equals_the_resolved_policy(unit):
    _, _, pins, policy = stage_buffered(unit, 'tail', 'recovery')
    assert pins[0].part == policy.to_dict()
    assert pins[0].source == 'fallback'
    assert pins[0].part['source_role'] == policy.to_dict()['source_role']


def test_recovery_anchor_self_stage_writes_one_row_with_no_descriptor(unit):
    writes, _, pins, _ = stage_buffered(unit, 'head', 'recovery')
    assert set(writes) == {('jobs', 'head')}
    assert pins == []


def test_recovery_flush_pins_the_canonical_anchor_row(unit):
    _, _, pins, policy = stage_buffered(unit, 'tail', 'recovery')
    assert policies_flush(unit, pins) == 1
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts']['recovery'] == policy.to_dict()
    assert anchor['policy_part_sources']['recovery'] == 'fallback'


def test_recovery_second_flush_of_a_pinned_anchor_never_overwrites(unit):
    _, _, first, _ = stage_buffered(unit, 'tail', 'recovery')
    assert policies_flush(unit, list(first)) == 1
    rewritten = replace(STAGE_TYPES['recovery'](), source_role='later-env')
    duplicate = AnchorStagePin('head', 'recovery', rewritten.to_dict(), 'fallback')
    before = unit.get('jobs', 'head')['policy_parts']['recovery']
    assert policies_flush(unit, [duplicate]) == 0
    assert unit.get('jobs', 'head')['policy_parts']['recovery'] == before


def test_recovery_flush_defers_when_the_anchor_holds_a_partial_stamp(unit):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'recovery': {}}
    _, _, pins, _ = stage_buffered(unit, 'tail', 'recovery')
    assert policies_flush(unit, pins) == 0
    assert unit.get('jobs', 'head')['policy_parts']['recovery'] == {}


def test_recovery_pinned_anchor_copies_to_the_sibling_without_a_descriptor(unit):
    pinned = replace(STAGE_TYPES['recovery'](), source_role='pin-canonical')
    unit.rows[('jobs', 'head')]['policy_parts'] = {'recovery': pinned.to_dict()}
    writes, _, pins, policy = stage_buffered(unit, 'tail', 'recovery')
    assert set(writes) == {('jobs', 'tail')}
    assert pins == []
    assert policy.to_dict() == pinned.to_dict()


def test_recovery_pinned_part_converges_later_siblings_without_resolution(unit, monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'pin-serving')
    _, _, pins, first = stage_buffered(unit, 'tail', 'recovery')
    assert policies_flush(unit, pins) == 1
    monkeypatch.setenv('K_SERVICE', 'later-role')
    monkeypatch.setattr(
        IMPORTED_POLICIES,
        'resolve_stage_policy',
        lambda *a, **k: pytest.fail('re-resolved after the pin existed'),
    )
    _, _, _, second = stage_buffered(unit, 'mid', 'recovery')
    assert second.to_dict() == first.to_dict()


def test_recovery_recorded_whole_unit_policy_guards_the_pin_provenance(unit):
    recorded = replace(STAGE_TYPES['recovery'](), source_role='recorded-owner')
    unit.rows[('jobs', 'head')]['policy'] = recorded.to_dict()
    unit.rows[('jobs', 'head')]['policy_source'] = 'recorded'
    _, _, pins, _ = stage_buffered(unit, 'tail', 'recovery')
    assert policies_flush(unit, pins) == 1
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts']['recovery']
    assert 'policy_part_sources' not in anchor


def test_recovery_pin_failure_is_deferred_and_names_the_stage(unit, caplog):
    pins = []

    def body(tx):
        job = tx.get('jobs', 'tail')
        return IMPORTED_POLICIES.stage_in_transaction(tx, job, 'recovery', pins=pins)

    unit.run(body)
    witness = pin_broken_store(unit)
    with caplog.at_level('WARNING', logger='database.batch_pipeline_policy'):
        assert policies_flush(witness, pins) == 0
    assert any('outcome=deferred' in r.getMessage() and 'stage=recovery' in r.getMessage() for r in caplog.records)
    assert unit.get('jobs', 'tail')['policy_parts']['recovery'], 'the transition row stays durable'


def test_recovery_wrapper_refuses_an_absent_part_without_server_flags(unit):
    from database.batch_pipeline_policy import UnpinnedPolicyRefused, load_stage_policy

    with pytest.raises(UnpinnedPolicyRefused) as refused:
        load_stage_policy(unit, 'tail', 'recovery', server_flags=None)
    assert refused.value.stage == 'recovery'
    assert unit.get('jobs', 'tail').get('policy_parts') is None


def test_recovery_wrapper_stages_the_job_and_pins_the_anchor(unit, monkeypatch):
    from database.batch_pipeline_policy import load_stage_policy

    monkeypatch.setenv('K_SERVICE', 'pin-serving')
    _, policy = load_stage_policy(unit, 'tail', 'recovery')
    assert unit.get('jobs', 'tail')['policy_parts']['recovery'] == policy.to_dict()
    assert unit.get('jobs', 'head')['policy_parts']['recovery'] == policy.to_dict()


def test_recovery_recorded_job_part_returns_before_any_anchor_read(unit):
    own = replace(STAGE_TYPES['recovery'](), source_role='own-row')
    unit.rows[('jobs', 'tail')]['policy_parts'] = {'recovery': own.to_dict()}
    _, gets, pins, policy = stage_buffered(unit, 'tail', 'recovery')
    assert pins == []
    assert policy.to_dict() == own.to_dict()
    assert all(key[1] != 'head' for key in gets)


def test_recovery_candidate_cache_resolves_once_per_anchor_and_stage(unit, monkeypatch):
    resolve = IMPORTED_POLICIES.resolve_stage_policy
    calls = []
    monkeypatch.setattr(
        IMPORTED_POLICIES, 'resolve_stage_policy', lambda uid, st, **k: calls.append(st) or resolve(uid, st, **k)
    )
    candidates = {}
    stage_buffered(unit, 'tail', 'recovery', candidates=candidates)
    stage_buffered(unit, 'mid', 'recovery', candidates=candidates)
    assert calls == ['recovery']


def test_recovery_caller_without_pins_keeps_the_in_transaction_anchor_write(unit):
    writes, _, _, _ = stage_buffered(unit, 'tail', 'recovery', pins=None)
    assert set(writes) == {('jobs', 'head'), ('jobs', 'tail')}
    for sid in ('head', 'tail'):
        assert writes[('jobs', sid)]['policy_parts']['recovery']


def test_recovery_partial_anchor_stamp_uses_defaults_without_env_or_descriptor(unit, monkeypatch):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'recovery': {}}
    monkeypatch.setattr(IMPORTED_POLICIES, 'resolve_stage_policy', lambda *a, **k: pytest.fail('re-resolved'))
    writes, _, pins, policy = stage_buffered(unit, 'tail', 'recovery')
    assert set(writes) == {('jobs', 'tail')}
    assert pins == []
    assert policy == STAGE_TYPES['recovery']()


def test_recovery_matrix_absent_part_serving_resolution_pins_the_anchor(unit, monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'matrix-serving')
    policy, pinned, pins = commit_stage(unit, 'tail', 'recovery')
    assert pinned == 1
    assert unit.get('jobs', 'head')['policy_parts']['recovery'] == policy.to_dict()
    assert unit.get('jobs', 'head')['policy_part_sources']['recovery'] == 'fallback'


def test_recovery_matrix_absent_part_operator_mapping_pins_its_own_provenance(unit):
    flags = {'K_SERVICE': 'operator-role'}
    _, _, pins, policy = stage_buffered(unit, 'tail', 'recovery', server_flags=flags)
    assert pins[0].source == 'operator_server_flags'
    assert policies_flush(unit, pins) == 1
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts']['recovery'] == policy.to_dict()
    assert anchor['policy_part_sources']['recovery'] == 'operator_server_flags'


def test_recovery_matrix_absent_part_without_authority_is_refused_before_writes(unit):
    import pytest as _pytest

    with _pytest.raises(Exception):
        stage_buffered(unit, 'tail', 'recovery', server_flags=None)
    assert unit.get('jobs', 'tail').get('policy_parts') is None
    assert unit.get('jobs', 'head').get('policy_parts') is None


def test_recovery_matrix_pinned_part_serving_copy_keeps_the_stamp(unit):
    pinned = replace(STAGE_TYPES['recovery'](), source_role='pin-canonical')
    unit.rows[('jobs', 'head')]['policy_parts'] = {'recovery': pinned.to_dict()}
    unit.rows[('jobs', 'head')]['policy_part_sources'] = {'recovery': 'fallback'}
    policy, pinned_count, pins = commit_stage(unit, 'tail', 'recovery')
    assert pinned_count == 0 and pins == []
    assert policy.to_dict() == pinned.to_dict()
    assert unit.get('jobs', 'tail')['policy_part_sources']['recovery'] == 'fallback'


def test_recovery_matrix_partial_stamp_operator_mapping_defaults_without_env(unit, monkeypatch):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'recovery': {}}
    monkeypatch.setattr(IMPORTED_POLICIES, 'resolve_stage_policy', lambda *a, **k: pytest.fail('re-resolved'))
    flags = {'K_SERVICE': 'operator-role'}
    _, _, pins, _ = stage_buffered(unit, 'tail', 'recovery', server_flags=flags)
    assert pins == []
    assert unit.get('jobs', 'head')['policy_parts']['recovery'] == {}


def test_recovery_flush_defers_when_the_anchor_row_is_gone(unit):
    _, _, pins, _ = stage_buffered(unit, 'tail', 'recovery')
    unit.rows.pop(('jobs', 'head'))
    assert policies_flush(unit, pins) == 0
    assert pins == []


def test_recovery_pin_transaction_carries_the_static_label(unit):
    labels = []

    class Witness:
        def run(self, body, *, operation=None):
            labels.append(operation)
            return unit.run(body, operation=operation)

        def __getattr__(self, name):
            return getattr(unit, name)

    _, _, pins, _ = stage_buffered(unit, 'tail', 'recovery')
    assert policies_flush(Witness(), pins) == 1
    assert labels == ['batch_anchor_stage_pin']


def test_recovery_duplicate_descriptors_collapse_into_one_pin_transaction(unit):
    _, _, pins, _ = stage_buffered(unit, 'tail', 'recovery')
    stage_buffered(unit, 'tail', 'recovery', pins=pins)
    before = unit.transactions
    assert policies_flush(unit, pins) == 1
    assert unit.transactions == before + 1


def test_recovery_pin_write_respects_the_privacy_fence(unit):
    pins = []

    def body(tx):
        job = tx.get('jobs', 'tail')
        return IMPORTED_POLICIES.stage_in_transaction(tx, job, 'recovery', pins=pins)

    unit.run(body)
    unit.customer.block_privacy('owner')
    descriptor = AnchorStagePin('head', 'recovery', replace(STAGE_TYPES['recovery']()).to_dict(), 'fallback')
    assert policies_flush(unit, [descriptor]) == 0
    assert unit.get('jobs', 'head').get('policy_parts') is None
    assert unit.get('jobs', 'tail')['policy_parts']['recovery'], 'the transition row stays durable'


def test_recovery_flush_needs_only_the_store_run_protocol(unit):
    runs = []

    class Tiny:
        def run(self, body, *, operation=None):
            runs.append(operation)
            return unit.run(body, operation=operation)

    _, _, pins, _ = stage_buffered(unit, 'tail', 'recovery')
    assert policies_flush(Tiny(), pins) == 1
    assert runs == ['batch_anchor_stage_pin']


def test_recovery_descriptor_is_a_frozen_value_object():
    descriptor = AnchorStagePin('head', 'recovery', {}, 'fallback')
    assert descriptor == AnchorStagePin('head', 'recovery', {}, 'fallback')
    with pytest.raises(Exception):
        descriptor.stage = 'other'


def test_recovery_absent_part_without_authority_refuses_the_sibling_stage(unit):
    with pytest.raises(Exception):
        stage_buffered(unit, 'tail', 'recovery', server_flags=None)
    assert unit.get('jobs', 'tail').get('policy_parts') is None


def test_recovery_anchor_self_stage_operator_mapping_records_operator_provenance(unit):
    writes, _, pins, _ = stage_buffered(unit, 'head', 'recovery', server_flags={'K_SERVICE': 'operator-role'})
    assert set(writes) == {('jobs', 'head')}
    assert writes[('jobs', 'head')]['policy_part_sources']['recovery'] == 'operator_server_flags'
    assert pins == []


def test_recovery_pre_pin_siblings_converge_on_their_next_touch(unit, monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'first-role')
    _, _, first_pins, first_part = stage_buffered(unit, 'tail', 'recovery')
    monkeypatch.setenv('K_SERVICE', 'second-role')
    _, _, second_pins, _ = stage_buffered(unit, 'mid', 'recovery')
    assert policies_flush(unit, first_pins + second_pins) == 1
    anchor_part = unit.get('jobs', 'head')['policy_parts']['recovery']
    assert anchor_part == first_part.to_dict(), 'the first emitted pin wins'
    monkeypatch.setattr(IMPORTED_POLICIES, 'resolve_stage_policy', lambda *a, **k: pytest.fail('re-resolved'))
    _, _, _, converged = stage_buffered(unit, 'mid', 'recovery')
    assert converged.to_dict() == anchor_part


def test_recovery_pinned_part_keeps_the_stage_stable_default_identity(unit):
    _, _, pins, policy = stage_buffered(unit, 'tail', 'recovery')
    assert pins[0].part['source_role'] == policy.to_dict()['source_role']
    assert policies_flush(unit, pins) == 1


def test_recovery_matrix_pinned_part_operator_mapping_copies_the_stamp(unit):
    pinned = replace(STAGE_TYPES['recovery'](), source_role='pin-canonical')
    unit.rows[('jobs', 'head')]['policy_parts'] = {'recovery': pinned.to_dict()}
    flags = {'K_SERVICE': 'operator-role'}
    _, _, pins, policy = stage_buffered(unit, 'tail', 'recovery', server_flags=flags)
    assert pins == []
    assert policy.to_dict() == pinned.to_dict()


def test_recovery_matrix_partial_stamp_without_authority_still_uses_defaults(unit):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'recovery': {}}
    _, _, pins, policy = stage_buffered(unit, 'tail', 'recovery', server_flags=None)
    assert pins == []
    assert policy == STAGE_TYPES['recovery']()


def test_recovery_self_stage_serving_end_state(unit, monkeypatch):
    lone = make_store(siblings=('lone',))
    lone.rows[('jobs', 'lone')]['projection_binding']['segment_ids'] = ('lone',)
    monkeypatch.setenv('K_SERVICE', 'matrix-serving')
    policy, pinned, pins = commit_stage(lone, 'lone', 'recovery', server_flags=flags_for('serving'))
    row = lone.get('jobs', 'lone')
    assert pinned == 0 and pins == []
    assert row['policy_parts']['recovery'] == policy.to_dict()
    assert row['policy_part_sources']['recovery'] == 'fallback'


def test_recovery_self_stage_mapping_end_state(unit):
    lone = make_store(siblings=('lone',))
    lone.rows[('jobs', 'lone')]['projection_binding']['segment_ids'] = ('lone',)
    policy, pinned, pins = commit_stage(lone, 'lone', 'recovery', server_flags=flags_for('mapping'))
    row = lone.get('jobs', 'lone')
    assert pinned == 0 and pins == []
    assert row['policy_parts']['recovery'] == policy.to_dict()
    assert row['policy_part_sources']['recovery'] == 'operator_server_flags'


def test_recovery_self_stage_none_end_state(unit):
    lone = make_store(siblings=('lone',))
    lone.rows[('jobs', 'lone')]['projection_binding']['segment_ids'] = ('lone',)
    import pytest as _pytest

    with _pytest.raises(Exception):
        stage_buffered(lone, 'lone', 'recovery', server_flags=None)
    assert lone.get('jobs', 'lone').get('policy_parts') is None


def test_scheduler_sibling_stage_write_set_is_the_job_row_only(unit):
    writes, _, pins, _ = stage_buffered(unit, 'tail', 'scheduler')
    assert set(writes) == {('jobs', 'tail')}, 'the anchor row stays out of the transition write set'
    assert pins[0].segment_id == 'head'
    assert pins[0].stage == 'scheduler'


def test_scheduler_descriptor_part_equals_the_resolved_policy(unit):
    _, _, pins, policy = stage_buffered(unit, 'tail', 'scheduler')
    assert pins[0].part == policy.to_dict()
    assert pins[0].source == 'fallback'
    assert pins[0].part['source_role'] == policy.to_dict()['source_role']


def test_scheduler_anchor_self_stage_writes_one_row_with_no_descriptor(unit):
    writes, _, pins, _ = stage_buffered(unit, 'head', 'scheduler')
    assert set(writes) == {('jobs', 'head')}
    assert pins == []


def test_scheduler_flush_pins_the_canonical_anchor_row(unit):
    _, _, pins, policy = stage_buffered(unit, 'tail', 'scheduler')
    assert policies_flush(unit, pins) == 1
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts']['scheduler'] == policy.to_dict()
    assert anchor['policy_part_sources']['scheduler'] == 'fallback'


def test_scheduler_second_flush_of_a_pinned_anchor_never_overwrites(unit):
    _, _, first, _ = stage_buffered(unit, 'tail', 'scheduler')
    assert policies_flush(unit, list(first)) == 1
    rewritten = replace(STAGE_TYPES['scheduler'](), source_role='later-env')
    duplicate = AnchorStagePin('head', 'scheduler', rewritten.to_dict(), 'fallback')
    before = unit.get('jobs', 'head')['policy_parts']['scheduler']
    assert policies_flush(unit, [duplicate]) == 0
    assert unit.get('jobs', 'head')['policy_parts']['scheduler'] == before


def test_scheduler_flush_defers_when_the_anchor_holds_a_partial_stamp(unit):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'scheduler': {}}
    _, _, pins, _ = stage_buffered(unit, 'tail', 'scheduler')
    assert policies_flush(unit, pins) == 0
    assert unit.get('jobs', 'head')['policy_parts']['scheduler'] == {}


def test_scheduler_pinned_anchor_copies_to_the_sibling_without_a_descriptor(unit):
    pinned = replace(STAGE_TYPES['scheduler'](), source_role='pin-canonical')
    unit.rows[('jobs', 'head')]['policy_parts'] = {'scheduler': pinned.to_dict()}
    writes, _, pins, policy = stage_buffered(unit, 'tail', 'scheduler')
    assert set(writes) == {('jobs', 'tail')}
    assert pins == []
    assert policy.to_dict() == pinned.to_dict()


def test_scheduler_pinned_part_converges_later_siblings_without_resolution(unit, monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'pin-serving')
    _, _, pins, first = stage_buffered(unit, 'tail', 'scheduler')
    assert policies_flush(unit, pins) == 1
    monkeypatch.setenv('K_SERVICE', 'later-role')
    monkeypatch.setattr(
        IMPORTED_POLICIES,
        'resolve_stage_policy',
        lambda *a, **k: pytest.fail('re-resolved after the pin existed'),
    )
    _, _, _, second = stage_buffered(unit, 'mid', 'scheduler')
    assert second.to_dict() == first.to_dict()


def test_scheduler_recorded_whole_unit_policy_guards_the_pin_provenance(unit):
    recorded = replace(STAGE_TYPES['scheduler'](), source_role='recorded-owner')
    unit.rows[('jobs', 'head')]['policy'] = recorded.to_dict()
    unit.rows[('jobs', 'head')]['policy_source'] = 'recorded'
    _, _, pins, _ = stage_buffered(unit, 'tail', 'scheduler')
    assert policies_flush(unit, pins) == 1
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts']['scheduler']
    assert 'policy_part_sources' not in anchor


def test_scheduler_pin_failure_is_deferred_and_names_the_stage(unit, caplog):
    pins = []

    def body(tx):
        job = tx.get('jobs', 'tail')
        return IMPORTED_POLICIES.stage_in_transaction(tx, job, 'scheduler', pins=pins)

    unit.run(body)
    witness = pin_broken_store(unit)
    with caplog.at_level('WARNING', logger='database.batch_pipeline_policy'):
        assert policies_flush(witness, pins) == 0
    assert any('outcome=deferred' in r.getMessage() and 'stage=scheduler' in r.getMessage() for r in caplog.records)
    assert unit.get('jobs', 'tail')['policy_parts']['scheduler'], 'the transition row stays durable'


def test_scheduler_wrapper_refuses_an_absent_part_without_server_flags(unit):
    from database.batch_pipeline_policy import UnpinnedPolicyRefused, load_stage_policy

    with pytest.raises(UnpinnedPolicyRefused) as refused:
        load_stage_policy(unit, 'tail', 'scheduler', server_flags=None)
    assert refused.value.stage == 'scheduler'
    assert unit.get('jobs', 'tail').get('policy_parts') is None


def test_scheduler_wrapper_stages_the_job_and_pins_the_anchor(unit, monkeypatch):
    from database.batch_pipeline_policy import load_stage_policy

    monkeypatch.setenv('K_SERVICE', 'pin-serving')
    _, policy = load_stage_policy(unit, 'tail', 'scheduler')
    assert unit.get('jobs', 'tail')['policy_parts']['scheduler'] == policy.to_dict()
    assert unit.get('jobs', 'head')['policy_parts']['scheduler'] == policy.to_dict()


def test_scheduler_recorded_job_part_returns_before_any_anchor_read(unit):
    own = replace(STAGE_TYPES['scheduler'](), source_role='own-row')
    unit.rows[('jobs', 'tail')]['policy_parts'] = {'scheduler': own.to_dict()}
    _, gets, pins, policy = stage_buffered(unit, 'tail', 'scheduler')
    assert pins == []
    assert policy.to_dict() == own.to_dict()
    assert all(key[1] != 'head' for key in gets)


def test_scheduler_candidate_cache_resolves_once_per_anchor_and_stage(unit, monkeypatch):
    resolve = IMPORTED_POLICIES.resolve_stage_policy
    calls = []
    monkeypatch.setattr(
        IMPORTED_POLICIES, 'resolve_stage_policy', lambda uid, st, **k: calls.append(st) or resolve(uid, st, **k)
    )
    candidates = {}
    stage_buffered(unit, 'tail', 'scheduler', candidates=candidates)
    stage_buffered(unit, 'mid', 'scheduler', candidates=candidates)
    assert calls == ['scheduler']


def test_scheduler_caller_without_pins_keeps_the_in_transaction_anchor_write(unit):
    writes, _, _, _ = stage_buffered(unit, 'tail', 'scheduler', pins=None)
    assert set(writes) == {('jobs', 'head'), ('jobs', 'tail')}
    for sid in ('head', 'tail'):
        assert writes[('jobs', sid)]['policy_parts']['scheduler']


def test_scheduler_partial_anchor_stamp_uses_defaults_without_env_or_descriptor(unit, monkeypatch):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'scheduler': {}}
    monkeypatch.setattr(IMPORTED_POLICIES, 'resolve_stage_policy', lambda *a, **k: pytest.fail('re-resolved'))
    writes, _, pins, policy = stage_buffered(unit, 'tail', 'scheduler')
    assert set(writes) == {('jobs', 'tail')}
    assert pins == []
    assert policy == STAGE_TYPES['scheduler']()


def test_scheduler_matrix_absent_part_serving_resolution_pins_the_anchor(unit, monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'matrix-serving')
    policy, pinned, pins = commit_stage(unit, 'tail', 'scheduler')
    assert pinned == 1
    assert unit.get('jobs', 'head')['policy_parts']['scheduler'] == policy.to_dict()
    assert unit.get('jobs', 'head')['policy_part_sources']['scheduler'] == 'fallback'


def test_scheduler_matrix_absent_part_operator_mapping_pins_its_own_provenance(unit):
    flags = {'K_SERVICE': 'operator-role'}
    _, _, pins, policy = stage_buffered(unit, 'tail', 'scheduler', server_flags=flags)
    assert pins[0].source == 'operator_server_flags'
    assert policies_flush(unit, pins) == 1
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts']['scheduler'] == policy.to_dict()
    assert anchor['policy_part_sources']['scheduler'] == 'operator_server_flags'


def test_scheduler_matrix_absent_part_without_authority_is_refused_before_writes(unit):
    import pytest as _pytest

    with _pytest.raises(Exception):
        stage_buffered(unit, 'tail', 'scheduler', server_flags=None)
    assert unit.get('jobs', 'tail').get('policy_parts') is None
    assert unit.get('jobs', 'head').get('policy_parts') is None


def test_scheduler_matrix_pinned_part_serving_copy_keeps_the_stamp(unit):
    pinned = replace(STAGE_TYPES['scheduler'](), source_role='pin-canonical')
    unit.rows[('jobs', 'head')]['policy_parts'] = {'scheduler': pinned.to_dict()}
    unit.rows[('jobs', 'head')]['policy_part_sources'] = {'scheduler': 'fallback'}
    policy, pinned_count, pins = commit_stage(unit, 'tail', 'scheduler')
    assert pinned_count == 0 and pins == []
    assert policy.to_dict() == pinned.to_dict()
    assert unit.get('jobs', 'tail')['policy_part_sources']['scheduler'] == 'fallback'


def test_scheduler_matrix_partial_stamp_operator_mapping_defaults_without_env(unit, monkeypatch):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'scheduler': {}}
    monkeypatch.setattr(IMPORTED_POLICIES, 'resolve_stage_policy', lambda *a, **k: pytest.fail('re-resolved'))
    flags = {'K_SERVICE': 'operator-role'}
    _, _, pins, _ = stage_buffered(unit, 'tail', 'scheduler', server_flags=flags)
    assert pins == []
    assert unit.get('jobs', 'head')['policy_parts']['scheduler'] == {}


def test_scheduler_flush_defers_when_the_anchor_row_is_gone(unit):
    _, _, pins, _ = stage_buffered(unit, 'tail', 'scheduler')
    unit.rows.pop(('jobs', 'head'))
    assert policies_flush(unit, pins) == 0
    assert pins == []


def test_scheduler_pin_transaction_carries_the_static_label(unit):
    labels = []

    class Witness:
        def run(self, body, *, operation=None):
            labels.append(operation)
            return unit.run(body, operation=operation)

        def __getattr__(self, name):
            return getattr(unit, name)

    _, _, pins, _ = stage_buffered(unit, 'tail', 'scheduler')
    assert policies_flush(Witness(), pins) == 1
    assert labels == ['batch_anchor_stage_pin']


def test_scheduler_duplicate_descriptors_collapse_into_one_pin_transaction(unit):
    _, _, pins, _ = stage_buffered(unit, 'tail', 'scheduler')
    stage_buffered(unit, 'tail', 'scheduler', pins=pins)
    before = unit.transactions
    assert policies_flush(unit, pins) == 1
    assert unit.transactions == before + 1


def test_scheduler_pin_write_respects_the_privacy_fence(unit):
    pins = []

    def body(tx):
        job = tx.get('jobs', 'tail')
        return IMPORTED_POLICIES.stage_in_transaction(tx, job, 'scheduler', pins=pins)

    unit.run(body)
    unit.customer.block_privacy('owner')
    descriptor = AnchorStagePin('head', 'scheduler', replace(STAGE_TYPES['scheduler']()).to_dict(), 'fallback')
    assert policies_flush(unit, [descriptor]) == 0
    assert unit.get('jobs', 'head').get('policy_parts') is None
    assert unit.get('jobs', 'tail')['policy_parts']['scheduler'], 'the transition row stays durable'


def test_scheduler_flush_needs_only_the_store_run_protocol(unit):
    runs = []

    class Tiny:
        def run(self, body, *, operation=None):
            runs.append(operation)
            return unit.run(body, operation=operation)

    _, _, pins, _ = stage_buffered(unit, 'tail', 'scheduler')
    assert policies_flush(Tiny(), pins) == 1
    assert runs == ['batch_anchor_stage_pin']


def test_scheduler_descriptor_is_a_frozen_value_object():
    descriptor = AnchorStagePin('head', 'scheduler', {}, 'fallback')
    assert descriptor == AnchorStagePin('head', 'scheduler', {}, 'fallback')
    with pytest.raises(Exception):
        descriptor.stage = 'other'


def test_scheduler_absent_part_without_authority_refuses_the_sibling_stage(unit):
    with pytest.raises(Exception):
        stage_buffered(unit, 'tail', 'scheduler', server_flags=None)
    assert unit.get('jobs', 'tail').get('policy_parts') is None


def test_scheduler_anchor_self_stage_operator_mapping_records_operator_provenance(unit):
    writes, _, pins, _ = stage_buffered(unit, 'head', 'scheduler', server_flags={'K_SERVICE': 'operator-role'})
    assert set(writes) == {('jobs', 'head')}
    assert writes[('jobs', 'head')]['policy_part_sources']['scheduler'] == 'operator_server_flags'
    assert pins == []


def test_scheduler_pre_pin_siblings_converge_on_their_next_touch(unit, monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'first-role')
    _, _, first_pins, first_part = stage_buffered(unit, 'tail', 'scheduler')
    monkeypatch.setenv('K_SERVICE', 'second-role')
    _, _, second_pins, _ = stage_buffered(unit, 'mid', 'scheduler')
    assert policies_flush(unit, first_pins + second_pins) == 1
    anchor_part = unit.get('jobs', 'head')['policy_parts']['scheduler']
    assert anchor_part == first_part.to_dict(), 'the first emitted pin wins'
    monkeypatch.setattr(IMPORTED_POLICIES, 'resolve_stage_policy', lambda *a, **k: pytest.fail('re-resolved'))
    _, _, _, converged = stage_buffered(unit, 'mid', 'scheduler')
    assert converged.to_dict() == anchor_part


def test_scheduler_pinned_part_keeps_the_stage_stable_default_identity(unit):
    _, _, pins, policy = stage_buffered(unit, 'tail', 'scheduler')
    assert pins[0].part['source_role'] == policy.to_dict()['source_role']
    assert policies_flush(unit, pins) == 1


def test_scheduler_matrix_pinned_part_operator_mapping_copies_the_stamp(unit):
    pinned = replace(STAGE_TYPES['scheduler'](), source_role='pin-canonical')
    unit.rows[('jobs', 'head')]['policy_parts'] = {'scheduler': pinned.to_dict()}
    flags = {'K_SERVICE': 'operator-role'}
    _, _, pins, policy = stage_buffered(unit, 'tail', 'scheduler', server_flags=flags)
    assert pins == []
    assert policy.to_dict() == pinned.to_dict()


def test_scheduler_matrix_partial_stamp_without_authority_still_uses_defaults(unit):
    unit.rows[('jobs', 'head')]['policy_parts'] = {'scheduler': {}}
    _, _, pins, policy = stage_buffered(unit, 'tail', 'scheduler', server_flags=None)
    assert pins == []
    assert policy == STAGE_TYPES['scheduler']()


def test_scheduler_self_stage_serving_end_state(unit, monkeypatch):
    lone = make_store(siblings=('lone',))
    lone.rows[('jobs', 'lone')]['projection_binding']['segment_ids'] = ('lone',)
    monkeypatch.setenv('K_SERVICE', 'matrix-serving')
    policy, pinned, pins = commit_stage(lone, 'lone', 'scheduler', server_flags=flags_for('serving'))
    row = lone.get('jobs', 'lone')
    assert pinned == 0 and pins == []
    assert row['policy_parts']['scheduler'] == policy.to_dict()
    assert row['policy_part_sources']['scheduler'] == 'fallback'


def test_scheduler_self_stage_mapping_end_state(unit):
    lone = make_store(siblings=('lone',))
    lone.rows[('jobs', 'lone')]['projection_binding']['segment_ids'] = ('lone',)
    policy, pinned, pins = commit_stage(lone, 'lone', 'scheduler', server_flags=flags_for('mapping'))
    row = lone.get('jobs', 'lone')
    assert pinned == 0 and pins == []
    assert row['policy_parts']['scheduler'] == policy.to_dict()
    assert row['policy_part_sources']['scheduler'] == 'operator_server_flags'


def test_scheduler_self_stage_none_end_state(unit):
    lone = make_store(siblings=('lone',))
    lone.rows[('jobs', 'lone')]['projection_binding']['segment_ids'] = ('lone',)
    import pytest as _pytest

    with _pytest.raises(Exception):
        stage_buffered(lone, 'lone', 'scheduler', server_flags=None)
    assert lone.get('jobs', 'lone').get('policy_parts') is None


def test_admission_pin_is_idempotent_across_flushes(unit):
    for job in unit.jobs():
        job.pop('policy', None)
    _, pins = commit_policy(unit, 'tail')
    assert policies_flush(unit, list(pins)) == 1
    pinned_part = unit.get('jobs', 'head')['policy']
    from config.policy import resolve_batch_policy

    competing = resolve_batch_policy('owner', flags={'BATCH_PIPELINE_ENABLED': 'false', 'BATCH_PIPELINE_PERCENT': '0'})
    duplicate = AnchorStagePin('head', 'admission', competing.to_dict(), 'fallback')
    assert policies_flush(unit, [duplicate]) == 0
    assert unit.get('jobs', 'head')['policy'] == pinned_part


def test_admission_descriptor_records_the_fallback_source(unit):
    _, _, pins, _ = policy_buffered(unit, 'tail')
    assert pins[0].source == 'fallback'
    assert policies_flush(unit, pins) == 1
    assert unit.get('jobs', 'head')['policy_source'] == 'fallback'


def test_mixed_stage_and_admission_descriptors_flush_one_transaction_each(unit):
    pins = []
    for stage in STAGES:
        stage_buffered(unit, 'tail', stage, pins=pins)
    _, _, admission_pins, _ = policy_buffered(unit, 'tail')
    pins.extend(admission_pins)
    before = unit.transactions
    assert policies_flush(unit, pins) == len(STAGES) + 1
    assert unit.transactions == before + len(STAGES) + 1
    anchor = unit.get('jobs', 'head')
    assert set(anchor['policy_parts']) == set(STAGES)
    assert anchor['policy']


from database import batch_pipeline_policy as _policies

IMPORTED_POLICIES = _policies


def policies_flush(store, pins):
    return _policies.flush_anchor_stage_pins(store, pins)


@pytest.fixture
def unit():
    return make_store()
