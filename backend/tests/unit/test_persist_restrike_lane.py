#!/usr/bin/env python3
"""Worker-integration matrix for the persist re-strike lane.

Every cell drives the real PipelineWorker.process_batch with a scripted persist and pins
one literal facet: recovery after 0-3 strikes on both the serial and IO-executor call
sites, exhaustion booking the legacy fault, the GPU chain running exactly once across
strikes, payload and timing-span identity, and independence across sibling units.

Failure-Class: FC-persist-transport-loss-discards-completed-gpu-results
"""

import logging

import pytest
from google.api_core.exceptions import InvalidArgument, InternalServerError, ServiceUnavailable
from google.api_core.exceptions import DeadlineExceeded

from dataclasses import replace

from diarizer import batch_pipeline as bp
from utils.batch_pipeline.contracts import FailedWork, WorkResult
from tests.unit.persist_lane_harness import (
    GATE,
    RecordingTimings,
    ScriptedPersist,
    SleepRecorder,
    WORKER_LOGGER,
    build_worker,
    exhaust_script,
    item,
    PerSegmentPersist,
    pin_full_gpu_stages,
    run_lane,
    run_two_units,
    script_for,
)


@pytest.fixture(autouse=True)
def _lane_env(monkeypatch):
    pin_full_gpu_stages(monkeypatch)


def test_recovery_0_strikes_serial_returns_the_completed_work_result(monkeypatch):
    run = run_lane(monkeypatch, script_for(0))

    assert len(run['results']) == 1 and isinstance(run['results'][0], WorkResult)


def test_recovery_0_strikes_serial_reports_the_final_strike_uri(monkeypatch):
    run = run_lane(monkeypatch, script_for(0))

    assert run['results'][0].result_uri == 'OK'


def test_recovery_0_strikes_serial_keeps_the_success_outcome(monkeypatch):
    run = run_lane(monkeypatch, script_for(0))

    assert run['results'][0].outcome == 'success'


def test_recovery_0_strikes_serial_persists_1_times(monkeypatch):
    run = run_lane(monkeypatch, script_for(0))

    assert run['persist'].calls.count('a') == 1


def test_recovery_0_strikes_serial_sleeps_the_documented_schedule(monkeypatch):
    run = run_lane(monkeypatch, script_for(0))

    assert run['sleeps'].delays == []


def test_recovery_0_strikes_serial_books_no_worker_fault(monkeypatch):
    run = run_lane(monkeypatch, script_for(0))

    assert run['meta']['failures'] == [] and run['worker'].counts['failed'] == 0


def test_recovery_0_strikes_serial_runs_the_gpu_chain_once(monkeypatch):
    run = run_lane(monkeypatch, script_for(0))

    assert run['meta']['decoded'] == ['a'] and run['meta']['diarized'] == [32000]


def test_recovery_0_strikes_serial_hands_the_same_payload_to_every_strike(monkeypatch):
    run = run_lane(monkeypatch, script_for(0))

    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_recovery_0_strikes_serial_opens_a_persist_span_per_strike(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, script_for(0), timings=timings)

    assert timings.spans.count('persist') == 1


def test_recovery_1_strikes_serial_returns_the_completed_work_result(monkeypatch):
    run = run_lane(monkeypatch, script_for(1))

    assert len(run['results']) == 1 and isinstance(run['results'][0], WorkResult)


def test_recovery_1_strikes_serial_reports_the_final_strike_uri(monkeypatch):
    run = run_lane(monkeypatch, script_for(1))

    assert run['results'][0].result_uri == 'OK'


def test_recovery_1_strikes_serial_keeps_the_success_outcome(monkeypatch):
    run = run_lane(monkeypatch, script_for(1))

    assert run['results'][0].outcome == 'success'


def test_recovery_1_strikes_serial_persists_2_times(monkeypatch):
    run = run_lane(monkeypatch, script_for(1))

    assert run['persist'].calls.count('a') == 2


def test_recovery_1_strikes_serial_sleeps_the_documented_schedule(monkeypatch):
    run = run_lane(monkeypatch, script_for(1))

    assert run['sleeps'].delays == [0.25]


def test_recovery_1_strikes_serial_books_no_worker_fault(monkeypatch):
    run = run_lane(monkeypatch, script_for(1))

    assert run['meta']['failures'] == [] and run['worker'].counts['failed'] == 0


def test_recovery_1_strikes_serial_runs_the_gpu_chain_once(monkeypatch):
    run = run_lane(monkeypatch, script_for(1))

    assert run['meta']['decoded'] == ['a'] and run['meta']['diarized'] == [32000]


def test_recovery_1_strikes_serial_hands_the_same_payload_to_every_strike(monkeypatch):
    run = run_lane(monkeypatch, script_for(1))

    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_recovery_1_strikes_serial_opens_a_persist_span_per_strike(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, script_for(1), timings=timings)

    assert timings.spans.count('persist') == 2


def test_recovery_2_strikes_serial_returns_the_completed_work_result(monkeypatch):
    run = run_lane(monkeypatch, script_for(2))

    assert len(run['results']) == 1 and isinstance(run['results'][0], WorkResult)


def test_recovery_2_strikes_serial_reports_the_final_strike_uri(monkeypatch):
    run = run_lane(monkeypatch, script_for(2))

    assert run['results'][0].result_uri == 'OK'


def test_recovery_2_strikes_serial_keeps_the_success_outcome(monkeypatch):
    run = run_lane(monkeypatch, script_for(2))

    assert run['results'][0].outcome == 'success'


def test_recovery_2_strikes_serial_persists_3_times(monkeypatch):
    run = run_lane(monkeypatch, script_for(2))

    assert run['persist'].calls.count('a') == 3


def test_recovery_2_strikes_serial_sleeps_the_documented_schedule(monkeypatch):
    run = run_lane(monkeypatch, script_for(2))

    assert run['sleeps'].delays == [0.25, 0.5]


def test_recovery_2_strikes_serial_books_no_worker_fault(monkeypatch):
    run = run_lane(monkeypatch, script_for(2))

    assert run['meta']['failures'] == [] and run['worker'].counts['failed'] == 0


def test_recovery_2_strikes_serial_runs_the_gpu_chain_once(monkeypatch):
    run = run_lane(monkeypatch, script_for(2))

    assert run['meta']['decoded'] == ['a'] and run['meta']['diarized'] == [32000]


def test_recovery_2_strikes_serial_hands_the_same_payload_to_every_strike(monkeypatch):
    run = run_lane(monkeypatch, script_for(2))

    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_recovery_2_strikes_serial_opens_a_persist_span_per_strike(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, script_for(2), timings=timings)

    assert timings.spans.count('persist') == 3


def test_recovery_0_strikes_io_returns_the_completed_work_result(monkeypatch):
    run = run_lane(monkeypatch, script_for(0), io_concurrency=2)

    assert len(run['results']) == 1 and isinstance(run['results'][0], WorkResult)


def test_recovery_0_strikes_io_reports_the_final_strike_uri(monkeypatch):
    run = run_lane(monkeypatch, script_for(0), io_concurrency=2)

    assert run['results'][0].result_uri == 'OK'


def test_recovery_0_strikes_io_keeps_the_success_outcome(monkeypatch):
    run = run_lane(monkeypatch, script_for(0), io_concurrency=2)

    assert run['results'][0].outcome == 'success'


def test_recovery_0_strikes_io_persists_1_times(monkeypatch):
    run = run_lane(monkeypatch, script_for(0), io_concurrency=2)

    assert run['persist'].calls.count('a') == 1


def test_recovery_0_strikes_io_sleeps_the_documented_schedule(monkeypatch):
    run = run_lane(monkeypatch, script_for(0), io_concurrency=2)

    assert run['sleeps'].delays == []


def test_recovery_0_strikes_io_books_no_worker_fault(monkeypatch):
    run = run_lane(monkeypatch, script_for(0), io_concurrency=2)

    assert run['meta']['failures'] == [] and run['worker'].counts['failed'] == 0


def test_recovery_0_strikes_io_runs_the_gpu_chain_once(monkeypatch):
    run = run_lane(monkeypatch, script_for(0), io_concurrency=2)

    assert run['meta']['decoded'] == ['a'] and run['meta']['diarized'] == [32000]


def test_recovery_0_strikes_io_hands_the_same_payload_to_every_strike(monkeypatch):
    run = run_lane(monkeypatch, script_for(0), io_concurrency=2)

    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_recovery_0_strikes_io_opens_a_persist_span_per_strike(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, script_for(0), timings=timings, io_concurrency=2)

    assert timings.spans.count('persist') == 1


def test_recovery_1_strikes_io_returns_the_completed_work_result(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), io_concurrency=2)

    assert len(run['results']) == 1 and isinstance(run['results'][0], WorkResult)


def test_recovery_1_strikes_io_reports_the_final_strike_uri(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), io_concurrency=2)

    assert run['results'][0].result_uri == 'OK'


def test_recovery_1_strikes_io_keeps_the_success_outcome(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), io_concurrency=2)

    assert run['results'][0].outcome == 'success'


def test_recovery_1_strikes_io_persists_2_times(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), io_concurrency=2)

    assert run['persist'].calls.count('a') == 2


def test_recovery_1_strikes_io_sleeps_the_documented_schedule(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), io_concurrency=2)

    assert run['sleeps'].delays == [0.25]


def test_recovery_1_strikes_io_books_no_worker_fault(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), io_concurrency=2)

    assert run['meta']['failures'] == [] and run['worker'].counts['failed'] == 0


def test_recovery_1_strikes_io_runs_the_gpu_chain_once(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), io_concurrency=2)

    assert run['meta']['decoded'] == ['a'] and run['meta']['diarized'] == [32000]


def test_recovery_1_strikes_io_hands_the_same_payload_to_every_strike(monkeypatch):
    run = run_lane(monkeypatch, script_for(1), io_concurrency=2)

    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_recovery_1_strikes_io_opens_a_persist_span_per_strike(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, script_for(1), timings=timings, io_concurrency=2)

    assert timings.spans.count('persist') == 2


def test_recovery_2_strikes_io_returns_the_completed_work_result(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), io_concurrency=2)

    assert len(run['results']) == 1 and isinstance(run['results'][0], WorkResult)


def test_recovery_2_strikes_io_reports_the_final_strike_uri(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), io_concurrency=2)

    assert run['results'][0].result_uri == 'OK'


def test_recovery_2_strikes_io_keeps_the_success_outcome(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), io_concurrency=2)

    assert run['results'][0].outcome == 'success'


def test_recovery_2_strikes_io_persists_3_times(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), io_concurrency=2)

    assert run['persist'].calls.count('a') == 3


def test_recovery_2_strikes_io_sleeps_the_documented_schedule(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), io_concurrency=2)

    assert run['sleeps'].delays == [0.25, 0.5]


def test_recovery_2_strikes_io_books_no_worker_fault(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), io_concurrency=2)

    assert run['meta']['failures'] == [] and run['worker'].counts['failed'] == 0


def test_recovery_2_strikes_io_runs_the_gpu_chain_once(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), io_concurrency=2)

    assert run['meta']['decoded'] == ['a'] and run['meta']['diarized'] == [32000]


def test_recovery_2_strikes_io_hands_the_same_payload_to_every_strike(monkeypatch):
    run = run_lane(monkeypatch, script_for(2), io_concurrency=2)

    payloads = run['persist'].payloads
    assert all(payload is payloads[0] for payload in payloads)


def test_recovery_2_strikes_io_opens_a_persist_span_per_strike(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, script_for(2), timings=timings, io_concurrency=2)

    assert timings.spans.count('persist') == 3


def test_exhaustion_at_the_cap_serial_returns_no_result_entry(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())

    assert run['results'] == []


def test_exhaustion_at_the_cap_serial_books_the_legacy_worker_fault(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())

    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_exhaustion_at_the_cap_serial_increments_the_failed_count_once(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())

    assert run['worker'].counts['failed'] == 1 and run['worker'].counts['items'] == 1


def test_exhaustion_at_the_cap_serial_stops_at_the_cap_calls(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())

    assert len(run['persist'].calls) == 3


def test_exhaustion_at_the_cap_serial_sleeps_only_between_strikes(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())

    assert run['sleeps'].delays == [0.25, 0.5]


def test_exhaustion_at_the_cap_serial_keeps_the_gpu_chain_at_one_pass(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())

    assert run['meta']['decoded'] == ['a']


def test_exhaustion_at_the_cap_serial_opens_a_persist_span_per_strike(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, exhaust_script(), timings=timings)

    assert timings.spans.count('persist') == 3


def test_exhaustion_at_the_cap_io_returns_no_result_entry(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), io_concurrency=2)

    assert run['results'] == []


def test_exhaustion_at_the_cap_io_books_the_legacy_worker_fault(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), io_concurrency=2)

    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_exhaustion_at_the_cap_io_increments_the_failed_count_once(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), io_concurrency=2)

    assert run['worker'].counts['failed'] == 1 and run['worker'].counts['items'] == 1


def test_exhaustion_at_the_cap_io_stops_at_the_cap_calls(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), io_concurrency=2)

    assert len(run['persist'].calls) == 3


def test_exhaustion_at_the_cap_io_sleeps_only_between_strikes(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), io_concurrency=2)

    assert run['sleeps'].delays == [0.25, 0.5]


def test_exhaustion_at_the_cap_io_keeps_the_gpu_chain_at_one_pass(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script(), io_concurrency=2)

    assert run['meta']['decoded'] == ['a']


def test_exhaustion_at_the_cap_io_opens_a_persist_span_per_strike(monkeypatch):
    timings = RecordingTimings()
    run = run_lane(monkeypatch, exhaust_script(), timings=timings, io_concurrency=2)

    assert timings.spans.count('persist') == 3


def test_lane_recovery_never_raises_out_of_process_batch(monkeypatch):
    run = run_lane(monkeypatch, script_for(2))

    assert isinstance(run['results'], list) and run['results']


def test_lane_exhaustion_never_raises_out_of_process_batch(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())

    assert isinstance(run['results'], list)


def test_on_failure_carries_the_fault_type_name_only_on_exhaustion(monkeypatch):
    run = run_lane(monkeypatch, exhaust_script())

    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_on_failure_stays_silent_when_the_lane_recovers(monkeypatch):
    run = run_lane(monkeypatch, script_for(2))

    assert run['meta']['failures'] == []


def test_nongoogle_fault_fails_on_the_first_call(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([ValueError('custody')]))
    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_gate_off_faults_on_the_first_call(monkeypatch):
    run = run_lane(monkeypatch, script_for(3), gate='false')

    assert run['results'] == [] and len(run['persist'].calls) == 1
    assert run['sleeps'].delays == []


def test_unset_gate_recovers(monkeypatch):
    pin_full_gpu_stages(monkeypatch)
    monkeypatch.delenv(GATE, raising=False)
    sleeps = SleepRecorder()
    monkeypatch.setattr(bp.time, 'sleep', sleeps)
    persist = ScriptedPersist(script_for(1))
    worker, meta = build_worker(persist)
    results = worker.process_batch([item()])
    assert results and results[0].result_uri == 'OK' and sleeps.delays == [0.25]


def test_mixed_google_fault_family_recovers(monkeypatch):
    script = [ServiceUnavailable('a'), InternalServerError('b'), 'OK']
    run = run_lane(monkeypatch, script)

    assert run['results'][0].result_uri == 'OK'
    assert run['sleeps'].delays == [0.25, 0.5]


def test_two_units_recover_independently(monkeypatch):
    routes = PerSegmentPersist({'a': ScriptedPersist(script_for(1)), 'b': ScriptedPersist([])})
    run = run_two_units(monkeypatch, routes)
    assert {r.segment_id for r in run['results']} == {'a', 'b'}
    assert run['persist'].calls == ['a', 'a', 'b']


def test_one_exhausted_unit_does_not_poison_its_sibling(monkeypatch):
    routes = PerSegmentPersist({'a': exhaust_script(), 'b': ScriptedPersist([])})
    run = run_two_units(monkeypatch, routes)
    assert [r.segment_id for r in run['results']] == ['b']
    assert run['meta']['failures'] == [('a', 'InvalidArgument')]


def test_sibling_counts_stay_per_unit(monkeypatch):
    routes = PerSegmentPersist({'a': exhaust_script(), 'b': ScriptedPersist([])})
    run = run_two_units(monkeypatch, routes)
    assert run['worker'].counts['items'] == 2 and run['worker'].counts['failed'] == 1


def test_mid_lane_gate_flip_does_not_abort_an_earned_strike(monkeypatch):
    pin_full_gpu_stages(monkeypatch)
    monkeypatch.setenv(GATE, 'true')
    sleeps = SleepRecorder()
    monkeypatch.setattr(bp.time, 'sleep', sleeps)
    inner = ScriptedPersist(script_for(1))

    def flip(work, payload):
        step = inner(work, payload)
        monkeypatch.setenv(GATE, 'false')
        return step

    worker, meta = build_worker(flip)
    results = worker.process_batch([item()])
    assert results and results[0].result_uri == 'OK' and sleeps.delays == [0.25]


def test_lane_composes_with_language_receipt(monkeypatch):
    pin_full_gpu_stages(monkeypatch)
    monkeypatch.setenv(GATE, 'true')
    sleeps = SleepRecorder()
    monkeypatch.setattr(bp.time, 'sleep', sleeps)
    persist = ScriptedPersist(script_for(1))
    worker, meta = build_worker(persist)
    results = worker.process_batch([replace(item(), language_receipt_enabled=True)])
    assert results[0].language_receipt['route'] == 'parakeet'


def test_lane_composes_with_shadow_units(monkeypatch):
    pin_full_gpu_stages(monkeypatch)
    monkeypatch.setenv(GATE, 'true')
    sleeps = SleepRecorder()
    monkeypatch.setattr(bp.time, 'sleep', sleeps)
    persist = ScriptedPersist(script_for(1))
    worker, meta = build_worker(persist)
    results = worker.process_batch([replace(item(), shadow=True)])
    assert results and results[0].result_uri == 'OK'


def test_recovered_result_is_a_work_result_not_a_fault_work(monkeypatch):
    run = run_lane(monkeypatch, script_for(2))

    assert isinstance(run['results'][0], WorkResult)
    assert not isinstance(run['results'][0], FailedWork)
