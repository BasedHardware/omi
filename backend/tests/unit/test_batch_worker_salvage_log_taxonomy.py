"""Fault-channel taxonomy for salvaged and typed batch worker faults.

Every cell drives one real PipelineWorker flight and pins the exact channel the
worker's finish() report routes it to: designed handoffs (typed deterministic
decode faults, the language barrier, the empty ladder, the terminal validation
disposition) report on their INFO transition channels, while unclassified
faults - including every salvaged orchestration escape, at every cursor stage -
stay booked as ``event=batch_worker_failed`` ERROR records with the closed
``unknown`` reason and a static ``site=`` field. Salvaged flights also report
exactly one ``event=batch_chain outcome=salvaged`` line with the closed
exception type and the salvaged/settled counts.

Failure-Class: FC-worker-flight-escape-voids-settled-and-held-units-into-anonymous-quarantine
"""

import logging

import pytest

from diarizer import batch_pipeline
from diarizer.batch_pipeline import PipelineWorker
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason

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
    def __init__(self, empty=False, bad_clock=False):
        self.empty = empty
        self.bad_clock = bad_clock

    def transcribe_batch(self, samples):
        if self.empty:
            return [[] for _ in samples]
        if self.bad_clock:
            return [[{'word': 'hello', 'timestamp': [5.0, 1.0]}] for _ in samples]
        return [[{'word': 'hello', 'timestamp': [0.1, 0.2]}] for _ in samples]


def item(key, dur=2, shadow=False):
    return WorkItem(key, 'owner-' + key, 100, 'encrypted://' + key, dur, Priority.FRESH, shadow=shadow)


def make_worker(*, language='en', words=None, vad_error=None, decode_error=None, empty_asr=False):
    def decode(work):
        if decode_error is not None:
            raise decode_error
        return Samples(work.duration_seconds, key=work.segment_id)

    def vad(samples):
        if vad_error is not None:
            raise vad_error
        if getattr(samples, 'key', '') == 'ghost':
            return []
        return [(0, len(samples) / 16000)]

    def persist(work, payload):
        return 'encrypted-result://' + work.segment_id

    return PipelineWorker(
        language_of=lambda i: language,
        decode=decode,
        vad=vad,
        words_providers={'parakeet': words or Words(empty=empty_asr)},
        diarizers={'pyannote': lambda samples: {'turns': []}},
        persist=persist,
        on_failure=lambda i, e: None,
    )


def lines_with(caplog, needle):
    return [r.getMessage() for r in caplog.records if needle in r.getMessage()]


@pytest.fixture(autouse=True)
def _deterministic_gpu_stages(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')


def test_typed_decode_fault_reports_on_the_disposition_channel(caplog, monkeypatch):
    worker = make_worker(decode_error=StagedAudioInvalid('cannot decode'))
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    disposition = lines_with(caplog, 'event=batch_validation_disposition outcome=recovery_handoff')
    assert len(disposition) == 1
    assert 'stage=fetch_decode' in disposition[0]
    assert 'reason=staged_audio_invalid' in disposition[0]
    assert not lines_with(caplog, 'event=batch_worker_failed')


def test_language_barrier_reports_on_the_guard_channel(caplog, monkeypatch):
    worker = make_worker(language='zh')
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    guard = lines_with(caplog, 'event=batch_language_guard')
    assert len(guard) == 1
    assert 'stage=vad_windows' in guard[0]
    assert 'reason=unsupported_language' in guard[0]
    assert not lines_with(caplog, 'event=batch_worker_failed')


def test_empty_ladder_reports_on_its_recovery_channel(caplog, monkeypatch):
    worker = make_worker(empty_asr=True)
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    ladder = lines_with(caplog, 'event=batch_empty_ladder outcome=recovery_handoff')
    assert len(ladder) == 1
    assert 'stage=assemble_words' in ladder[0]
    assert 'reason=empty_asr' in ladder[0]


def test_vad_bounds_verdict_stays_a_fault_with_disposition_off(caplog, monkeypatch):
    worker = make_worker(vad_error=BatchValidationError(ValidationReason.VAD_BOUNDS))
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    faults = lines_with(caplog, 'event=batch_worker_failed')
    assert len(faults) == 1
    assert 'stage=vad_windows' in faults[0]
    assert 'reason=vad_bounds' in faults[0]
    assert 'error_class=BatchValidationError' in faults[0]


def test_word_clock_verdict_stays_a_fault_with_disposition_off(caplog, monkeypatch):
    worker = make_worker(words=Words(bad_clock=True))
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    faults = lines_with(caplog, 'event=batch_worker_failed')
    assert len(faults) == 1
    assert 'stage=word_clocks' in faults[0]
    assert 'reason=word_clock' in faults[0]


def test_unclassified_decode_fault_keeps_its_stage(caplog, monkeypatch):
    worker = make_worker(decode_error=RuntimeError('mystery decode failure'))
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    faults = lines_with(caplog, 'event=batch_worker_failed')
    assert len(faults) == 1
    assert 'stage=fetch_decode' in faults[0]
    assert 'reason=unclassified' in faults[0]
    assert 'mystery decode failure' not in faults[0]


def test_salvaged_escape_at_pack_windows_stays_a_fault_naming_vad_windows(caplog, monkeypatch):
    worker = make_worker()
    monkeypatch.setattr(batch_pipeline, 'pack_windows', _boom('packing escape'))
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    faults = lines_with(caplog, 'event=batch_worker_failed')
    assert len(faults) == 1
    assert 'stage=vad_windows' in faults[0]
    assert 'reason=unknown' in faults[0]
    assert 'error_class=RuntimeError' in faults[0]
    assert ' site=' in faults[0]


def test_salvaged_escape_at_pack_windows_reports_one_salvaged_line(caplog, monkeypatch):
    worker = make_worker()
    monkeypatch.setattr(batch_pipeline, 'pack_windows', _boom('packing escape'))
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    salvaged = lines_with(caplog, 'event=batch_chain outcome=salvaged')
    assert len(salvaged) == 1
    assert 'exception_type=RuntimeError' in salvaged[0]
    assert 'salvaged=1' in salvaged[0]
    assert 'settled=0' in salvaged[0]


def test_salvaged_escape_at_pack_windows_never_demotes_to_a_designed_handoff(caplog, monkeypatch):
    worker = make_worker()
    monkeypatch.setattr(batch_pipeline, 'pack_windows', _boom('packing escape'))
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    assert not lines_with(caplog, 'event=batch_language_guard')
    assert not lines_with(caplog, 'event=batch_empty_ladder')
    assert not lines_with(caplog, 'event=batch_validation_disposition')


def test_salvaged_escape_at_remember_stays_a_fault_naming_vad_windows(caplog, monkeypatch):
    worker = make_worker()
    worker.left_context.remember = _boom('remember escape')
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    faults = lines_with(caplog, 'event=batch_worker_failed')
    assert len(faults) == 1
    assert 'stage=vad_windows' in faults[0]
    assert 'reason=unknown' in faults[0]
    assert 'error_class=RuntimeError' in faults[0]
    assert ' site=' in faults[0]


def test_salvaged_escape_at_remember_reports_one_salvaged_line(caplog, monkeypatch):
    worker = make_worker()
    worker.left_context.remember = _boom('remember escape')
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    salvaged = lines_with(caplog, 'event=batch_chain outcome=salvaged')
    assert len(salvaged) == 1
    assert 'exception_type=RuntimeError' in salvaged[0]
    assert 'salvaged=1' in salvaged[0]
    assert 'settled=0' in salvaged[0]


def test_salvaged_escape_at_remember_never_demotes_to_a_designed_handoff(caplog, monkeypatch):
    worker = make_worker()
    worker.left_context.remember = _boom('remember escape')
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    assert not lines_with(caplog, 'event=batch_language_guard')
    assert not lines_with(caplog, 'event=batch_empty_ladder')
    assert not lines_with(caplog, 'event=batch_validation_disposition')


def test_salvaged_escape_at_with_left_context_stays_a_fault_naming_vad_windows(caplog, monkeypatch):
    worker = make_worker()
    worker._with_left_context = _boom('extension escape')
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    faults = lines_with(caplog, 'event=batch_worker_failed')
    assert len(faults) == 1
    assert 'stage=vad_windows' in faults[0]
    assert 'reason=unknown' in faults[0]
    assert 'error_class=RuntimeError' in faults[0]
    assert ' site=' in faults[0]


def test_salvaged_escape_at_with_left_context_reports_one_salvaged_line(caplog, monkeypatch):
    worker = make_worker()
    worker._with_left_context = _boom('extension escape')
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    salvaged = lines_with(caplog, 'event=batch_chain outcome=salvaged')
    assert len(salvaged) == 1
    assert 'exception_type=RuntimeError' in salvaged[0]
    assert 'salvaged=1' in salvaged[0]
    assert 'settled=0' in salvaged[0]


def test_salvaged_escape_at_with_left_context_never_demotes_to_a_designed_handoff(caplog, monkeypatch):
    worker = make_worker()
    worker._with_left_context = _boom('extension escape')
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    assert not lines_with(caplog, 'event=batch_language_guard')
    assert not lines_with(caplog, 'event=batch_empty_ladder')
    assert not lines_with(caplog, 'event=batch_validation_disposition')


def test_salvaged_escape_at_record_route_stays_a_fault_naming_fetch_decode(caplog, monkeypatch):
    worker = make_worker()
    monkeypatch.setattr(batch_pipeline, 'record_route', _boom('route escape'))
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    faults = lines_with(caplog, 'event=batch_worker_failed')
    assert len(faults) == 1
    assert 'stage=fetch_decode' in faults[0]
    assert 'reason=unknown' in faults[0]
    assert 'error_class=RuntimeError' in faults[0]
    assert ' site=' in faults[0]


def test_salvaged_escape_at_record_route_reports_one_salvaged_line(caplog, monkeypatch):
    worker = make_worker()
    monkeypatch.setattr(batch_pipeline, 'record_route', _boom('route escape'))
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    salvaged = lines_with(caplog, 'event=batch_chain outcome=salvaged')
    assert len(salvaged) == 1
    assert 'exception_type=RuntimeError' in salvaged[0]
    assert 'salvaged=1' in salvaged[0]
    assert 'settled=0' in salvaged[0]


def test_salvaged_escape_at_record_route_never_demotes_to_a_designed_handoff(caplog, monkeypatch):
    worker = make_worker()
    monkeypatch.setattr(batch_pipeline, 'record_route', _boom('route escape'))
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    assert not lines_with(caplog, 'event=batch_language_guard')
    assert not lines_with(caplog, 'event=batch_empty_ladder')
    assert not lines_with(caplog, 'event=batch_validation_disposition')


def test_salvaged_escape_at_receipt_stays_a_fault_naming_word_clocks(caplog, monkeypatch):
    worker = make_worker()
    monkeypatch.setattr(batch_pipeline, 'vad_receipt', _boom('receipt escape'))
    worker = make_worker(empty_asr=True)
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    faults = lines_with(caplog, 'event=batch_worker_failed')
    assert len(faults) == 1
    assert 'stage=word_clocks' in faults[0]
    assert 'reason=unknown' in faults[0]
    assert 'error_class=RuntimeError' in faults[0]
    assert ' site=' in faults[0]


def test_salvaged_escape_at_receipt_reports_one_salvaged_line(caplog, monkeypatch):
    worker = make_worker()
    monkeypatch.setattr(batch_pipeline, 'vad_receipt', _boom('receipt escape'))
    worker = make_worker(empty_asr=True)
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    salvaged = lines_with(caplog, 'event=batch_chain outcome=salvaged')
    assert len(salvaged) == 1
    assert 'exception_type=RuntimeError' in salvaged[0]
    assert 'salvaged=1' in salvaged[0]
    assert 'settled=0' in salvaged[0]


def test_salvaged_escape_at_receipt_never_demotes_to_a_designed_handoff(caplog, monkeypatch):
    worker = make_worker()
    monkeypatch.setattr(batch_pipeline, 'vad_receipt', _boom('receipt escape'))
    worker = make_worker(empty_asr=True)
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    assert not lines_with(caplog, 'event=batch_language_guard')
    assert not lines_with(caplog, 'event=batch_empty_ladder')
    assert not lines_with(caplog, 'event=batch_validation_disposition')


def test_salvaged_escape_at_assembly_names_assemble_words_on_the_shadow_channel(caplog, monkeypatch):
    worker = make_worker()
    monkeypatch.setattr(batch_pipeline, 'cap_dispatch_enabled', lambda uid, lane: True)
    worker = make_worker()
    worker._flight_diarize = _boom('assembly escape')
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a', shadow=True)])
    shadow = lines_with(caplog, 'event=batch_shadow_worker_failure')
    assert len(shadow) == 1
    assert 'stage=assemble_words' in shadow[0]
    assert 'reason=unknown' in shadow[0]
    assert not lines_with(caplog, 'event=batch_worker_failed')


def test_salvaged_shadow_escape_at_pack_windows_stays_on_the_shadow_channel(caplog, monkeypatch):
    worker = make_worker()
    monkeypatch.setattr(batch_pipeline, 'pack_windows', _boom('packing escape'))
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a', shadow=True)])
    shadow = lines_with(caplog, 'event=batch_shadow_worker_failure')
    assert len(shadow) == 1
    assert 'stage=vad_windows' in shadow[0]
    assert 'reason=unknown' in shadow[0]
    assert not lines_with(caplog, 'event=batch_worker_failed')


def test_salvaged_shadow_escape_at_remember_stays_on_the_shadow_channel(caplog, monkeypatch):
    worker = make_worker()
    worker.left_context.remember = _boom('remember escape')
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a', shadow=True)])
    shadow = lines_with(caplog, 'event=batch_shadow_worker_failure')
    assert len(shadow) == 1
    assert 'stage=vad_windows' in shadow[0]
    assert 'reason=unknown' in shadow[0]
    assert not lines_with(caplog, 'event=batch_worker_failed')


def test_disposition_switch_does_not_demote_salvaged_escapes(caplog, monkeypatch):
    worker = make_worker()
    monkeypatch.setattr(batch_pipeline, 'pack_windows', _boom('packing escape'))
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    with caplog.at_level(logging.INFO):
        worker.process_batch([item('a')])
    assert len(lines_with(caplog, 'event=batch_worker_failed')) == 1
    assert not lines_with(caplog, 'event=batch_validation_disposition')


def _boom(message):
    def raise_it(*args, **kwargs):
        raise RuntimeError(message)

    return raise_it
