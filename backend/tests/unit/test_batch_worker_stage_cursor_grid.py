"""Stage-cursor grid for worker-flight salvage.

Every cell drives one real PipelineWorker flight with a fixed escape seam and a
flight composition (typed decode failures, VAD-silent units, or both), and pins
each unit's salvaged outcome class and stage-cursor evidence as literals. The
expectations follow docs/batch-flight-escape-salvage.md: the cursor records the
deepest completed typed boundary (fetch_decode, vad_windows, word_clocks,
assemble_words); a unit the escape reached before its entry boundary is
attributed to fetch_decode; settled typed failures and admission holds stand.

Failure-Class: FC-worker-flight-escape-voids-settled-and-held-units-into-anonymous-quarantine
"""

import pytest

from diarizer import batch_pipeline
from diarizer.batch_pipeline import PipelineWorker
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import (
    FailedWork,
    HeldWork,
    Priority,
    ValidationFailureWork,
    WorkItem,
)

FC = 'FC-worker-flight-escape-voids-settled-and-held-units-into-anonymous-quarantine'


class Samples:
    def __init__(self, seconds, key=''):
        self.size = int(seconds * 16000)
        self.key = key

    def __len__(self):
        return self.size

    def __getitem__(self, key):
        return Samples((key.stop - key.start) / 16000)


class Words:
    def __init__(self, empty=False):
        self.empty = empty

    def transcribe_batch(self, samples):
        if self.empty:
            return [[] for _ in samples]
        return [[{'word': 'hello', 'timestamp': [0.1, 0.2]}] for _ in samples]


def item(key, dur=2):
    return WorkItem(key, 'owner-' + key, 100, 'encrypted://' + key, dur, Priority.FRESH)


class Flight:
    """One deterministic worker flight; positions drive decode failures and silence."""

    def __init__(self, keys, *, decode_fail_set=(), silent_set=(), empty_asr=False):
        self.keys = list(keys)
        self.fail_keys = {self.keys[i] for i in decode_fail_set}
        self.silent_keys = {self.keys[i] for i in silent_set}
        self.saved = {}
        self.failures = []
        self.words = Words(empty=empty_asr)

        def decode(work):
            if work.segment_id in self.fail_keys:
                raise StagedAudioInvalid('cannot decode')
            return Samples(work.duration_seconds, key=work.segment_id)

        def vad(samples):
            if getattr(samples, 'key', None) in self.silent_keys:
                return []
            return [(0, len(samples) / 16000)]

        def persist(work, payload):
            self.saved[work.segment_id] = payload
            return 'encrypted-result://' + work.segment_id

        self.worker = PipelineWorker(
            language_of=lambda i: 'en',
            decode=decode,
            vad=vad,
            words_providers={'parakeet': self.words},
            diarizers={'pyannote': lambda samples: {'turns': []}},
            persist=persist,
            on_failure=lambda i, e: self.failures.append((i.segment_id, e)),
        )


def by_id(results):
    return {result.segment_id: result for result in results}


def _boom(message):
    def raise_it(*args, **kwargs):
        raise RuntimeError(message)

    return raise_it


def arm_seam(monkeypatch, flight, seam):
    if seam == 'pack_windows':
        monkeypatch.setattr(batch_pipeline, 'pack_windows', _boom('packing escape'))
    elif seam == 'remember':
        flight.worker.left_context.remember = _boom('remember escape')
    elif seam == 'with_left_context':
        flight.worker._with_left_context = _boom('extension escape')
    elif seam == 'record_route':
        monkeypatch.setattr(batch_pipeline, 'record_route', _boom('route escape'))
    elif seam == 'receipt':
        monkeypatch.setattr(batch_pipeline, 'vad_receipt', _boom('receipt escape'))
    elif seam == 'assembly':
        monkeypatch.setattr(batch_pipeline, 'cap_dispatch_enabled', lambda uid, lane: True)
        flight.worker._flight_diarize = _boom('assembly escape')
    else:
        raise AssertionError('unknown seam ' + seam)


def run_flight(monkeypatch, flight, seam):
    arm_seam(monkeypatch, flight, seam)
    return by_id(flight.worker.process_batch([item(k) for k in flight.keys]))


def assert_failed_work(results, key, stage):
    result = results[key]
    assert isinstance(result, FailedWork), (key, type(result).__name__)
    assert result.worker_failure == {'stage': stage, 'reason': 'unknown'}


def assert_typed_decode_failure(results, key):
    result = results[key]
    assert isinstance(result, ValidationFailureWork), (key, type(result).__name__)
    assert result.stage == 'fetch_decode'
    assert result.reason == 'staged_audio_invalid'


def assert_held_work(results, key):
    result = results[key]
    assert isinstance(result, HeldWork), (key, type(result).__name__)
    assert result.reason == ''


@pytest.fixture(autouse=True)
def _deterministic_gpu_stages(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')


# ------------------------------------------------- seam: pack_windows


def test_cursor_grid_n1_pack_windows_plain(monkeypatch):
    flight = Flight(['u0'])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')


def test_cursor_grid_n1_pack_windows_fail0(monkeypatch):
    flight = Flight(['u0'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')


def test_cursor_grid_n1_pack_windows_silent0(monkeypatch):
    flight = Flight(['u0'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')


def test_cursor_grid_n2_pack_windows_plain(monkeypatch):
    flight = Flight(['u0', 'u1'])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n2_pack_windows_fail0(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n2_pack_windows_fail1(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')


def test_cursor_grid_n2_pack_windows_silent0(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n2_pack_windows_silent1(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n2_pack_windows_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n2_pack_windows_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')


def test_cursor_grid_n2_pack_windows_fail01(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')


def test_cursor_grid_n2_pack_windows_silent01(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n3_pack_windows_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_pack_windows_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_pack_windows_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_pack_windows_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_pack_windows_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_pack_windows_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_pack_windows_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_pack_windows_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_pack_windows_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_pack_windows_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_pack_windows_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_pack_windows_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_pack_windows_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_pack_windows_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_pack_windows_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_pack_windows_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_pack_windows_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_pack_windows_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_pack_windows_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n4_pack_windows_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_pack_windows_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail0_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail1_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail2_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail3_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_pack_windows_fail3_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_pack_windows_fail3_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_pack_windows_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_pack_windows_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_fail13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_pack_windows_fail23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_pack_windows_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_silent03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_silent13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_pack_windows_silent23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n5_pack_windows_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_pack_windows_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail0_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail0_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail1_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail1_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail2_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail2_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail3_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail3_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail3_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail3_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail4_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_pack_windows_fail4_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_pack_windows_fail4_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_pack_windows_fail4_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_pack_windows_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail04(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 4])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_pack_windows_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail14(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 4])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_pack_windows_fail23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_fail24(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2, 4])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_pack_windows_fail34(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3, 4])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_pack_windows_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_silent03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_silent04(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 4])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_silent13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_silent14(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 4])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_silent23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_silent24(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2, 4])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_pack_windows_silent34(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[3, 4])
    results = run_flight(monkeypatch, flight, 'pack_windows')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


# ------------------------------------------------- seam: remember


def test_cursor_grid_n1_remember_plain(monkeypatch):
    flight = Flight(['u0'])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')


def test_cursor_grid_n1_remember_fail0(monkeypatch):
    flight = Flight(['u0'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')


def test_cursor_grid_n1_remember_silent0(monkeypatch):
    flight = Flight(['u0'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')


def test_cursor_grid_n2_remember_plain(monkeypatch):
    flight = Flight(['u0', 'u1'])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n2_remember_fail0(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n2_remember_fail1(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')


def test_cursor_grid_n2_remember_silent0(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n2_remember_silent1(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n2_remember_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n2_remember_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')


def test_cursor_grid_n2_remember_fail01(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')


def test_cursor_grid_n2_remember_silent01(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n3_remember_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_remember_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_remember_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_remember_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_remember_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_remember_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_remember_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_remember_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_remember_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_remember_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_remember_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_remember_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_remember_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_remember_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_remember_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_remember_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_remember_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_remember_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_remember_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n4_remember_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_remember_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail0_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail1_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail2_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail3_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_remember_fail3_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_remember_fail3_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_remember_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_remember_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_fail13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_remember_fail23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_remember_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_silent03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_silent13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_remember_silent23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n5_remember_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_remember_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail0_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail0_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail1_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail1_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail2_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail2_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail3_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail3_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail3_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail3_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail4_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_remember_fail4_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_remember_fail4_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_remember_fail4_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_remember_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail04(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 4])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_remember_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail14(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 4])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_remember_fail23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_fail24(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2, 4])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_remember_fail34(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3, 4])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_remember_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_silent03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_silent04(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 4])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_silent13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_silent14(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 4])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_silent23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_silent24(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2, 4])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_remember_silent34(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[3, 4])
    results = run_flight(monkeypatch, flight, 'remember')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


# ------------------------------------------------- seam: with_left_context


def test_cursor_grid_n1_with_left_context_plain(monkeypatch):
    flight = Flight(['u0'])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')


def test_cursor_grid_n2_with_left_context_plain(monkeypatch):
    flight = Flight(['u0', 'u1'])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n2_with_left_context_fail0(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n2_with_left_context_fail1(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')


def test_cursor_grid_n2_with_left_context_silent0(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n2_with_left_context_silent1(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n3_with_left_context_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_with_left_context_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_with_left_context_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_with_left_context_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_with_left_context_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_with_left_context_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_with_left_context_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_with_left_context_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_with_left_context_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_with_left_context_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_with_left_context_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_with_left_context_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_with_left_context_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_with_left_context_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_with_left_context_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_with_left_context_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_with_left_context_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_with_left_context_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_with_left_context_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n4_with_left_context_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_with_left_context_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail0_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail1_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail2_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail3_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_with_left_context_fail3_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_with_left_context_fail3_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_with_left_context_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_with_left_context_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_fail13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_with_left_context_fail23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_with_left_context_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_silent03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_silent13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_with_left_context_silent23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n5_with_left_context_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_with_left_context_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail0_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail0_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail1_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail1_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail2_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail2_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail3_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail3_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail3_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail3_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail4_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_with_left_context_fail4_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_with_left_context_fail4_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_with_left_context_fail4_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_with_left_context_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail04(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 4])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_with_left_context_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail14(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 4])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_with_left_context_fail23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_fail24(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2, 4])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_with_left_context_fail34(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3, 4])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_with_left_context_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_silent03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_silent04(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 4])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_silent13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_silent14(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 4])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_silent23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_silent24(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2, 4])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_with_left_context_silent34(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[3, 4])
    results = run_flight(monkeypatch, flight, 'with_left_context')
    assert_failed_work(results, 'u0', 'vad_windows')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


# ------------------------------------------------- seam: record_route


def test_cursor_grid_n1_record_route_plain(monkeypatch):
    flight = Flight(['u0'])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')


def test_cursor_grid_n1_record_route_silent0(monkeypatch):
    flight = Flight(['u0'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')


def test_cursor_grid_n2_record_route_plain(monkeypatch):
    flight = Flight(['u0', 'u1'])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')


def test_cursor_grid_n2_record_route_fail0(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')


def test_cursor_grid_n2_record_route_fail1(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')


def test_cursor_grid_n2_record_route_silent0(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')


def test_cursor_grid_n2_record_route_silent1(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')


def test_cursor_grid_n2_record_route_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')


def test_cursor_grid_n2_record_route_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')


def test_cursor_grid_n2_record_route_silent01(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')


def test_cursor_grid_n3_record_route_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n3_record_route_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')


def test_cursor_grid_n4_record_route_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail0_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail1_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail2_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail3_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail3_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail3_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_fail23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_silent03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_silent13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n4_record_route_silent23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')


def test_cursor_grid_n5_record_route_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail0_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail0_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail1_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail1_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail2_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail2_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail3_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail3_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail3_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail3_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail4_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail4_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail4_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail4_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail04(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 4])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail14(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 4])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail24(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2, 4])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_fail34(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3, 4])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_silent03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_silent04(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 4])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_silent13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_silent14(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 4])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_silent23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_silent24(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2, 4])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


def test_cursor_grid_n5_record_route_silent34(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[3, 4])
    results = run_flight(monkeypatch, flight, 'record_route')
    assert_failed_work(results, 'u0', 'fetch_decode')
    assert_failed_work(results, 'u1', 'fetch_decode')
    assert_failed_work(results, 'u2', 'fetch_decode')
    assert_failed_work(results, 'u3', 'fetch_decode')
    assert_failed_work(results, 'u4', 'fetch_decode')


# ------------------------------------------------- seam: receipt


def test_cursor_grid_n1_receipt_plain(monkeypatch):
    flight = Flight(['u0'], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')


def test_cursor_grid_n2_receipt_plain(monkeypatch):
    flight = Flight(['u0', 'u1'], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')


def test_cursor_grid_n2_receipt_fail0(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')


def test_cursor_grid_n2_receipt_fail1(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')


def test_cursor_grid_n2_receipt_silent0(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')


def test_cursor_grid_n2_receipt_silent1(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')


def test_cursor_grid_n3_receipt_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')


def test_cursor_grid_n3_receipt_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')


def test_cursor_grid_n3_receipt_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'word_clocks')


def test_cursor_grid_n3_receipt_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_receipt_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')


def test_cursor_grid_n3_receipt_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'word_clocks')


def test_cursor_grid_n3_receipt_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_receipt_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0], silent_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_failed_work(results, 'u2', 'word_clocks')


def test_cursor_grid_n3_receipt_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0], silent_set=[2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_receipt_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1], silent_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'word_clocks')


def test_cursor_grid_n3_receipt_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1], silent_set=[2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_receipt_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2], silent_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_receipt_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2], silent_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_receipt_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0, 1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'word_clocks')


def test_cursor_grid_n3_receipt_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0, 2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_receipt_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1, 2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_receipt_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0, 1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_failed_work(results, 'u2', 'word_clocks')


def test_cursor_grid_n3_receipt_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0, 2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n3_receipt_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[1, 2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')


def test_cursor_grid_n4_receipt_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_fail3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_receipt_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_receipt_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_fail0_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_receipt_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_fail1_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_receipt_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_fail2_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_receipt_fail3_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_receipt_fail3_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_receipt_fail3_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_receipt_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_fail03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_receipt_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1, 2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_fail13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1, 3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_receipt_fail23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2, 3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_typed_decode_failure(results, 'u2')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_receipt_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_silent03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_receipt_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1, 2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'word_clocks')


def test_cursor_grid_n4_receipt_silent13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1, 3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n4_receipt_silent23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[2, 3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')


def test_cursor_grid_n5_receipt_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_receipt_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[4], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_receipt_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail0_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail0_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[4], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_receipt_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail1_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail1_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[4], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_receipt_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail2_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail2_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[4], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_receipt_fail3_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail3_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail3_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail3_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[4], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_receipt_fail4_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[0], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_receipt_fail4_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_receipt_fail4_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_receipt_fail4_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_receipt_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail04(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 4], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_receipt_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail14(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 4], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_receipt_fail23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2, 3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_typed_decode_failure(results, 'u2')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_fail24(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2, 4], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_receipt_fail34(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3, 4], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_typed_decode_failure(results, 'u3')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_receipt_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 1], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_silent03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_silent04(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 4], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_receipt_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 2], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_silent13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_silent14(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 4], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'vad_windows')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_receipt_silent23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2, 3], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'word_clocks')


def test_cursor_grid_n5_receipt_silent24(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2, 4], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'vad_windows')
    assert_failed_work(results, 'u3', 'word_clocks')
    assert_failed_work(results, 'u4', 'vad_windows')


def test_cursor_grid_n5_receipt_silent34(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[3, 4], empty_asr=True)
    results = run_flight(monkeypatch, flight, 'receipt')
    assert_failed_work(results, 'u0', 'word_clocks')
    assert_failed_work(results, 'u1', 'word_clocks')
    assert_failed_work(results, 'u2', 'word_clocks')
    assert_failed_work(results, 'u3', 'vad_windows')
    assert_failed_work(results, 'u4', 'vad_windows')


# ------------------------------------------------- seam: assembly


def test_cursor_grid_n1_assembly_plain(monkeypatch):
    flight = Flight(['u0'])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')


def test_cursor_grid_n1_assembly_fail0(monkeypatch):
    flight = Flight(['u0'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')


def test_cursor_grid_n1_assembly_silent0(monkeypatch):
    flight = Flight(['u0'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')


def test_cursor_grid_n2_assembly_plain(monkeypatch):
    flight = Flight(['u0', 'u1'])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')


def test_cursor_grid_n2_assembly_fail0(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')


def test_cursor_grid_n2_assembly_fail1(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')


def test_cursor_grid_n2_assembly_silent0(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')


def test_cursor_grid_n2_assembly_silent1(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')


def test_cursor_grid_n2_assembly_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')


def test_cursor_grid_n2_assembly_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_typed_decode_failure(results, 'u1')


def test_cursor_grid_n2_assembly_fail01(monkeypatch):
    flight = Flight(['u0', 'u1'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')


def test_cursor_grid_n2_assembly_silent01(monkeypatch):
    flight = Flight(['u0', 'u1'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'assemble_words')


def test_cursor_grid_n3_assembly_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')


def test_cursor_grid_n3_assembly_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')


def test_cursor_grid_n3_assembly_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_held_work(results, 'u2')


def test_cursor_grid_n3_assembly_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_assembly_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')


def test_cursor_grid_n3_assembly_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_held_work(results, 'u2')


def test_cursor_grid_n3_assembly_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')


def test_cursor_grid_n3_assembly_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_held_work(results, 'u2')


def test_cursor_grid_n3_assembly_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')


def test_cursor_grid_n3_assembly_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_typed_decode_failure(results, 'u1')
    assert_held_work(results, 'u2')


def test_cursor_grid_n3_assembly_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')


def test_cursor_grid_n3_assembly_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_assembly_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[2], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_assembly_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_held_work(results, 'u2')


def test_cursor_grid_n3_assembly_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_assembly_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], decode_fail_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_typed_decode_failure(results, 'u2')


def test_cursor_grid_n3_assembly_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_held_work(results, 'u2')


def test_cursor_grid_n3_assembly_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')


def test_cursor_grid_n3_assembly_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2'], silent_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_failed_work(results, 'u2', 'assemble_words')


def test_cursor_grid_n4_assembly_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_fail3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_assembly_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_failed_work(results, 'u3', 'assemble_words')


def test_cursor_grid_n4_assembly_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_fail0_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_failed_work(results, 'u3', 'assemble_words')


def test_cursor_grid_n4_assembly_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_typed_decode_failure(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_fail1_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_held_work(results, 'u2')
    assert_failed_work(results, 'u3', 'assemble_words')


def test_cursor_grid_n4_assembly_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_typed_decode_failure(results, 'u2')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_fail2_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'assemble_words')


def test_cursor_grid_n4_assembly_fail3_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_assembly_fail3_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_held_work(results, 'u2')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_assembly_fail3_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[3], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_assembly_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_fail03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_assembly_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_fail13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_held_work(results, 'u2')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_assembly_fail23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], decode_fail_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_typed_decode_failure(results, 'u3')


def test_cursor_grid_n4_assembly_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_silent03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_failed_work(results, 'u3', 'assemble_words')


def test_cursor_grid_n4_assembly_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_held_work(results, 'u3')


def test_cursor_grid_n4_assembly_silent13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_held_work(results, 'u2')
    assert_failed_work(results, 'u3', 'assemble_words')


def test_cursor_grid_n4_assembly_silent23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3'], silent_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_failed_work(results, 'u3', 'assemble_words')


def test_cursor_grid_n5_assembly_plain(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_typed_decode_failure(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_assembly_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_failed_work(results, 'u3', 'assemble_words')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_failed_work(results, 'u4', 'assemble_words')


def test_cursor_grid_n5_assembly_fail0_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail0_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail0_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_failed_work(results, 'u3', 'assemble_words')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail0_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_failed_work(results, 'u4', 'assemble_words')


def test_cursor_grid_n5_assembly_fail1_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_typed_decode_failure(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail1_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail1_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_held_work(results, 'u2')
    assert_failed_work(results, 'u3', 'assemble_words')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail1_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_failed_work(results, 'u4', 'assemble_words')


def test_cursor_grid_n5_assembly_fail2_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail2_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_typed_decode_failure(results, 'u2')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail2_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_failed_work(results, 'u3', 'assemble_words')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail2_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_held_work(results, 'u3')
    assert_failed_work(results, 'u4', 'assemble_words')


def test_cursor_grid_n5_assembly_fail3_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_typed_decode_failure(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail3_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_held_work(results, 'u2')
    assert_typed_decode_failure(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail3_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_typed_decode_failure(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail3_silent4(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3], silent_set=[4])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_typed_decode_failure(results, 'u3')
    assert_failed_work(results, 'u4', 'assemble_words')


def test_cursor_grid_n5_assembly_fail4_silent0(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[0])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_assembly_fail4_silent1(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_assembly_fail4_silent2(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_held_work(results, 'u3')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_assembly_fail4_silent3(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[4], silent_set=[3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_failed_work(results, 'u3', 'assemble_words')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_assembly_fail01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_typed_decode_failure(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail04(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[0, 4])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_typed_decode_failure(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_assembly_fail12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_held_work(results, 'u2')
    assert_typed_decode_failure(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail14(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[1, 4])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_typed_decode_failure(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_assembly_fail23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_typed_decode_failure(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_fail24(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[2, 4])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_typed_decode_failure(results, 'u2')
    assert_held_work(results, 'u3')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_assembly_fail34(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], decode_fail_set=[3, 4])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_typed_decode_failure(results, 'u3')
    assert_typed_decode_failure(results, 'u4')


def test_cursor_grid_n5_assembly_silent01(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 1])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_silent02(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_silent03(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_failed_work(results, 'u3', 'assemble_words')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_silent04(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[0, 4])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_failed_work(results, 'u0', 'assemble_words')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_failed_work(results, 'u4', 'assemble_words')


def test_cursor_grid_n5_assembly_silent12(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 2])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_held_work(results, 'u3')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_silent13(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_held_work(results, 'u2')
    assert_failed_work(results, 'u3', 'assemble_words')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_silent14(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[1, 4])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_failed_work(results, 'u1', 'assemble_words')
    assert_held_work(results, 'u2')
    assert_held_work(results, 'u3')
    assert_failed_work(results, 'u4', 'assemble_words')


def test_cursor_grid_n5_assembly_silent23(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2, 3])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_failed_work(results, 'u3', 'assemble_words')
    assert_held_work(results, 'u4')


def test_cursor_grid_n5_assembly_silent24(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[2, 4])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_failed_work(results, 'u2', 'assemble_words')
    assert_held_work(results, 'u3')
    assert_failed_work(results, 'u4', 'assemble_words')


def test_cursor_grid_n5_assembly_silent34(monkeypatch):
    flight = Flight(['u0', 'u1', 'u2', 'u3', 'u4'], silent_set=[3, 4])
    results = run_flight(monkeypatch, flight, 'assembly')
    assert_held_work(results, 'u0')
    assert_held_work(results, 'u1')
    assert_held_work(results, 'u2')
    assert_failed_work(results, 'u3', 'assemble_words')
    assert_failed_work(results, 'u4', 'assemble_words')
