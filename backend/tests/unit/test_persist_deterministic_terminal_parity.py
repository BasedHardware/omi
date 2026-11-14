#!/usr/bin/env python3
"""A persist refusal identical input reproduces ends the chain with custody.

A 400-class ``InvalidArgument`` the persist stage raises for a unit's own
request payload used to book an ordinary retryable worker fault: the
re-strike lane burned its budget against the identical payload, the job
ladder re-ran the full GPU pipeline for every remaining attempt only to
raise the same refusal at the same boundary, and the exhausted unit
quarantined blind before the recovery re-run fed the same bytes through
the whole cycle again. The boundary now reads the refusal's type through
the shared contention classifier — never its message — and books the
typed ``persist_payload_invalid`` custody handoff the decode trio rides:
the chain ends at its first occurrence, custody stays intact for the
fenced recovery lane whose fresh provider payload is the escape the
refusal could never produce in-place, and the expired-chain contention
shape keeps its storm-windowed replay arm.

Failure-Class: FC-deterministic-persist-refusal-walks-gpu-retry-ladder-as-unclassified-invalidargument
"""

import logging

from google.api_core.exceptions import Aborted, InternalServerError, InvalidArgument

from diarizer import batch_pipeline as bp
from utils.batch_pipeline.contracts import FailedWork, WorkResult
from tests.unit.persist_lane_harness import (
    GATE,
    PerSegmentPersist,
    ScriptedPersist,
    WORKER_LOGGER,
    build_worker,
    contention,
    exhaust_script,
    item,
    pin_full_gpu_stages,
    run_lane,
    run_two_units,
    script_for,
)

FC = 'FC-deterministic-persist-refusal-walks-gpu-retry-ladder-as-unclassified-invalidargument'

EXPIRY_MESSAGE = '400 The referenced transaction has expired or is no longer valid'


def expiry_fault(message=EXPIRY_MESSAGE):
    return InvalidArgument(message)


def from_aborted_cause():
    try:
        try:
            raise Aborted('row locked')
        except Aborted as cause:
            raise InvalidArgument('refused mid-flight') from cause
    except InvalidArgument as error:
        return error


# --- The boundary booking -------------------------------------------------------


def test_exhausted_refusal_books_the_typed_custody_handoff(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].segment_id == 'a'
    assert run['results'][0].stage == 'persist'
    assert run['results'][0].reason == 'persist_payload_invalid'


def test_the_handoff_is_independent_of_the_safety_net(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), safety_net='true')
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].reason == 'persist_payload_invalid'


def test_the_gate_off_books_the_same_handoff_on_the_first_call(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), gate='false')
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].reason == 'persist_payload_invalid'
    assert len(run['persist'].calls) == 1 and run['sleeps'].delays == []


def test_a_custom_wording_books_the_same_handoff(monkeypatch):
    # The verdict reads the type through the shared classifier, never the
    # message: any 400-class wording is the same deterministic refusal.
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument('totally-custom-refusal')] * 3, default='OK'))
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].reason == 'persist_payload_invalid'


def test_a_case_variant_expiry_wording_keeps_the_transport_booking(monkeypatch):
    # The expired-chain shape is contention: the storm-windowed replay arm
    # stays authoritative and the booking stays the legacy retryable fault.
    script = ScriptedPersist([expiry_fault('Please Transaction Has Expired just now')] * 3, default='OK')
    run = run_lane(monkeypatch, script, safety_net='true')
    assert [type(r).__name__ for r in run['results']] == ['FailedWork']
    assert run['results'][0].worker_failure == {'stage': 'persist', 'reason': 'unknown'}


def test_an_aborted_cause_chain_keeps_the_transport_booking(monkeypatch):
    fault = from_aborted_cause()
    script = ScriptedPersist([fault] * 3, default=InvalidArgument('refused mid-flight'))
    run = run_lane(monkeypatch, script, safety_net='true')
    assert [type(r).__name__ for r in run['results']] == ['FailedWork']
    assert run['results'][0].worker_failure == {'stage': 'persist', 'reason': 'unknown'}


def test_the_expired_shape_rides_the_lane_to_its_cap(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([expiry_fault()] * 3, default=expiry_fault()), safety_net='true')
    assert len(run['persist'].calls) == 3 and run['sleeps'].delays == [0.25, 0.5]
    assert [type(r).__name__ for r in run['results']] == ['FailedWork']


def test_the_refusal_rides_the_lane_to_its_cap_before_the_handoff(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())
    assert len(run['persist'].calls) == 3 and run['sleeps'].delays == [0.25, 0.5]


def test_the_handoff_keeps_the_gpu_chain_at_one_pass(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())
    assert run['meta']['decoded'] == ['a']
    assert run['worker'].counts['items'] == 1


def test_the_handoff_keeps_the_failure_callback_contract(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_a_shadow_unit_books_the_same_handoff(monkeypatch):
    from dataclasses import replace

    run = run_lane(monkeypatch, exhaust_script(), unit=replace(item(), shadow=True))
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].reason == 'persist_payload_invalid'


def test_a_recovered_unit_still_commits(monkeypatch):
    run = run_lane(monkeypatch, script_for(1))
    assert [type(r).__name__ for r in run['results']] == ['WorkResult']


def test_a_sibling_refusal_does_not_poison_its_neighbor(monkeypatch):
    routes = PerSegmentPersist({'a': exhaust_script(), 'b': ScriptedPersist([])})
    run = run_two_units(monkeypatch, routes)
    assert [(r.segment_id, type(r).__name__) for r in run['results']] == [
        ('a', 'ValidationFailureWork'),
        ('b', 'WorkResult'),
    ]


# --- Transport and contention parity (unchanged families) ------------------------


def test_a_transport_exhaustion_still_books_the_retryable_fault(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(TimeoutError), safety_net='true')
    assert [type(r).__name__ for r in run['results']] == ['FailedWork']
    assert run['results'][0].worker_failure == {'stage': 'persist', 'reason': 'unknown'}


def test_a_server_fault_exhaustion_still_books_the_retryable_fault(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(InternalServerError), safety_net='true')
    assert [type(r).__name__ for r in run['results']] == ['FailedWork']
    assert run['results'][0].worker_failure == {'stage': 'persist', 'reason': 'unknown'}


def test_a_contention_loss_still_rides_the_storm_stamp(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([contention(2.0), 'OK']))
    assert run['sleeps'].delays == [2.0]
    assert [type(r).__name__ for r in run['results']] == ['WorkResult']


def test_a_contention_exhaustion_still_books_the_retryable_fault(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([contention()] * 3, default=contention()), safety_net='true')
    assert [type(r).__name__ for r in run['results']] == ['FailedWork']
    assert run['results'][0].worker_failure == {'stage': 'persist', 'reason': 'unknown'}


def test_a_staged_audio_fault_still_books_its_own_typed_handoff(monkeypatch):
    from utils.batch_pipeline.audio import StagedAudioInvalid

    run = run_lane(
        monkeypatch,
        ScriptedPersist([], default='OK'),
        decode=lambda work: (_ for _ in ()).throw(StagedAudioInvalid('garbage container')),
        safety_net='true',
    )
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].stage == 'fetch_decode'
    assert run['results'][0].reason == 'staged_audio_invalid'


# --- The classifier --------------------------------------------------------------


def test_the_classifier_answers_for_the_refusal():
    assert bp.persist_loss_is_deterministic(InvalidArgument('burst')) is True


def test_the_classifier_defers_the_expired_chain_shape():
    assert bp.persist_loss_is_deterministic(expiry_fault()) is False


def test_the_classifier_defers_a_cause_chain_contention():
    assert bp.persist_loss_is_deterministic(from_aborted_cause()) is False


def test_the_classifier_defers_every_non_refusal_class():
    for fault in (
        TimeoutError('burst'),
        InternalServerError('burst'),
        Aborted('row locked'),
        contention(),
        OSError('socket dropped'),
    ):
        assert bp.persist_loss_is_deterministic(fault) is False


def test_the_classifier_never_raises_on_hostile_input():
    for hostile in (None, 7, 'burst', True, object()):
        assert bp.persist_loss_is_deterministic(hostile) is False


# --- Source and doc parity -------------------------------------------------------


def test_the_boundary_reads_the_classifier_not_the_message():
    source = __import__('pathlib').Path(bp.__file__).read_text()
    assert 'persist_loss_is_deterministic(' in source
    assert 'isinstance' not in source.split('def persist_loss_is_deterministic')[1].split('\ndef ')[0].split('"""')[1]


def test_the_handoff_arm_rides_the_validation_failure_route():
    source = __import__('pathlib').Path(bp.__file__).read_text()
    arm = source.split('persist_payload_invalid = (')[1].split('state = states.get')[0]
    assert 'PERSIST_PAYLOAD_INVALID' in arm
    assert 'or persist_payload_invalid' in source


def test_the_classifier_docstring_carries_the_failure_class():
    source = __import__('pathlib').Path(bp.__file__).read_text()
    block = source.split('def persist_loss_is_deterministic')[1].split('def ')[0]
    assert f'Failure-Class: {FC}' in block


def test_the_doc_names_the_class_and_both_channels():
    from pathlib import Path

    doc = Path(bp.__file__).resolve().parents[1] / 'docs' / 'batch-persist-deterministic-terminal-parity.md'
    assert doc.exists()
    text = doc.read_text()
    assert FC in text
    assert 'event=batch_worker_failed error_class=InvalidArgument' in text
    assert 'event=batch_validation_disposition' in text
