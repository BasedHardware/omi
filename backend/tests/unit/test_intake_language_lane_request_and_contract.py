"""Request-level lane resolution and the provider lane's admission contract.

``intake_request_language_lane`` flips a request to the provider lane exactly
when one unit plan demands it and the request is not already there. The flip
reuses the C8 provider route vocabulary, so the staged jobs, the policy fields
and the outbox enqueue all keep one closed shape.
"""

from dataclasses import asdict, replace

import pytest

from config.batch_pipeline import known_unsupported_batch_language
from utils.batch_pipeline.contracts import Priority
from config.batch_pipeline_language import (
    IntakeRequestLanguagePlan,
    IntakeUnitLanguagePlan,
    intake_request_language_lane,
    intake_unit_language_plan,
)
from config.policy import BatchUnitPolicy
from utils.batch_pipeline.provider_stt_admission import (
    PENDING,
    SttRoute,
    enqueue_in_transaction,
)
from utils.batch_pipeline.scheduler import owner_key


def unit_plan(lane='parakeet', reason='decision_parakeet_safe', frozen='en'):
    return IntakeUnitLanguagePlan(lane, reason, frozen)


def speech_plan(frozen='und', reason='unknown_speech'):
    return IntakeUnitLanguagePlan('multilingual', reason, frozen)


def test_all_parakeet_plans_keep_the_callers_route():
    plans = [unit_plan(), unit_plan('parakeet', 'silent_or_unresolved_barrier', 'und')]
    assert intake_request_language_lane(plans, stt_route='parakeet').provider_lane is False


def test_all_parakeet_plans_carry_no_flip_reason():
    plans = [unit_plan(), unit_plan()]
    assert intake_request_language_lane(plans, stt_route='parakeet').reason is None


def test_all_parakeet_plans_carry_no_flip_language():
    plans = [unit_plan()]
    assert intake_request_language_lane(plans, stt_route='parakeet').language == ''


def test_one_speech_plan_flips_the_whole_request():
    plans = [unit_plan(), speech_plan()]
    assert intake_request_language_lane(plans, stt_route='parakeet').provider_lane is True


def test_the_flip_names_the_flipping_units_reason():
    plans = [unit_plan(), speech_plan(reason='detected_unsupported_speech')]
    assert intake_request_language_lane(plans, stt_route='parakeet').reason == 'detected_unsupported_speech'


def test_the_flip_carries_the_flipping_units_frozen_language():
    plans = [unit_plan(), speech_plan(frozen='ja')]
    assert intake_request_language_lane(plans, stt_route='parakeet').language == 'ja'


def test_an_already_provider_request_never_flips_again():
    plans = [speech_plan()]
    assert intake_request_language_lane(plans, stt_route='provider').provider_lane is False


def test_an_already_provider_request_keeps_its_own_reason_none():
    plans = [speech_plan()]
    resolved = intake_request_language_lane(plans, stt_route='provider')
    assert resolved.reason is None


def test_an_already_provider_request_still_reports_the_unit_language():
    plans = [speech_plan(frozen='ja')]
    assert intake_request_language_lane(plans, stt_route='provider').language == 'ja'


def test_the_first_speech_plan_wins_the_flip_reason():
    plans = [speech_plan(reason='unknown_speech'), speech_plan(reason='detected_unsupported_speech', frozen='ja')]
    resolved = intake_request_language_lane(plans, stt_route='parakeet')
    assert resolved.reason == 'unknown_speech' and resolved.language == 'und'


def test_empty_plans_never_flip():
    assert intake_request_language_lane([], stt_route='parakeet').provider_lane is False


def test_the_flip_plan_is_frozen_data():
    value = intake_request_language_lane([speech_plan()], stt_route='parakeet')
    with pytest.raises(Exception):
        value.provider_lane = False


def test_request_plan_defaults_describe_a_non_flip():
    value = IntakeRequestLanguagePlan(False, None, '')
    assert (value.provider_lane, value.reason, value.language) == (False, None, '')


def test_flip_route_matches_the_c8_provider_vocabulary():
    flipped = SttRoute('provider', 'unsupported_language', 'modulate', 'und')
    assert asdict(flipped) == {
        'stt_route': 'provider',
        'provider_reason': 'unsupported_language',
        'provider_service': 'modulate',
        'language': 'und',
    }


def test_flip_route_names_exactly_one_provider_service():
    with pytest.raises(ValueError):
        SttRoute('provider', 'unsupported_language', 'none', 'und')


def test_flip_route_rejects_a_parakeet_route_with_a_service():
    with pytest.raises(ValueError):
        SttRoute('parakeet', 'none', 'modulate', 'en')


def test_flip_route_rejects_an_off_vocabulary_reason():
    with pytest.raises(ValueError):
        SttRoute('provider', 'unknown_speech', 'modulate', 'und')


def test_flip_route_rejects_an_empty_language():
    with pytest.raises(ValueError):
        SttRoute('provider', 'unsupported_language', 'modulate', '')


def test_flip_route_bounds_the_language():
    with pytest.raises(ValueError):
        SttRoute('provider', 'unsupported_language', 'modulate', 'x' * 17)


def test_flip_route_keeps_a_bounded_detected_code():
    assert SttRoute('provider', 'unsupported_language', 'modulate', 'ja').language == 'ja'


def test_resolve_route_keeps_declared_multi_on_parakeet_as_legacy():
    from utils.batch_pipeline.provider_stt_admission import resolve_route

    assert resolve_route('multi').stt_route == 'parakeet'


def test_resolve_route_keeps_blank_declarations_on_parakeet_as_legacy():
    from utils.batch_pipeline.provider_stt_admission import resolve_route

    assert resolve_route('').stt_route == 'parakeet'


def test_resolve_route_sends_und_to_the_provider_lane():
    from utils.batch_pipeline.provider_stt_admission import resolve_route

    assert resolve_route('und').stt_route == 'provider'


def test_resolve_route_names_modulate_for_und():
    from utils.batch_pipeline.provider_stt_admission import resolve_route

    assert resolve_route('und').provider_service == 'modulate'


def test_resolve_route_names_the_unsupported_reason_for_und():
    from utils.batch_pipeline.provider_stt_admission import resolve_route

    assert resolve_route('und').provider_reason == 'unsupported_language'


def test_resolve_route_sends_detected_unsupported_codes_to_the_provider_lane():
    from utils.batch_pipeline.provider_stt_admission import resolve_route

    assert resolve_route('ja').stt_route == 'provider'


def test_resolve_route_bounds_the_multi_normalized_blank():
    from utils.batch_pipeline.provider_stt_admission import resolve_route

    assert resolve_route('').language == 'multi'


def test_resolve_route_keeps_supported_languages_on_parakeet():
    from utils.batch_pipeline.provider_stt_admission import resolve_route

    assert resolve_route('en').stt_route == 'parakeet'


def test_resolve_route_records_no_service_for_supported_languages():
    from utils.batch_pipeline.provider_stt_admission import resolve_route

    assert resolve_route('en').provider_service == 'none'


def test_declared_unsupported_names_never_admit_to_batch_gpu():
    assert known_unsupported_batch_language('ja') is True


def test_declared_multi_is_not_known_unsupported():
    assert known_unsupported_batch_language('multi') is False


def test_declared_blank_is_not_known_unsupported():
    assert known_unsupported_batch_language('') is False


def test_declared_und_is_not_known_unsupported():
    assert known_unsupported_batch_language('und') is False


def test_declared_en_is_not_known_unsupported():
    assert known_unsupported_batch_language('en') is False


def test_provider_policy_fields_mirror_the_flip_route():
    policy = BatchUnitPolicy(batch_enabled=True, live_admission_enabled=True, live_record_enabled=False)
    flipped = SttRoute('provider', 'unsupported_language', 'modulate', 'und')
    updated = replace(
        policy,
        stt_route=flipped.stt_route,
        provider_reason=flipped.provider_reason,
        provider_service=flipped.provider_service,
    )
    assert updated.stt_route == 'provider'
    assert updated.provider_reason == 'unsupported_language'
    assert updated.provider_service == 'modulate'


def test_the_flip_leaves_other_policy_fields_untouched():
    policy = BatchUnitPolicy(batch_enabled=True, live_admission_enabled=True, live_record_enabled=False)
    updated = replace(
        policy,
        stt_route='provider',
        provider_reason='unsupported_language',
        provider_service='modulate',
    )
    assert updated.batch_enabled is True
    assert updated.live_admission_enabled is True
    assert updated.live_record_enabled is False


def test_flip_route_replaces_the_route_object_without_mutating_it():
    original = SttRoute('parakeet', 'none', 'none', 'multi')
    flipped = replace(
        original, stt_route='provider', provider_reason='unsupported_language', provider_service='modulate'
    )
    assert original.stt_route == 'parakeet'
    assert flipped.stt_route == 'provider'


def test_provider_units_stage_without_compute_admission():
    from tests.unit.test_batch_pipeline_scheduler import item

    assert replace(item('seg', owner='owner-x'), requires_compute_admission=False).requires_compute_admission is False


def test_compute_units_keep_compute_admission():
    from tests.unit.test_batch_pipeline_scheduler import item

    assert replace(item('seg', owner='owner-x'), requires_compute_admission=True).requires_compute_admission is True


def _run_enqueue(store, work, route, *, now=100.0, policy=None):
    from config.policy import BatchUnitPolicy as BUP

    return store.run(lambda tx: enqueue_in_transaction(tx, work, now, route=route, policy=policy or BUP()))


def _admit_store():
    from tests.unit.test_batch_pipeline_scheduler import MemoryStore

    store = MemoryStore()
    return store


def _provider_item(segment='seg', owner='provider-owner', frozen='und'):
    from tests.unit.test_batch_pipeline_scheduler import item

    route = SttRoute('provider', 'unsupported_language', 'modulate', frozen)
    work = replace(item(segment, owner=owner), requires_compute_admission=False, priority=Priority.DEEP)
    return work, route


def test_provider_route_enqueues_a_pending_job_outside_the_gpu_ring():
    store = _admit_store()
    work, route = _provider_item()
    assert _run_enqueue(store, work, route) is True


def test_provider_job_lands_in_the_pending_state():
    store = _admit_store()
    work, route = _provider_item()
    work, route = _provider_item()
    _run_enqueue(store, work, route)
    assert store.rows['jobs', 'seg']['state'] == PENDING


def test_provider_job_carries_the_closed_route_dict():
    store = _admit_store()
    work, route = _provider_item()
    work, route = _provider_item()
    _run_enqueue(store, work, route)
    assert store.rows['jobs', 'seg']['stt_route'] == asdict(route)


def test_provider_job_never_enters_the_merge_ring():
    store = _admit_store()
    work, route = _provider_item()
    work, route = _provider_item()
    _run_enqueue(store, work, route)
    job = store.rows['jobs', 'seg']
    assert job['merge_pending'] is True and job['token'] == ''


def test_provider_route_refuses_compute_admission_items():
    store = _admit_store()
    work, route = _provider_item()
    compute = replace(work, requires_compute_admission=True)
    with pytest.raises(ValueError, match='provider units are funded by the provider stage'):
        _run_enqueue(store, compute, route)


def test_provider_route_refuses_a_parakeet_route():
    store = _admit_store()
    work, _ = _provider_item()
    parakeet = SttRoute('parakeet', 'none', 'none', 'en')
    with pytest.raises(ValueError, match='only provider routes'):
        _run_enqueue(store, work, parakeet)


def test_provider_replay_of_the_same_immutable_work_is_idempotent():
    store = _admit_store()
    work, route = _provider_item()
    assert _run_enqueue(store, work, route) is True
    assert _run_enqueue(store, work, route, now=200.0) is False


def test_provider_replay_with_a_different_route_refuses_the_segment():
    store = _admit_store()
    work, route = _provider_item()
    _run_enqueue(store, work, route)
    other = SttRoute('provider', 'unsupported_language', 'modulate', 'ja')
    with pytest.raises(ValueError, match='different immutable work'):
        _run_enqueue(store, work, other, now=200.0)


def test_provider_admission_bumps_the_owner_revision_once():
    store = _admit_store()
    work, route = _provider_item()
    _run_enqueue(store, work, route)
    assert store.rows['owners', owner_key('provider-owner')]['revision'] == 1


def test_gpu_pull_never_leases_a_provider_job():
    from utils.batch_pipeline.scheduler import Scheduler

    store = _admit_store()
    work, route = _provider_item()
    _run_enqueue(store, work, route)
    assert Scheduler(store).pull(1000.0) == []


def test_gpu_pull_leases_a_compute_job_for_the_same_owner():
    from utils.batch_pipeline.scheduler import Scheduler
    from tests.unit.test_batch_pipeline_scheduler import item

    store = _admit_store()
    work, route = _provider_item()
    _run_enqueue(store, work, route)
    compute = replace(item('gpu-seg', owner='provider-owner'), requires_compute_admission=True)
    Scheduler(store).enqueue(compute, 150.0)
    leased = Scheduler(store).pull(1000.0)
    assert [lease.item.segment_id for lease in leased] == ['gpu-seg']


def test_unit_plan_freeze_matches_the_parent_expression_for_safe_decisions():
    decision = 'en'
    parent = decision if True else 'und'
    assert (
        intake_unit_language_plan(
            decision_language=decision,
            parakeet_safe=True,
            strict_speech=None,
            input_language='multi',
            language_guard=True,
        ).frozen_language
        == parent
    )


def test_unit_plan_freeze_matches_the_parent_expression_for_unsupported_decisions():
    decision = 'ja'
    parent = decision
    assert (
        intake_unit_language_plan(
            decision_language=decision,
            parakeet_safe=False,
            strict_speech=False,
            input_language='multi',
            language_guard=True,
        ).frozen_language
        == parent
    )


def test_unit_plan_freeze_matches_the_parent_expression_for_unknown_decisions():
    parent = 'und'
    assert (
        intake_unit_language_plan(
            decision_language='und',
            parakeet_safe=False,
            strict_speech=False,
            input_language='multi',
            language_guard=True,
        ).frozen_language
        == parent
    )


def test_unit_plan_freeze_matches_the_parent_expression_with_the_guard_off():
    assert (
        intake_unit_language_plan(
            decision_language='und', parakeet_safe=False, strict_speech=None, input_language='ko', language_guard=False
        ).frozen_language
        == 'ko'
    )


def test_unit_plan_freeze_never_regresses_a_detected_code_to_und_when_silent():
    assert (
        intake_unit_language_plan(
            decision_language='ar', parakeet_safe=False, strict_speech=None, input_language='multi', language_guard=True
        ).frozen_language
        == 'ar'
    )


def test_unit_plan_freeze_keeps_und_for_unresolved_unknown_speech_cells():
    assert (
        intake_unit_language_plan(
            decision_language='und',
            parakeet_safe=False,
            strict_speech=True,
            input_language='multi',
            language_guard=True,
        ).frozen_language
        == 'und'
    )


def test_unit_plan_freeze_keeps_the_detected_code_for_proven_unsupported_speech():
    assert (
        intake_unit_language_plan(
            decision_language='ja', parakeet_safe=False, strict_speech=True, input_language='multi', language_guard=True
        ).frozen_language
        == 'ja'
    )
