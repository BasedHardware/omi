"""A worker-flight orchestration escape must salvage the flight, not void it.

The stage pipeline wraps every per-item fault in the typed ``fail()`` closure, but the
orchestration between those boundaries - left-context bookkeeping, window packing, the
decode generator's route recording, and the observability hooks inside ``fail()`` -
runs unwrapped. On the parent behavior one exception there propagated out of
``process_batch``: the pump received no results for any unit in the flight, settled
outcomes were re-leased for duplicate GPU work, admission holds re-walked the ladder,
and every affected unit climbed evidence-less to the ceiling attempt, whose terminal
record collapsed to the anonymous ``stage=unknown worker_reason=unclassified``
quarantine.

The contract of record is ``docs/batch-flight-escape-salvage.md``. These tests drive the
real ``PipelineWorker`` flight with an escape injected at each unwrapped seam and pin
the salvaged outcomes, stage-cursor evidence, counters, callbacks and fault-channel
records against it.

Failure-Class: FC-worker-flight-escape-voids-settled-and-held-units-into-anonymous-quarantine
"""

import asyncio
import logging

import pytest

from diarizer import batch_pipeline
from diarizer.batch_pipeline import PipelineWorker
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import (
    FailedWork,
    HeldWork,
    Priority,
    ValidationFailureWork,
    WorkItem,
    WorkResult,
)
from utils.batch_pipeline.errors import validate_worker_failure_evidence

FC = 'FC-worker-flight-escape-voids-settled-and-held-units-into-anonymous-quarantine'


@pytest.fixture(autouse=True)
def _deterministic_gpu_stages(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')


class Samples:
    def __init__(self, seconds):
        self.size = int(seconds * 16000)

    def __len__(self):
        return self.size

    def __getitem__(self, key):
        return Samples((key.stop - key.start) / 16000)


class Words:
    def __init__(self, empty=False):
        self.empty = empty
        self.calls = 0

    def transcribe_batch(self, samples):
        self.calls += 1
        if self.empty:
            return [[] for _ in samples]
        return [[{'word': 'hello', 'timestamp': [0.1, 0.2]}] for _ in samples]


def item(key, dur=2):
    return WorkItem(key, 'owner-' + key, 100, 'encrypted://' + key, dur, Priority.FRESH)


class Flight:
    """One deterministic worker flight with injectable escape seams."""

    def __init__(self, keys, *, vad_map=None, decode_fail_at=None, empty_asr=False):
        self.keys = list(keys)
        self.saved = {}
        self.failures = []
        self.words = Words(empty=empty_asr)
        self.vad_map = vad_map or {}

        def decode(work):
            if decode_fail_at is not None and work.segment_id == self.keys[decode_fail_at]:
                raise StagedAudioInvalid('cannot decode')
            return Samples(work.duration_seconds)

        def persist(work, payload):
            self.saved[work.segment_id] = payload
            return 'encrypted-result://' + work.segment_id

        seen = {'vad_calls': 0}

        def vad_by_call(samples):
            seen['vad_calls'] += 1
            spans = self.vad_map.get(seen['vad_calls'])
            return spans if spans is not None else [(0, len(samples) / 16000)]

        self.worker = PipelineWorker(
            language_of=lambda i: 'en',
            decode=decode,
            vad=vad_by_call,
            words_providers={'parakeet': self.words},
            diarizers={'pyannote': lambda samples: {'turns': []}},
            persist=persist,
            on_failure=lambda i, e: self.failures.append((i.segment_id, e)),
        )


def by_id(results):
    return {result.segment_id: result for result in results}


def salvage_stage(result):
    assert isinstance(result, FailedWork), type(result).__name__
    validate_worker_failure_evidence(result.worker_failure)
    return result.worker_failure['stage']


# ------------------------------------------------------- containment per seam


def test_pack_windows_escape_is_contained_not_raised(monkeypatch):
    flight = Flight(['a', 'b', 'c'])

    def boom(*args, **kwargs):
        raise RuntimeError('packing boom')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    assert len(flight.worker.process_batch([item(k) for k in flight.keys])) == 3


def test_left_context_remember_escape_is_contained_not_raised(monkeypatch):
    flight = Flight(['a', 'b'])
    flight.worker.left_context.remember = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('remember boom'))
    assert len(flight.worker.process_batch([item(k) for k in flight.keys])) == 2


def test_left_context_extension_escape_is_contained_not_raised(monkeypatch):
    flight = Flight(['a', 'b'])
    flight.worker._with_left_context = lambda state, clips: (_ for _ in ()).throw(RuntimeError('extension boom'))
    assert len(flight.worker.process_batch([item(k) for k in flight.keys])) == 2


def test_route_recording_escape_is_contained_not_raised(monkeypatch):
    flight = Flight(['a', 'b'])

    def boom(*args, **kwargs):
        raise RuntimeError('route boom')

    monkeypatch.setattr(batch_pipeline, 'record_route', boom)
    assert len(flight.worker.process_batch([item(k) for k in flight.keys])) == 2


def test_empty_asr_evidence_hook_escape_is_contained_not_raised(monkeypatch):
    flight = Flight(['a', 'b'], empty_asr=True)

    def boom(*args, **kwargs):
        raise RuntimeError('evidence boom')

    monkeypatch.setattr(batch_pipeline, 'record_correctness', boom)
    assert len(flight.worker.process_batch([item(k) for k in flight.keys])) == 2


def test_fault_receipt_hook_escape_mid_fail_is_contained_not_raised(monkeypatch):
    # An empty recognition drives the assembly loop's typed fail() for both
    # units; the fault receipt hook inside the handler raises mid-way. The
    # escape fires during the flight, so the salvage contains it.
    flight = Flight(['a', 'b'], empty_asr=True)

    def boom(*args, **kwargs):
        raise RuntimeError('receipt boom')

    monkeypatch.setattr(batch_pipeline, 'vad_receipt', boom)
    assert len(flight.worker.process_batch([item(k) for k in flight.keys])) == 2


# --------------------------------------------------- stage cursor attribution


def test_pack_windows_escape_salvages_every_unit_at_vad_windows(monkeypatch):
    flight = Flight(['a', 'b', 'c'])

    def boom(*args, **kwargs):
        raise RuntimeError('packing boom')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    results = by_id(flight.worker.process_batch([item(k) for k in flight.keys]))
    assert [salvage_stage(results[key]) for key in ('a', 'b', 'c')] == ['vad_windows'] * 3


def test_left_context_escape_salvages_every_unit_at_vad_windows(monkeypatch):
    flight = Flight(['a', 'b', 'c'])
    flight.worker.left_context.remember = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('remember boom'))
    results = by_id(flight.worker.process_batch([item(k) for k in flight.keys]))
    assert [salvage_stage(results[key]) for key in ('a', 'b', 'c')] == ['vad_windows'] * 3


def test_route_recording_escape_attributes_every_unit_at_its_entry_boundary(monkeypatch):
    flight = Flight(['a', 'b', 'c'])

    def boom(*args, **kwargs):
        raise RuntimeError('route boom')

    monkeypatch.setattr(batch_pipeline, 'record_route', boom)
    results = by_id(flight.worker.process_batch([item(k) for k in flight.keys]))
    # Route recording runs inside the decode generator before the unit's VAD
    # turn: unit 'a' completed its decode boundary when the hook raised, and
    # 'b' and 'c' were never entered, so the entry-boundary attribution
    # applies to all three.
    assert [salvage_stage(results[key]) for key in ('a', 'b', 'c')] == ['fetch_decode'] * 3


def test_empty_asr_evidence_hook_escape_attributes_word_clocks(monkeypatch):
    flight = Flight(['a', 'b'], empty_asr=True)

    def boom(*args, **kwargs):
        raise RuntimeError('evidence boom')

    monkeypatch.setattr(batch_pipeline, 'record_correctness', boom)
    results = by_id(flight.worker.process_batch([item(k) for k in flight.keys]))
    assert [salvage_stage(results[key]) for key in ('a', 'b')] == ['word_clocks'] * 2


def test_mid_fail_rescue_attributes_word_clocks_and_assembly_positions(monkeypatch):
    # Unit 'a' is silent and joins the assembly list; unit 'b' then raises the
    # empty-recognition verdict inside the same loop and its typed fail()
    # dies at the receipt hook (mid-way, cursor word_clocks). The escape
    # leaves 'a' prepared-but-unsettled and 'b' mid-handler.
    flight = Flight(['a', 'b'], empty_asr=True, vad_map={1: []})

    def boom(*args, **kwargs):
        raise RuntimeError('receipt boom')

    monkeypatch.setattr(batch_pipeline, 'vad_receipt', boom)
    results = by_id(flight.worker.process_batch([item(k) for k in flight.keys]))
    assert salvage_stage(results['a']) == 'assemble_words'
    assert salvage_stage(results['b']) == 'word_clocks'


# ------------------------------------------------------ typed outcomes stand


def test_typed_decode_failure_is_never_re_emitted_by_salvage(monkeypatch):
    flight = Flight(['a', 'b', 'c'], decode_fail_at=0)
    flight.worker.left_context.remember = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('remember boom'))
    results = by_id(flight.worker.process_batch([item(k) for k in flight.keys]))
    assert isinstance(results['a'], ValidationFailureWork)
    assert results['a'].stage == 'fetch_decode'
    assert results['a'].reason == 'staged_audio_invalid'
    assert [salvage_stage(results[key]) for key in ('b', 'c')] == ['vad_windows'] * 2
    assert len(results) == 3


def test_typed_decode_failure_at_the_tail_leaves_the_head_salvageable(monkeypatch):
    flight = Flight(['a', 'b', 'c'], decode_fail_at=2)

    def boom(*args, **kwargs):
        raise RuntimeError('packing boom')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    results = by_id(flight.worker.process_batch([item(k) for k in flight.keys]))
    assert salvage_stage(results['a']) == 'vad_windows'
    assert isinstance(results['c'], ValidationFailureWork)


def test_silent_unit_salvages_at_its_vad_windows_position(monkeypatch):
    flight = Flight(['a', 'b'], vad_map={2: []})
    flight.worker.left_context.remember = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('remember boom'))
    results = by_id(flight.worker.process_batch([item(k) for k in flight.keys]))
    assert [salvage_stage(results[key]) for key in ('a', 'b')] == ['vad_windows'] * 2
    assert flight.saved == {}


def test_every_unit_appears_exactly_once_in_a_salvaged_flight(monkeypatch):
    flight = Flight(['a', 'b', 'c'], decode_fail_at=1)
    flight.worker.left_context.remember = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('remember boom'))
    results = flight.worker.process_batch([item(k) for k in flight.keys])
    ids = [result.segment_id for result in results]
    assert sorted(ids) == ['a', 'b', 'c']
    assert len(ids) == len(set(ids))


# --------------------------------------------------------- admission holds stand


def test_admission_holds_survive_an_assembly_region_escape(monkeypatch):
    flight = Flight(['a', 'b'])
    # Dispatch admission on, policy authority absent: every unit is held with
    # an empty recorded reason before the assembly region.
    monkeypatch.setattr(batch_pipeline, 'cap_dispatch_enabled', lambda uid, lane: True)
    # Escape seam injection: the packed diarization assembly call site.
    flight.worker._flight_diarize = lambda pending: (_ for _ in ()).throw(RuntimeError('assembly boom'))
    results = by_id(flight.worker.process_batch([item(k) for k in flight.keys]))
    for key in ('a', 'b'):
        assert isinstance(results[key], HeldWork)
        assert results[key].reason == ''
    assert flight.worker.counts['failed'] == 0


def test_salvage_does_not_double_emit_held_units(monkeypatch):
    flight = Flight(['a', 'b'])
    monkeypatch.setattr(batch_pipeline, 'cap_dispatch_enabled', lambda uid, lane: True)
    flight.worker._flight_diarize = lambda pending: (_ for _ in ()).throw(RuntimeError('assembly boom'))
    results = flight.worker.process_batch([item(k) for k in flight.keys])
    ids = [result.segment_id for result in results]
    assert len(ids) == len(set(ids)) == 2
    assert all(isinstance(result, HeldWork) for result in results)


# ------------------------------------------------------------- parity hooks


def test_salvage_increments_the_failed_counter_once_per_unit(monkeypatch):
    flight = Flight(['a', 'b', 'c'])

    def boom(*args, **kwargs):
        raise RuntimeError('packing boom')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    flight.worker.process_batch([item(k) for k in flight.keys])
    assert flight.worker.counts['failed'] == 3


def test_mid_fail_rescue_does_not_double_count_the_failed_counter(monkeypatch):
    flight = Flight(['a', 'b'], empty_asr=True)

    def boom(*args, **kwargs):
        raise RuntimeError('receipt boom')

    monkeypatch.setattr(batch_pipeline, 'vad_receipt', boom)
    flight.worker.process_batch([item(k) for k in flight.keys])
    # Each unit was counted once by its typed handler before the hook raised;
    # the salvage must not add a second count for either.
    assert flight.worker.counts['failed'] == 2


def test_salvage_fires_the_failure_callback_once_per_unit(monkeypatch):
    flight = Flight(['a', 'b'])

    def boom(*args, **kwargs):
        raise RuntimeError('packing boom')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    flight.worker.process_batch([item(k) for k in flight.keys])
    assert flight.failures == [('a', 'RuntimeError'), ('b', 'RuntimeError')]


def test_mid_fail_rescue_still_fires_the_failure_callback(monkeypatch):
    flight = Flight(['a'], empty_asr=True)

    def boom(*args, **kwargs):
        raise RuntimeError('receipt boom')

    monkeypatch.setattr(batch_pipeline, 'vad_receipt', boom)
    flight.worker.process_batch([item(k) for k in flight.keys])
    assert flight.failures == [('a', 'RuntimeError')]


def test_raising_failure_callback_never_breaks_the_salvage(monkeypatch):
    flight = Flight(['a'])

    def boom(*args, **kwargs):
        raise RuntimeError('packing boom')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    flight.worker.on_failure = lambda i, e: (_ for _ in ()).throw(ValueError('callback boom'))
    results = flight.worker.process_batch([item(k) for k in flight.keys])
    assert isinstance(results[0], FailedWork)


def test_salvaged_units_never_reach_persist(monkeypatch):
    flight = Flight(['a', 'b'])
    flight.worker.left_context.remember = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('remember boom'))
    flight.worker.process_batch([item(k) for k in flight.keys])
    assert flight.saved == {}


# ------------------------------------------------------------ fault channel


def test_fault_channel_names_the_cursor_stage_and_unknown_reason(caplog, monkeypatch):
    flight = Flight(['a', 'b'])

    def boom(*args, **kwargs):
        raise RuntimeError('packing boom')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    with caplog.at_level(logging.ERROR):
        flight.worker.process_batch([item(k) for k in flight.keys])
    lines = [r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert len(lines) == 2
    assert all('stage=vad_windows' in line for line in lines)
    assert all('reason=unknown' in line for line in lines)
    assert all('error_class=RuntimeError' in line for line in lines)
    assert all(' site=' in line for line in lines)


def test_salvage_reports_once_on_the_batch_chain_channel(caplog, monkeypatch):
    flight = Flight(['a', 'b', 'c'])
    flight.worker.left_context.remember = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('remember boom'))
    with caplog.at_level(logging.ERROR):
        flight.worker.process_batch([item(k) for k in flight.keys])
    lines = [r.getMessage() for r in caplog.records if 'event=batch_chain' in r.getMessage()]
    assert len(lines) == 1
    assert 'outcome=salvaged' in lines[0]
    assert 'exception_type=RuntimeError' in lines[0]
    assert 'salvaged=3' in lines[0]
    assert 'settled=0' in lines[0]


def test_contained_flight_never_reports_a_retry_void(caplog, monkeypatch):
    flight = Flight(['a'])

    def boom(*args, **kwargs):
        raise RuntimeError('packing boom')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    with caplog.at_level(logging.ERROR):
        flight.worker.process_batch([item(k) for k in flight.keys])
    assert not [r for r in caplog.records if 'outcome=retry' in r.getMessage()]


def test_salvaged_line_counts_a_mid_fail_unit_as_salvaged(caplog, monkeypatch):
    flight = Flight(['a', 'b'], empty_asr=True)

    def boom(*args, **kwargs):
        raise RuntimeError('receipt boom')

    monkeypatch.setattr(batch_pipeline, 'vad_receipt', boom)
    with caplog.at_level(logging.ERROR):
        flight.worker.process_batch([item(k) for k in flight.keys])
    lines = [r.getMessage() for r in caplog.records if 'event=batch_chain outcome=salvaged' in r.getMessage()]
    assert len(lines) == 1
    assert 'salvaged=2' in lines[0]
    assert 'settled=0' in lines[0]


# ------------------------------------------------------- fatal GPU and cancellation


def test_cuda_fatal_escape_restarts_the_chain_instead_of_salvaging(monkeypatch):
    flight = Flight(['a', 'b'])

    def boom(*args, **kwargs):
        raise RuntimeError('CUDA out of memory during packing')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    with pytest.raises(batch_pipeline.FatalGpuError):
        flight.worker.process_batch([item(k) for k in flight.keys])
    assert flight.worker._unavailable is True


def test_cancellation_is_never_salvaged(monkeypatch):
    flight = Flight(['a', 'b'])

    def boom(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    with pytest.raises(asyncio.CancelledError):
        flight.worker.process_batch([item(k) for k in flight.keys])


def test_unavailable_chain_refuses_the_next_flight(monkeypatch):
    flight = Flight(['a'])

    def boom(*args, **kwargs):
        raise RuntimeError('cuda out of memory')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    with pytest.raises(batch_pipeline.FatalGpuError):
        flight.worker.process_batch([item(k) for k in flight.keys])
    with pytest.raises(batch_pipeline.FatalGpuError):
        flight.worker.process_batch([item(k) for k in flight.keys])


# --------------------------------------------------------- evidence contracts


def test_salvage_evidence_passes_the_durable_evidence_validator(monkeypatch):
    flight = Flight(['a', 'b', 'c'])

    def boom(*args, **kwargs):
        raise RuntimeError('packing boom')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    for result in flight.worker.process_batch([item(k) for k in flight.keys]):
        validate_worker_failure_evidence(result.worker_failure)


def test_salvage_evidence_never_carries_the_escape_message(monkeypatch):
    flight = Flight(['a', 'b'])

    def boom(*args, **kwargs):
        raise RuntimeError('SECRET-ESCAPE-DETAILS')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    payload = repr(flight.worker.process_batch([item(k) for k in flight.keys]))
    assert 'SECRET-ESCAPE-DETAILS' not in payload


def test_salvage_does_not_emit_a_persisted_result(monkeypatch):
    flight = Flight(['a'])

    def boom(*args, **kwargs):
        raise RuntimeError('packing boom')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    results = flight.worker.process_batch([item(k) for k in flight.keys])
    assert isinstance(results[0], FailedWork)
    assert not isinstance(results[0], WorkResult)
    assert getattr(results[0], 'result_uri', None) is None


def test_salvage_runs_under_the_gpu_lock_and_returns_settleable_results(monkeypatch):
    flight = Flight(['a', 'b'])

    def boom(*args, **kwargs):
        raise RuntimeError('packing boom')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    pending = flight.worker.process_batch_deferred([item('a'), item('b')])
    settled = pending.settle()
    assert len(settled) == 2
    assert all(isinstance(result, FailedWork) for result in settled)


# ------------------------------------------------------- group containment


def test_second_group_escape_does_not_close_the_first_groups_receipts(monkeypatch):
    words = Words()
    saved = {}

    def persist(work, payload):
        saved[work.segment_id] = payload
        return 'encrypted-result://' + work.segment_id

    worker = PipelineWorker(
        language_of=lambda i: 'en',
        decode=lambda work: Samples(work.duration_seconds),
        vad=lambda s: [(0, len(s) / 16000)],
        words_providers={'parakeet': words},
        diarizers={'pyannote': lambda samples: {'turns': []}},
        persist=persist,
        on_failure=lambda i, e: None,
    )
    first = worker.process_batch_deferred([item('a'), item('b')])

    def boom(*args, **kwargs):
        raise RuntimeError('second group escape')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    second = worker.process_batch_deferred([item('c')])
    settled_first = first.settle()
    settled_second = second.settle()
    assert [r.segment_id for r in settled_first] == ['a', 'b']
    assert all(r.outcome == 'success' for r in settled_first)
    assert all(isinstance(r, FailedWork) for r in settled_second)


def test_salvaged_group_settle_completes_pending_persist_first(monkeypatch):
    flight = Flight(['a', 'b'])
    worker = flight.worker
    worker.left_context.remember = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('remember escape'))
    pending = worker.process_batch_deferred([item('a'), item('b')])
    settled = pending.settle()
    assert len(settled) == 2
    assert flight.saved == {}


def test_items_counter_is_not_doubled_by_salvage(monkeypatch):
    flight = Flight(['a', 'b', 'c'])

    def boom(*args, **kwargs):
        raise RuntimeError('packing escape')

    monkeypatch.setattr(batch_pipeline, 'pack_windows', boom)
    flight.worker.process_batch([item(k) for k in flight.keys])
    assert flight.worker.counts['items'] == 3
