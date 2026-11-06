"""Anchor stage pin parity: sibling staging without shared-row write collisions.

Contract under test (`database/batch_pipeline_policy.py`): a sibling segment's
first-touch policy staging self-stages the resolved part on its own row and
defers the canonical anchor write to `flush_anchor_stage_pins`, so concurrently
publishing siblings of one owner never carry the shared anchor row in their
transition transactions. The anchor remains the canonical snapshot: the first
pin wins, every later staging call copies from it, recorded parts never
re-resolve env, and provenance rules are byte-identical to the in-transaction
write they replace.
"""

import pytest

from config.policy.stages import STAGE_TYPES
from dataclasses import asdict, replace
from database import batch_pipeline_policy as policies
from database.batch_pipeline_policy import PROCESS_ENVIRONMENT, AnchorStagePin
from testing.pipeline_sim.store import CustomerData, SimStore, SimTransaction
from utils.batch_pipeline.contracts import ProjectionBinding

SIBLINGS = ('head', 'mid', 'tail')
STAGES = tuple(sorted(STAGE_TYPES))


def make_store(siblings=SIBLINGS):
    customer = CustomerData()
    customer.add_user('owner')
    store = SimStore(customer)
    binding = asdict(ProjectionBinding('owner', 'job', 'content', tuple(siblings)))
    for sid in siblings:
        store.rows[('jobs', sid)] = {'segment_id': sid, 'owner_id': 'owner', 'projection_binding': dict(binding)}
    return store


@pytest.fixture
def unit():
    return make_store()


class Abort(Exception):
    pass


class RecordingTx(SimTransaction):
    def __init__(self, store):
        super().__init__(store)
        self.gets = []

    def get(self, table, key):
        self.gets.append((table, key))
        return super().get(table, key)


_UNSET = object()


def stage_buffered(store, sid, stage, *, server_flags=PROCESS_ENVIRONMENT, pins=_UNSET, candidates=None):
    """Stage inside an uncommitted transaction; return its buffered write set.

    ``pins=_UNSET`` collects into a fresh list; ``pins=None`` exercises the
    legacy in-transaction anchor write; a list collects into the caller's list.
    """
    tx = RecordingTx(store)
    job = tx.get('jobs', sid)
    collected = [] if pins is _UNSET else pins  # type: ignore[assignment]
    policy = policies.stage_in_transaction(
        tx, job, stage, server_flags=server_flags, pins=collected, candidates=candidates
    )
    return dict(tx.writes), list(tx.gets), collected, policy


def policy_buffered(store, sid, *, pins=_UNSET, candidates=None):
    tx = RecordingTx(store)
    job = tx.get('jobs', sid)
    collected = [] if pins is _UNSET else pins  # type: ignore[assignment]
    policy = policies.policy_in_transaction(tx, job, pins=collected, candidates=candidates)
    return dict(tx.writes), list(tx.gets), collected, policy


def commit_stage(store, sid, stage, *, server_flags=PROCESS_ENVIRONMENT, pins=None):
    """Stage in a committed transaction; return (policy, pinned_count, pins)."""
    collected = [] if pins is None else pins

    def body(tx):
        job = tx.get('jobs', sid)
        return policies.stage_in_transaction(tx, job, stage, server_flags=server_flags, pins=collected)

    policy = store.run(body)
    pinned = policies.flush_anchor_stage_pins(store, collected)
    return policy, pinned, collected


def commit_policy(store, sid):
    """Whole-unit policy in a committed transaction; returns (policy, pins)."""
    collected = []

    def body(tx):
        job = tx.get('jobs', sid)
        return policies.policy_in_transaction(tx, job, pins=collected)

    policy = store.run(body)
    return policy, collected


def stage_and_flush(store, sid, stage, *, server_flags=PROCESS_ENVIRONMENT):
    pins = []

    def body(tx):
        job = tx.get('jobs', sid)
        return policies.stage_in_transaction(tx, job, stage, server_flags=server_flags, pins=pins)

    policy = store.run(body)
    pinned = policies.flush_anchor_stage_pins(store, pins)
    return policy, pinned, pins


def pin_broken_store(inner, break_on='batch_anchor_stage_pin'):
    class Broken:
        def __init__(self):
            self.pin_attempts = 0
            self.broken = True

        def run(self, body, *, operation=None):
            if self.broken and operation == break_on:
                self.pin_attempts += 1
                raise RuntimeError('simulated contention exhaustion')
            return inner.run(body, operation=operation)

        def __getattr__(self, name):
            return getattr(inner, name)

    return Broken()


# ---------------------------------------------------------------------------
# The contention surface: sibling transitions never write the anchor row.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('stage', STAGES)
def test_sibling_stage_transition_write_set_is_the_job_row_only(stage, unit):
    writes, gets, pins, _ = stage_buffered(unit, 'tail', stage)
    assert set(writes) == {('jobs', 'tail')}, 'the anchor row must stay out of the transition write set'
    assert ('jobs', 'head') not in writes
    assert pins and isinstance(pins[0], AnchorStagePin)


@pytest.mark.parametrize('stage', STAGES)
def test_sibling_stage_emits_one_descriptor_for_the_canonical_anchor(stage, unit):
    _, _, pins, policy = stage_buffered(unit, 'tail', stage)
    assert len(pins) == 1
    descriptor = pins[0]
    assert descriptor.segment_id == 'head', 'unit_anchor picks the first extant sibling'
    assert descriptor.stage == stage
    assert descriptor.part == policy.to_dict()
    assert descriptor.source == 'fallback'


@pytest.mark.parametrize('stage', STAGES)
def test_sibling_stage_descriptor_matches_the_self_staged_row(stage, unit):
    writes, _, pins, _ = stage_buffered(unit, 'tail', stage)
    staged = writes[('jobs', 'tail')]
    assert staged['policy_parts'][stage] == pins[0].part
    assert staged['policy_part_sources'][stage] == pins[0].source


def test_whole_unit_sibling_write_set_is_the_job_row_only(unit):
    for job in unit.jobs():
        job.pop('policy', None)
    writes, gets, pins, _ = policy_buffered(unit, 'tail')
    assert set(writes) == {('jobs', 'tail')}
    assert pins[0].segment_id == 'head'
    assert pins[0].stage == 'admission'


def test_whole_unit_descriptor_carries_the_admission_fallback(unit):
    for job in unit.jobs():
        job.pop('policy', None)
    _, _, pins, policy = policy_buffered(unit, 'tail')
    assert pins[0].part == policy.to_dict()
    assert pins[0].source == 'fallback'


@pytest.mark.parametrize('stage', STAGES)
def test_anchor_self_stage_writes_only_its_own_row_and_emits_no_pin(stage, unit):
    writes, gets, pins, _ = stage_buffered(unit, 'head', stage)
    assert set(writes) == {('jobs', 'head')}
    assert pins == []
    assert not any(key[1] == 'mid' or key[1] == 'tail' for key in writes)


@pytest.mark.parametrize('stage', STAGES)
def test_anchor_present_copies_to_the_job_without_a_descriptor(stage, unit):
    pinned = replace(STAGE_TYPES[stage](), source_role='pin-canonical')
    unit.rows[('jobs', 'head')]['policy_parts'] = {stage: pinned.to_dict()}
    writes, _, pins, policy = stage_buffered(unit, 'tail', stage)
    assert set(writes) == {('jobs', 'tail')}
    assert pins == []
    assert policy == pinned


@pytest.mark.parametrize('stage', STAGES)
def test_partial_anchor_stamp_uses_defaults_without_env_or_descriptor(stage, unit, monkeypatch):
    unit.rows[('jobs', 'head')]['policy_parts'] = {stage: {}}
    monkeypatch.setattr(policies, 'resolve_stage_policy', lambda *a, **k: pytest.fail('partial stamp re-resolved env'))
    writes, _, pins, policy = stage_buffered(unit, 'tail', stage)
    assert set(writes) == {('jobs', 'tail')}
    assert pins == []
    assert policy == STAGE_TYPES[stage]()


@pytest.mark.parametrize('stage', STAGES)
def test_job_part_present_returns_before_any_anchor_read(stage, unit):
    own = replace(STAGE_TYPES[stage](), source_role='own-row')
    unit.rows[('jobs', 'tail')]['policy_parts'] = {stage: own.to_dict()}
    tx = RecordingTx(unit)
    job = tx.get('jobs', 'tail')
    collected = []
    policy = policies.stage_in_transaction(tx, job, stage, pins=collected)
    assert policy == own
    assert collected == []
    assert all(key[1] != 'head' for key in tx.gets), 'a recorded row must not read the anchor'


def test_job_policy_present_returns_before_any_anchor_read(unit):
    from config.policy import resolve_batch_policy

    own = resolve_batch_policy('owner', flags={'BATCH_PIPELINE_ENABLED': 'true', 'BATCH_PIPELINE_PERCENT': '100'})
    unit.rows[('jobs', 'tail')]['policy'] = own.to_dict()
    tx = RecordingTx(unit)
    job = tx.get('jobs', 'tail')
    collected = []
    policy = policies.policy_in_transaction(tx, job, pins=collected)
    assert collected == []
    assert policy.to_dict() == own.to_dict()
    assert all(key[1] != 'head' for key in tx.gets)


@pytest.mark.parametrize('stage', STAGES)
def test_partial_stamp_source_copies_anchor_provenance(stage, unit):
    unit.rows[('jobs', 'head')]['policy_parts'] = {stage: {}}
    unit.rows[('jobs', 'head')]['policy_part_sources'] = {stage: 'operator_server_flags'}
    flags = {'K_SERVICE': 'operator-role'}
    writes, _, pins, _policy = stage_buffered(unit, 'tail', stage, server_flags=flags)
    staged = writes[('jobs', 'tail')]
    assert staged['policy_part_sources'][stage] == 'operator_server_flags', 'the anchor provenance wins'
    assert pins == []


@pytest.mark.parametrize('stage', STAGES)
def test_candidate_cache_resolves_once_per_anchor_and_stage(stage, unit, monkeypatch):
    resolve = policies.resolve_stage_policy
    calls = []
    monkeypatch.setattr(
        policies, 'resolve_stage_policy', lambda uid, st, **k: calls.append(st) or resolve(uid, st, **k)
    )
    candidates = {}
    stage_buffered(unit, 'tail', stage, candidates=candidates)
    stage_buffered(unit, 'mid', stage, candidates=candidates)
    assert calls == [stage], 'both siblings share one resolution per anchor and stage'


def test_candidate_cache_keeps_admission_and_stage_resolutions_apart(unit, monkeypatch):
    for job in unit.jobs():
        job.pop('policy', None)
    resolve = policies.resolve_batch_policy
    calls = []
    monkeypatch.setattr(
        policies, 'resolve_batch_policy', lambda uid, **k: calls.append('admission') or resolve(uid, **k)
    )
    candidates = {}
    policy_buffered(unit, 'tail', candidates=candidates)
    stage_buffered(unit, 'tail', STAGES[0], candidates=candidates)
    assert calls == ['admission']


def test_empty_binding_makes_the_job_its_own_anchor(unit):
    lone = make_store(siblings=('lone',))
    lone.rows[('jobs', 'lone')]['projection_binding']['segment_ids'] = ()
    writes, _, pins, _ = stage_buffered(lone, 'lone', STAGES[0])
    assert set(writes) == {('jobs', 'lone')}
    assert pins == []


def test_absent_binding_siblings_fall_back_to_self_anchor(unit):
    unit.rows.pop(('jobs', 'head'))
    unit.rows.pop(('jobs', 'mid'))
    writes, _, pins, _ = stage_buffered(unit, 'tail', STAGES[0])
    assert set(writes) == {('jobs', 'tail')}
    assert pins == [], 'no extant sibling remains, the job self-anchors'


def test_privacy_blocked_sibling_is_skipped_for_the_anchor(unit):
    unit.customer.delete_conversation('owner', 'sealed')
    unit.rows[('jobs', 'head')]['conversation_id'] = 'sealed'
    writes, _, pins, _ = stage_buffered(unit, 'tail', STAGES[0])
    assert set(writes) == {('jobs', 'tail')}
    assert pins[0].segment_id == 'mid', 'the first extant, unblocked sibling becomes the anchor'


def test_policy_sibling_owner_mismatch_is_refused(unit):
    unit.rows[('jobs', 'head')]['owner_id'] = 'someone-else'
    with pytest.raises(ValueError, match='policy sibling owner mismatch'):
        stage_buffered(unit, 'tail', STAGES[0])
    assert unit.rows[('jobs', 'tail')].get('policy_parts') is None


# ---------------------------------------------------------------------------
# Refusals: nothing is staged, nothing is pinned, nothing is written.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('stage', STAGES)
def test_unpinned_sibling_stage_is_refused_before_any_write(stage, unit):
    with pytest.raises(policies.UnpinnedPolicyRefused) as refused:
        stage_buffered(unit, 'tail', stage, server_flags=None)
    assert refused.value.stage == stage
    assert unit.rows[('jobs', 'tail')].get('policy_parts') is None
    assert unit.rows[('jobs', 'head')].get('policy_parts') is None


def test_whole_unit_sibling_self_stage_records_fallback_provenance_on_the_job(unit):
    for job in unit.jobs():
        job.pop('policy', None)
    writes, _, _, _ = policy_buffered(unit, 'tail')
    staged = writes[('jobs', 'tail')]
    assert staged['policy_source'] == 'fallback'
    assert staged['policy']


# ---------------------------------------------------------------------------
# The pin flush: single-document CAS, first writer wins, provenance preserved.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('stage', STAGES)
def test_flush_pins_the_anchor_in_its_own_single_document_transaction(stage, unit):
    _, _, pins, _ = stage_buffered(unit, 'tail', stage)
    before = unit.transactions
    assert policies.flush_anchor_stage_pins(unit, pins) == 1
    assert unit.transactions == before + 1, 'exactly one pin transaction per descriptor'
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts'][stage]
    assert anchor['policy_part_sources'][stage] == 'fallback'


@pytest.mark.parametrize('stage', STAGES)
def test_flushed_anchor_part_equals_the_self_staged_part(stage, unit):
    writes, _, pins, _ = stage_buffered(unit, 'tail', stage)
    policies.flush_anchor_stage_pins(unit, pins)
    assert unit.get('jobs', 'head')['policy_parts'][stage] == writes[('jobs', 'tail')]['policy_parts'][stage]


@pytest.mark.parametrize('stage', STAGES)
def test_second_flush_of_the_same_descriptor_is_a_noop(stage, unit):
    _, _, first, _ = stage_buffered(unit, 'tail', stage)
    assert policies.flush_anchor_stage_pins(unit, list(first)) == 1
    rewritten = replace(STAGE_TYPES[stage](), source_role='later-env')
    duplicate = AnchorStagePin('head', stage, rewritten.to_dict(), 'fallback')
    before = unit.get('jobs', 'head')['policy_parts'][stage]
    assert policies.flush_anchor_stage_pins(unit, [duplicate]) == 0
    assert unit.get('jobs', 'head')['policy_parts'][stage] == before, 'the first pin wins'


@pytest.mark.parametrize('stage', STAGES)
def test_flush_defers_when_the_anchor_already_carries_a_partial_stamp(stage, unit):
    unit.rows[('jobs', 'head')]['policy_parts'] = {stage: {}}
    _, _, pins, _ = stage_buffered(unit, 'tail', stage)
    assert policies.flush_anchor_stage_pins(unit, pins) == 0
    assert unit.get('jobs', 'head')['policy_parts'][stage] == {}, 'a present stamp, even partial, wins'


@pytest.mark.parametrize('stage', STAGES)
def test_flush_refuses_to_pin_when_the_anchor_stamp_is_not_a_dict(stage, unit):
    unit.rows[('jobs', 'head')]['policy_parts'] = {stage: 'garbage'}
    with pytest.raises(ValueError, match='serialized policy part must be a dict'):
        stage_buffered(unit, 'tail', stage)
    assert unit.get('jobs', 'tail').get('policy_parts') is None, 'staging refuses before any write'


def test_flush_defers_when_the_anchor_row_is_gone(unit):
    _, _, pins, _ = stage_buffered(unit, 'tail', STAGES[0])
    unit.rows.pop(('jobs', 'head'))
    assert policies.flush_anchor_stage_pins(unit, pins) == 0
    assert pins == []


def test_flush_collapses_duplicate_descriptors_from_retried_bodies(unit):
    _, _, pins, _ = stage_buffered(unit, 'tail', STAGES[0])
    stage_buffered(unit, 'tail', STAGES[0], pins=pins)
    before = unit.transactions
    assert policies.flush_anchor_stage_pins(unit, pins) == 1
    assert unit.transactions == before + 1, 'duplicates collapse on (segment_id, stage)'
    assert pins == []


def test_flush_covers_every_stage_with_one_transaction_each(unit):
    pins = []
    for stage in STAGES:
        stage_buffered(unit, 'tail', stage, pins=pins)
    before = unit.transactions
    assert policies.flush_anchor_stage_pins(unit, pins) == len(STAGES)
    assert unit.transactions == before + len(STAGES)
    anchor = unit.get('jobs', 'head')
    assert set(anchor['policy_parts']) == set(STAGES)


def test_flush_with_no_descriptors_opens_no_transaction(unit):
    before = unit.transactions
    assert policies.flush_anchor_stage_pins(unit, []) == 0
    assert unit.transactions == before


def test_flush_clears_the_caller_list(unit):
    _, _, pins, _ = stage_buffered(unit, 'tail', STAGES[0])
    policies.flush_anchor_stage_pins(unit, pins)
    assert pins == []


def test_flush_returns_the_pinned_anchor_count(unit):
    pins = []
    stage_buffered(unit, 'tail', STAGES[0], pins=pins)
    stage_buffered(unit, 'mid', STAGES[1], pins=pins)
    assert policies.flush_anchor_stage_pins(unit, pins) == 2


def test_pin_operation_label_is_the_static_literal(unit):
    labels = []

    class Witness:
        def run(self, body, *, operation=None):
            labels.append(operation)
            return unit.run(body, operation=operation)

        def __getattr__(self, name):
            return getattr(unit, name)

    _, _, pins, _ = stage_buffered(unit, 'tail', STAGES[0])
    assert policies.flush_anchor_stage_pins(Witness(), pins) == 1
    assert labels == ['batch_anchor_stage_pin']
    assert policies.ANCHOR_STAGE_PIN_OPERATION == 'batch_anchor_stage_pin'


def test_pin_failure_is_deferred_and_logged_without_raising(unit, caplog):
    _, _, pins, _ = stage_buffered(unit, 'tail', STAGES[0])
    witness = pin_broken_store(unit)
    with caplog.at_level('WARNING', logger='database.batch_pipeline_policy'):
        assert policies.flush_anchor_stage_pins(witness, pins) == 0
    assert witness.pin_attempts == 1
    assert pins == []
    deferred = [record for record in caplog.records if 'outcome=deferred' in record.getMessage()]
    assert deferred and 'batch_anchor_stage_pin' in deferred[0].getMessage()
    assert 'RuntimeError' in deferred[0].getMessage()


def test_pin_failure_keeps_the_transition_durable_and_the_next_touch_converges(unit):
    pins = []

    def body(tx):
        job = tx.get('jobs', 'tail')
        return policies.stage_in_transaction(tx, job, STAGES[0], pins=pins)

    unit.run(body)
    assert unit.get('jobs', 'tail')['policy_parts'][STAGES[0]], 'the transition row is already durable'
    witness = pin_broken_store(unit)
    policies.flush_anchor_stage_pins(witness, pins)
    assert unit.get('jobs', 'head').get('policy_parts') is None
    commit_stage(unit, 'mid', STAGES[0])
    assert unit.get('jobs', 'head')['policy_parts'][STAGES[0]]
    assert unit.get('jobs', 'mid')['policy_parts'][STAGES[0]] == unit.get('jobs', 'head')['policy_parts'][STAGES[0]]


def test_pin_failure_on_one_descriptor_still_attempts_the_rest(unit):
    pins = []
    stage_buffered(unit, 'tail', STAGES[0], pins=pins)
    stage_buffered(unit, 'tail', STAGES[1], pins=pins)

    class Selective:
        def __init__(self):
            self.broken_stage = STAGES[0]
            self.refused = 0

        def run(self, body, *, operation=None):
            if operation == 'batch_anchor_stage_pin' and self.broken_stage:
                stage_now, self.broken_stage = self.broken_stage, None
                self.refused += 1
                raise RuntimeError(f'simulated contention exhaustion on {stage_now}')

            return unit.run(body, operation=operation)

        def __getattr__(self, name):
            return getattr(unit, name)

    witness = Selective()
    assert policies.flush_anchor_stage_pins(witness, pins) == 1
    assert witness.refused == 1
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts'][STAGES[1]], 'the healthy descriptor still landed'
    assert STAGES[0] not in anchor.get('policy_parts', {}), 'the broken descriptor stayed deferred'


def test_pin_write_respects_the_simulated_privacy_fence(unit):
    pins = []

    def body(tx):
        job = tx.get('jobs', 'tail')
        return policies.stage_in_transaction(tx, job, STAGES[0], pins=pins)

    unit.run(body)
    unit.customer.block_privacy('owner')
    descriptor = AnchorStagePin('head', STAGES[0], replace(STAGE_TYPES[STAGES[0]]()).to_dict(), 'fallback')
    assert policies.flush_anchor_stage_pins(unit, [descriptor]) == 0
    assert unit.get('jobs', 'head').get('policy_parts') is None
    assert unit.get('jobs', 'tail')['policy_parts'][STAGES[0]], 'the transition row stays staged'


def test_pin_descriptors_are_frozen_value_objects(unit):
    descriptor = AnchorStagePin('head', STAGES[0], {}, 'fallback')
    same = AnchorStagePin('head', STAGES[0], {}, 'fallback')
    assert descriptor == same
    with pytest.raises(Exception):
        descriptor.stage = 'other'


def test_minimal_store_protocol_is_enough_for_the_flush(unit):
    class Tiny:
        def __init__(self, inner):
            self.inner = inner
            self.runs = []

        def run(self, body, *, operation=None):
            self.runs.append(operation)
            return self.inner.run(body, operation=operation)

    _, _, pins, _ = stage_buffered(unit, 'tail', STAGES[0])
    tiny = Tiny(unit)
    assert policies.flush_anchor_stage_pins(tiny, pins) == 1
    assert tiny.runs == ['batch_anchor_stage_pin']


# ---------------------------------------------------------------------------
# Convergence: the anchor stays the canonical snapshot under env drift.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('stage', STAGES)
def test_pinned_part_is_copied_without_re_resolution_under_env_drift(stage, unit, monkeypatch):
    resolve = policies.resolve_stage_policy
    monkeypatch.setenv('K_SERVICE', 'pin-serving')
    _, _, pins, first = stage_buffered(unit, 'tail', stage)
    policies.flush_anchor_stage_pins(unit, pins)
    monkeypatch.setenv('K_SERVICE', 'later-role')
    monkeypatch.setattr(
        policies,
        'resolve_stage_policy',
        lambda uid, st, **k: pytest.fail(f're-resolved {st} after the pin existed'),
    )
    _, _, _, second = stage_buffered(unit, 'mid', stage)
    assert second == first
    writes, _, _, _ = stage_buffered(unit, 'mid', stage)
    assert set(writes) == {('jobs', 'mid')}


@pytest.mark.parametrize('stage', STAGES)
def test_pre_pin_sibling_resolution_converges_on_its_next_touch(stage, unit, monkeypatch):
    """The honest divergence window: two siblings staging before any pin land."""
    monkeypatch.setenv('K_SERVICE', 'first-role')
    _, _, first_pins, first_part = stage_buffered(unit, 'tail', stage)
    monkeypatch.setenv('K_SERVICE', 'second-role')
    _, _, second_pins, second_part = stage_buffered(unit, 'mid', stage)
    policies.flush_anchor_stage_pins(unit, first_pins + second_pins)
    anchor_part = unit.get('jobs', 'head')['policy_parts'][stage]
    assert anchor_part == first_part.to_dict(), 'the first emitted pin wins the canonical row'
    monkeypatch.setattr(
        policies, 'resolve_stage_policy', lambda uid, st, **k: pytest.fail('converged sibling re-resolved')
    )
    _, _, _, converged = stage_buffered(unit, 'mid', stage)
    assert converged.to_dict() == anchor_part


def test_whole_unit_pin_wins_and_later_uploads_copy_it(unit, monkeypatch):
    for job in unit.jobs():
        job.pop('policy', None)
    _, _, pins, first = policy_buffered(unit, 'tail')
    policies.flush_anchor_stage_pins(unit, pins)
    monkeypatch.setattr(policies, 'resolve_batch_policy', lambda *a, **k: pytest.fail('recorded policy re-resolved'))
    _, _, later_pins, later = policy_buffered(unit, 'mid')
    assert later_pins == []
    assert later.to_dict() == first.to_dict()
    assert unit.get('jobs', 'head')['policy_source'] == 'fallback'


def test_whole_unit_pin_is_refused_when_the_anchor_already_records_a_policy(unit):
    for job in unit.jobs():
        job.pop('policy', None)
    _, _, pins, first = policy_buffered(unit, 'tail')
    rewritten = replace(first, source_role='competing-writer')
    unit.rows[('jobs', 'head')]['policy'] = rewritten.to_dict()
    assert policies.flush_anchor_stage_pins(unit, pins) == 0
    assert unit.get('jobs', 'head')['policy'] == rewritten.to_dict()


@pytest.mark.parametrize('stage', STAGES)
def test_recorded_whole_unit_policy_guards_the_pin_provenance(stage, unit):
    recorded = replace(STAGE_TYPES[stage](), source_role='recorded-owner')
    unit.rows[('jobs', 'head')]['policy'] = recorded.to_dict()
    unit.rows[('jobs', 'head')]['policy_source'] = 'recorded'
    _, _, pins, _ = stage_buffered(unit, 'tail', stage)
    assert policies.flush_anchor_stage_pins(unit, pins) == 1
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts'][stage]
    assert 'policy_part_sources' not in anchor, 'a recorded row keeps its own provenance receipt'


def test_recorded_whole_unit_policy_guards_the_admission_pin(unit):
    from config.policy import resolve_batch_policy

    recorded = resolve_batch_policy('owner', flags={'BATCH_PIPELINE_ENABLED': 'true', 'BATCH_PIPELINE_PERCENT': '100'})
    unit.rows[('jobs', 'head')]['policy'] = recorded.to_dict()
    unit.rows[('jobs', 'head')]['policy_source'] = 'recorded'
    _, pins = commit_policy(unit, 'tail')
    assert pins == [], 'the anchor part already exists, the copy branch runs'
    assert unit.get('jobs', 'tail')['policy'] == recorded.to_dict()
    assert unit.transactions == 1, 'copy branch only: no pin transaction'


# ---------------------------------------------------------------------------
# Wrapper integration: load_stage_policy and load_job_policy flush their pins.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('stage', STAGES)
def test_load_stage_policy_stages_the_job_and_pins_the_anchor(stage, unit):
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv('K_SERVICE', 'pin-serving')
    try:
        _, policy = policies.load_stage_policy(unit, 'tail', stage)
    finally:
        monkeypatch.undo()
    anchor = unit.get('jobs', 'head')
    job = unit.get('jobs', 'tail')
    assert job['policy_parts'][stage] == policy.to_dict()
    assert anchor['policy_parts'][stage] == policy.to_dict()
    assert anchor['policy_part_sources'][stage] == 'fallback'


@pytest.mark.parametrize('stage', STAGES)
def test_load_stage_policy_post_pin_loads_converge_without_resolution(stage, unit, monkeypatch):
    policies.load_stage_policy(unit, 'tail', stage)
    monkeypatch.setattr(
        policies, 'resolve_stage_policy', lambda uid, st, **k: pytest.fail(f're-resolved {st} after pin')
    )
    _, second = policies.load_stage_policy(unit, 'mid', stage)
    _, anchor_part = policies.load_stage_policy(unit, 'head', stage)
    assert second == anchor_part


def test_load_job_policy_stages_the_row_and_pins_the_anchor(unit):
    for job in unit.jobs():
        job.pop('policy', None)
    _, policy = policies.load_job_policy(unit, 'tail')
    assert unit.get('jobs', 'tail')['policy'] == policy.to_dict()
    assert unit.get('jobs', 'head')['policy'] == policy.to_dict()
    assert unit.get('jobs', 'head')['policy_source'] == 'fallback'


def test_load_job_policy_second_load_copies_and_never_repins(unit):
    for job in unit.jobs():
        job.pop('policy', None)
    policies.load_job_policy(unit, 'tail')
    before = unit.transactions
    _, second = policies.load_job_policy(unit, 'mid')
    assert unit.transactions == before + 1, 'copy branch only: no pin transaction'
    assert unit.get('jobs', 'mid')['policy'] == second.to_dict()


def test_load_stage_policy_missing_job_stages_nothing(unit):
    before = unit.transactions
    job, policy = policies.load_stage_policy(unit, 'ghost', STAGES[0])
    assert not job and policy is None
    assert unit.transactions == before + 1, 'one read-only transaction, no pin flush'


def test_load_stage_policy_failure_to_pin_still_returns_the_staged_policy(unit):
    witness = pin_broken_store(unit)
    _, policy = policies.load_stage_policy(witness, 'tail', STAGES[0])
    assert policy is not None
    assert unit.get('jobs', 'tail')['policy_parts'][STAGES[0]] == policy.to_dict()


def test_load_job_policy_telemetry_is_emitted_once_for_the_fallback(unit, monkeypatch):
    from config.policy import telemetry

    for job in unit.jobs():
        job.pop('policy', None)
    events = []
    monkeypatch.setattr(telemetry, 'record_policy_source', lambda source, *_: events.append(source))
    policies.load_job_policy(unit, 'tail')
    assert events == ['fallback']
    policies.load_job_policy(unit, 'mid')
    assert events == ['fallback', 'fallback'], 'each first-touch row reports its own fallback observation'


@pytest.mark.parametrize('stage', STAGES)
def test_load_stage_policy_telemetry_distinguishes_fallback_from_stage(stage, unit, monkeypatch):
    from config.policy import telemetry

    events = []
    monkeypatch.setattr(telemetry, 'record_policy_source', lambda source, pid, *a, **k: events.append(source))
    policies.load_stage_policy(unit, 'tail', stage)
    assert events == ['fallback']


# ---------------------------------------------------------------------------
# Operator runs: explicit server_flags resolution and refusal semantics.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('stage', STAGES)
def test_operator_mapping_resolves_and_pins_with_its_own_provenance(stage, unit):
    flags = {'K_SERVICE': 'operator-role'}
    writes, _, pins, policy = stage_buffered(unit, 'tail', stage, server_flags=flags)
    staged = writes[('jobs', 'tail')]
    assert staged['policy_part_sources'][stage] == 'operator_server_flags'
    assert pins[0].source == 'operator_server_flags'
    assert policies.flush_anchor_stage_pins(unit, pins) == 1
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts'][stage] == policy.to_dict()
    assert anchor['policy_part_sources'][stage] == 'operator_server_flags'


@pytest.mark.parametrize('stage', STAGES)
def test_anchor_self_stage_under_absent_authority_is_refused_without_writes(stage, unit):
    with pytest.raises(policies.UnpinnedPolicyRefused):
        stage_buffered(unit, 'head', stage, server_flags=None)
    assert unit.get('jobs', 'head').get('policy_parts') is None
    assert unit.transactions == 0


@pytest.mark.parametrize('stage', STAGES)
def test_anchor_self_stage_under_operator_mapping_records_operator_provenance(stage, unit):
    writes, _, pins, _ = stage_buffered(unit, 'head', stage, server_flags={'K_SERVICE': 'operator-role'})
    assert set(writes) == {('jobs', 'head')}
    assert writes[('jobs', 'head')]['policy_part_sources'][stage] == 'operator_server_flags'
    assert pins == []


# ---------------------------------------------------------------------------
# End-state matrix: every stage x anchor state x flags mode.
# ---------------------------------------------------------------------------


def anchor_arrangement(unit, stage, state):
    if state == 'absent':
        return None
    if state == 'partial':
        unit.rows[('jobs', 'head')]['policy_parts'] = {stage: {}}
        return STAGE_TYPES[stage]()
    stamped = replace(STAGE_TYPES[stage](), source_role='pin-canonical')
    unit.rows[('jobs', 'head')]['policy_parts'] = {stage: stamped.to_dict()}
    unit.rows[('jobs', 'head')]['policy_part_sources'] = {stage: 'fallback'}
    return stamped


FLAGS_MODES = ('serving', 'mapping', 'none')


def flags_for(mode):
    if mode == 'serving':
        return PROCESS_ENVIRONMENT
    if mode == 'mapping':
        return {'K_SERVICE': 'matrix-operator'}
    return None


@pytest.mark.parametrize('stage', STAGES)
@pytest.mark.parametrize('mode', FLAGS_MODES)
@pytest.mark.parametrize('state', ('absent', 'partial', 'pinned'))
def test_stage_end_state_matrix(stage, unit, state, mode, monkeypatch):
    expected = anchor_arrangement(unit, stage, state)
    server_flags = flags_for(mode)
    if state == 'absent' and mode == 'none':
        with pytest.raises(policies.UnpinnedPolicyRefused):
            stage_and_flush(unit, 'tail', stage, server_flags=server_flags)
        assert unit.get('jobs', 'tail').get('policy_parts') is None
        assert unit.get('jobs', 'head').get('policy_parts') is None
        return
    if state == 'absent':
        monkeypatch.setenv('K_SERVICE', 'matrix-serving')
    policy, pinned, pins = stage_and_flush(unit, 'tail', stage, server_flags=server_flags)
    job = unit.get('jobs', 'tail')
    anchor = unit.get('jobs', 'head')
    if state == 'absent':
        assert pinned == 1
        assert anchor['policy_parts'][stage] == policy.to_dict()
        assert anchor['policy_part_sources'][stage] == ('fallback' if mode == 'serving' else 'operator_server_flags')
        assert job['policy_part_sources'][stage] == anchor['policy_part_sources'][stage]
    else:
        assert pinned == 0 and pins == []
        assert policy == expected
        assert job['policy_parts'][stage] == expected.to_dict()
        assert anchor['policy_parts'][stage] == (
            {} if state == 'partial' else expected.to_dict()
        ), 'the anchor stamp is never rewritten by a sibling copy'


# ---------------------------------------------------------------------------
# Legacy mode: callers without pins keep the in-transaction anchor write.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('stage', STAGES)
def test_caller_without_pins_keeps_the_in_transaction_anchor_write(stage, unit):
    writes, _, _, _ = stage_buffered(unit, 'tail', stage, pins=None)
    assert set(writes) == {('jobs', 'head'), ('jobs', 'tail')}


def test_caller_without_pins_keeps_the_whole_unit_anchor_write(unit):
    for job in unit.jobs():
        job.pop('policy', None)
    writes, _, _, _ = policy_buffered(unit, 'tail', pins=None)
    assert set(writes) == {('jobs', 'head'), ('jobs', 'tail')}


@pytest.mark.parametrize('stage', STAGES)
def test_legacy_anchor_write_records_the_same_provenance(stage, unit):
    writes, _, _, _ = stage_buffered(unit, 'tail', stage, pins=None)
    for sid in ('head', 'tail'):
        row = writes[('jobs', sid)]
        assert row['policy_parts'][stage]
        assert row['policy_part_sources'][stage] == 'fallback'


# ---------------------------------------------------------------------------
# Anchor selection: the pin always targets the sibling unit_anchor picks.
# ---------------------------------------------------------------------------


def test_binding_without_head_pins_the_next_extant_sibling(unit):
    unit.rows.pop(('jobs', 'head'))
    _, _, pins, _ = stage_buffered(unit, 'tail', STAGES[0])
    assert pins[0].segment_id == 'mid'
    assert policies.flush_anchor_stage_pins(unit, pins) == 1
    assert unit.get('jobs', 'mid')['policy_parts'][STAGES[0]]


def test_binding_without_mid_still_pins_the_head(unit):
    unit.rows.pop(('jobs', 'mid'))
    _, _, pins, _ = stage_buffered(unit, 'tail', STAGES[0])
    assert pins[0].segment_id == 'head'


def test_privacy_blocked_head_promotes_mid_to_the_anchor(unit):
    unit.customer.delete_conversation('owner', 'sealed')
    unit.rows[('jobs', 'head')]['conversation_id'] = 'sealed'
    _, _, pins, _ = stage_buffered(unit, 'tail', STAGES[0])
    assert pins[0].segment_id == 'mid'


def test_privacy_blocked_head_and_mid_promote_tail_to_self_anchor(unit):
    unit.customer.delete_conversation('owner', 'sealed')
    unit.rows[('jobs', 'head')]['conversation_id'] = 'sealed'
    unit.rows[('jobs', 'mid')]['conversation_id'] = 'sealed'
    writes, _, pins, _ = stage_buffered(unit, 'tail', STAGES[0])
    assert set(writes) == {('jobs', 'tail')}
    assert pins == [], 'every sibling blocked, the job self-anchors'


@pytest.mark.parametrize('stage', STAGES)
def test_stage_pin_part_carries_the_stage_stable_default_identity(stage, unit):
    _, _, pins, policy = stage_buffered(unit, 'tail', stage)
    assert pins[0].part['source_role'] == policy.to_dict()['source_role']
    assert policies.flush_anchor_stage_pins(unit, pins) == 1
    assert unit.get('jobs', 'head')['policy_parts'][stage] == policy.to_dict()


@pytest.mark.parametrize('stage', STAGES)
def test_wrapper_refuses_an_absent_part_without_server_flags(stage, unit):
    with pytest.raises(policies.UnpinnedPolicyRefused) as refused:
        policies.load_stage_policy(unit, 'tail', stage, server_flags=None)
    assert refused.value.stage == stage
    assert unit.get('jobs', 'tail').get('policy_parts') is None
    assert unit.get('jobs', 'head').get('policy_parts') is None


@pytest.mark.parametrize('stage', STAGES)
def test_wrapper_deferred_pin_logs_the_stage(stage, unit, caplog):
    witness = pin_broken_store(unit)
    with caplog.at_level('WARNING', logger='database.batch_pipeline_policy'):
        policies.load_stage_policy(witness, 'tail', stage)
    deferred = [record for record in caplog.records if 'outcome=deferred' in record.getMessage()]
    assert deferred and f'stage={stage}' in deferred[0].getMessage()


@pytest.mark.parametrize('stage', STAGES)
def test_retried_body_emits_duplicates_but_one_pin_transaction_lands(stage, unit):
    from testing.pipeline_sim.store import SimTransaction

    original = unit.run
    attempts = {'count': 0}

    def twice(body, *, operation=None):
        attempts['count'] += 1
        body(SimTransaction(unit))  # the aborted attempt discards its writes
        return original(body, operation=operation)

    unit.run = twice  # type: ignore[assignment]
    try:
        before = unit.transactions
        policies.load_stage_policy(unit, 'tail', stage)
    finally:
        del unit.run  # restore the SimStore method
    anchor = unit.get('jobs', 'head')
    assert anchor['policy_parts'][stage]
    assert unit.get('jobs', 'tail')['policy_parts'][stage] == anchor['policy_parts'][stage]
    assert unit.transactions == before + 2, 'one staging transaction plus one deduped pin transaction'
    assert attempts['count'] == 2, 'both transaction bodies replayed once'


@pytest.mark.parametrize('stage', STAGES)
@pytest.mark.parametrize('mode', FLAGS_MODES)
def test_self_anchor_end_state_matrix(stage, unit, mode, monkeypatch):
    """anchor == job: one row staged, no descriptor, no pin transaction."""
    lone = make_store(siblings=('lone',))
    lone.rows[('jobs', 'lone')]['projection_binding']['segment_ids'] = ('lone',)
    server_flags = flags_for(mode)
    if mode == 'none':
        with pytest.raises(policies.UnpinnedPolicyRefused):
            stage_and_flush(lone, 'lone', stage, server_flags=server_flags)
        assert lone.get('jobs', 'lone').get('policy_parts') is None
        return
    if mode == 'serving':
        monkeypatch.setenv('K_SERVICE', 'matrix-serving')
    policy, pinned, pins = stage_and_flush(lone, 'lone', stage, server_flags=server_flags)
    row = lone.get('jobs', 'lone')
    assert pinned == 0 and pins == []
    assert row['policy_parts'][stage] == policy.to_dict()
    assert row['policy_part_sources'][stage] == ('fallback' if mode == 'serving' else 'operator_server_flags')


@pytest.mark.parametrize('stage', STAGES)
def test_whole_unit_matrix_absent_part_pins_the_anchor(stage):
    """Whole-unit policy has its own two-state matrix: absent pins, present copies."""
    unit = make_store()
    for job in unit.jobs():
        job.pop('policy', None)
    writes, _, pins, policy = policy_buffered(unit, 'tail')
    assert set(writes) == {('jobs', 'tail')}
    assert pins[0].segment_id == 'head' and pins[0].stage == 'admission'
    assert policies.flush_anchor_stage_pins(unit, pins) == 1
    assert unit.get('jobs', 'head')['policy'] == policy.to_dict()
    assert unit.get('jobs', 'head')['policy_source'] == 'fallback'
    assert writes[('jobs', 'tail')]['policy'] == policy.to_dict()


def test_whole_unit_matrix_present_part_copies_without_a_pin(unit):
    from config.policy import resolve_batch_policy

    pinned = resolve_batch_policy('owner', flags={'BATCH_PIPELINE_ENABLED': 'true', 'BATCH_PIPELINE_PERCENT': '100'})
    unit.rows[('jobs', 'head')]['policy'] = pinned.to_dict()
    unit.rows[('jobs', 'head')]['policy_source'] = 'recorded'
    writes, _, pins, policy = policy_buffered(unit, 'tail')
    assert set(writes) == {('jobs', 'tail')}
    assert pins == []
    assert policy.to_dict() == pinned.to_dict()
    assert writes[('jobs', 'tail')]['policy_source'] == 'fallback', 'serving copies keep the fallback receipt'


@pytest.mark.parametrize('stage', STAGES)
def test_flush_failure_message_names_the_deferred_stage(stage, unit, caplog):
    _, _, pins, _ = stage_buffered(unit, 'tail', stage)
    witness = pin_broken_store(unit)
    with caplog.at_level('WARNING', logger='database.batch_pipeline_policy'):
        policies.flush_anchor_stage_pins(witness, pins)
    assert any(f'stage={stage}' in record.getMessage() for record in caplog.records)
