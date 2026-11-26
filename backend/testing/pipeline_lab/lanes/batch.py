"""Record/batch lane replay (``record_lane_owner=batch_live_v1``).

Production path: device records -> upload -> intake cuts capture units ->
scheduler lease -> GPU ``PipelineWorker`` (decode, VAD, padded windows, Parakeet
words, pyannote diarization, word validation) -> encrypted result -> ordered
``Projector`` -> ``projection_segments`` -> conversation transcript.

What this driver runs, per conversation:

| Step | Here | Production code? |
|---|---|---|
| Unit decode | ``diarizer.batch_pipeline_models.decode_pcm16_wav`` | yes |
| Unit cut | one unit per ``ProviderConfig.max_unit_seconds`` | simulated (intake cuts by capture/upload) |
| VAD | ``utils.stt.local_vad`` Silero (injectable) | product helper, but prod uses GPU pyannote VAD |
| Windows, packing, validation, silence/empty handling | real ``PipelineWorker.process_batch`` | yes |
| Words | cassette, served per window by offset (``SpanSource``) | simulated: vendor words, not Parakeet |
| Diarization | turns implied by the cassette's vendor speaker labels; with ``speakers`` (scenario speakers block) the hosted diarizer's community-1 turns for the unit, through the product's ``HttpDiarizer`` to the lab's speaker peer | simulated / product client + peer |
| Result payload | captured from the worker's ``persist`` | yes (shape), no encryption/storage |
| Projection | real ``projection_segments`` (word/turn assignment, grouping); with ``speakers`` the unit is its batch scope (``batch_segment_id``) as the production projector passes it | yes |
| Scheduler, leases, admission, ordered merge, owner-log assignment, privacy fences | not run | see ``testing.lifecycle_sim`` on the local stack |
| Speaker identity (centroids, owner) | not run | needs voiceprints + emulator |
| Boundaries | taken from the baseline row | not replayed (made on device / live lifecycle) |

The worker runs with speech-only diarization compaction pinned off because a
cassette's turns are on the unit clock; the pin is reported in
``driver.decisions``.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

from testing.pipeline_lab.cassette.adapters import pcm16_to_wav
from testing.pipeline_lab.cassette.format import Word, speaker_turns
from testing.pipeline_lab.cassette.player import SpanSource
from testing.pipeline_lab.lanes.audio import RATE, seconds, slice_pcm
from testing.pipeline_lab.lanes.output import IngestResult, contract_segment

LAB_UID = 'local-dev-user'  # DESIGN L4: replays never carry a real uid.
DRIVER = 'record_batch_v1'
PINNED_ENV = {
    # Cassette turns are on the unit clock; compaction would re-time samples.
    'BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED': 'false',
}
PRODUCTION_STEPS = ['decode_pcm16_wav', 'PipelineWorker.process_batch', 'projection_segments']
SIMULATED_STEPS = [
    'unit_cut',
    'dispatch_admission(allow)',
    'vad(local silero, prod: gpu pyannote)',
    'asr(cassette)',
    'diarization(cassette)',
]


@dataclass(frozen=True)
class BatchConversation:
    conversation_id: str
    pcm16: bytes
    started_at: str | None
    finished_at: str | None
    language: str | None = 'en'
    baseline_id: str | None = None
    evaluable: dict | None = None


VadFn = Callable[[np.ndarray], list[tuple[float, float]]]


def silero_vad(samples: np.ndarray) -> list[tuple[float, float]]:
    from utils.stt.local_vad import VAD_WINDOW_SAMPLES, segments_from_16khz_samples

    duration = len(samples) / RATE
    remainder = len(samples) % VAD_WINDOW_SAMPLES
    padded = np.pad(samples, (0, VAD_WINDOW_SAMPLES - remainder)) if remainder else samples
    return [
        (float(s['start']), float(min(duration, s['end'])))
        for s in segments_from_16khz_samples(padded)
        if s['start'] < duration
    ]


class CassetteWords:
    """``words_providers`` member for the real worker, served from a cassette.

    The worker passes bare sample arrays. A window is located in its unit by
    buffer address when it is a view (the normal case), else by searching the
    unit for the window's bytes (padded/concatenated retries).
    """

    def __init__(self):
        self.units: dict[str, tuple[np.ndarray, SpanSource]] = {}
        self.calls = 0
        self.unlocated = 0

    def register(self, segment_id: str, samples: np.ndarray, source: SpanSource) -> None:
        self.units[segment_id] = (samples, source)

    def _locate(self, window: np.ndarray) -> tuple[SpanSource, float] | None:
        for base, source in self.units.values():
            if np.shares_memory(window, base):
                offset = (window.__array_interface__['data'][0] - base.__array_interface__['data'][0]) // base.itemsize
                return source, offset / RATE
        tail = np.ascontiguousarray(window[-min(len(window), RATE // 2) :]).tobytes()
        for base, source in self.units.values():
            found = np.ascontiguousarray(base).tobytes().find(tail)
            while found >= 0 and found % base.itemsize:
                found = np.ascontiguousarray(base).tobytes().find(tail, found + 1)
            if found >= 0:
                end = found // base.itemsize + len(tail) // base.itemsize
                return source, (end - len(window)) / RATE
        return None

    def transcribe_batch(self, samples_list: Sequence[np.ndarray]) -> list[list[dict]]:
        self.calls += 1
        out = []
        for window in samples_list:
            located = self._locate(window)
            if located is None:
                self.unlocated += 1
                out.append([])
                continue
            source, offset = located
            duration = len(window) / RATE
            words = source.words(offset, duration)
            out.append([{'word': w.text, 'timestamp': [max(0.0, w.start), min(duration, w.end)]} for w in words])
        return out


@contextlib.contextmanager
def _pinned_env(values: dict[str, str]):
    previous = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _unit_bounds(total: float, max_unit: float) -> list[tuple[float, float]]:
    bounds, start = [], 0.0
    while start < total - 1e-9:
        end = min(total, start + max_unit)
        bounds.append((start, end))
        start = end
    return bounds


def replay_record_lane(
    conversation: BatchConversation,
    source: SpanSource,
    *,
    vad: VadFn | None = None,
    stt: dict | None = None,
    capture_epoch: float = 0.0,
    speakers=None,
) -> IngestResult:
    """Run one conversation's audio through the record lane's worker and projection.

    ``speakers`` (``speakers/scenario.ScenarioSpeakers``): diarize each unit through the hosted diarizer client
    instead of the cassette's labels, project with the unit as batch scope, keep each projected segment's
    product fields (``segment['product']``) and register each unit (result payload, WAV) for the staged-unit
    stand-in."""
    from config.batch_pipeline_providers import provider_config
    from diarizer.batch_pipeline import PipelineWorker
    from diarizer.batch_pipeline_models import decode_pcm16_wav
    from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem, WorkResult
    from utils.batch_pipeline.projection_segments import projection_segments

    result = IngestResult(
        id=conversation.conversation_id,
        baseline_id=conversation.baseline_id or conversation.conversation_id,
        lane='record',
        started_at=conversation.started_at,
        finished_at=conversation.finished_at,
        outcome='silence',
        language=conversation.language,
        boundaries={
            'source': 'baseline',
            'started_at': conversation.started_at,
            'finished_at': conversation.finished_at,
        },
        evaluable=conversation.evaluable or {'boundaries': False, 'reason': 'unknown'},
        stt={**(stt or {}), 'mode': 'span'},
        driver={
            'name': DRIVER,
            'production': PRODUCTION_STEPS,
            'simulated': SIMULATED_STEPS,
            'decisions': [{'name': k, 'mode': v, 'source': 'ingest.batch'} for k, v in PINNED_ENV.items()]
            + [{'name': 'batch_dispatch_admission', 'mode': 'allow_all', 'source': 'ingest.batch'}],
            'units': [],
        },
    )
    total = seconds(conversation.pcm16)
    if total <= 0:
        result.outcome, result.error = 'failed', 'no_audio'
        return result

    words_provider = CassetteWords()
    payloads: dict[str, dict] = {}
    failures: list[tuple[str, str]] = []
    turns_by_unit: dict[str, list[dict]] = {}
    current: dict[str, str | None] = {'unit': None}

    def persist(item, payload):
        payloads[item.segment_id] = payload
        return f'lab-result://{item.segment_id}'

    unit_pcm: dict[str, bytes] = {}

    def diarize(samples):
        # Called with the full unit (compaction pinned off). Units go through the worker one at a
        # time, so the unit in flight is the one being diarized; equal-length units stay distinct.
        unit = current['unit']
        if speakers is not None and unit:
            return speakers.diarize(unit_pcm[unit])  # the unit's exact PCM: the peer's cassette key
        return {'turns': turns_by_unit.get(unit, []) if unit else []}

    segments: list[dict] = []
    decoded: dict[str, np.ndarray] = {}
    with _pinned_env(PINNED_ENV):
        config = provider_config()  # production env resolution (unit length, windows, providers)
        worker = PipelineWorker(
            decode=lambda item: decoded[item.segment_id],
            vad=vad or silero_vad,
            words_providers={config.words: words_provider},
            diarizers={config.diarizer: diarize},
            persist=persist,
            config=config,
            on_failure=lambda item, exc: failures.append((item.segment_id, type(exc).__name__)),
            io_concurrency=1,
            language_of=lambda item: conversation.language,
        )
        try:
            for index, (u_start, u_end) in enumerate(_unit_bounds(total, config.max_unit_seconds)):
                segment_id = f'lab-{conversation.conversation_id}-{index}'
                pcm = slice_pcm(conversation.pcm16, u_start, u_end)
                item = WorkItem(
                    segment_id,
                    LAB_UID,
                    capture_epoch + u_start,
                    f'lab://{segment_id}',
                    seconds(pcm),
                    Priority.FRESH,
                    conversation_id=conversation.conversation_id,
                )
                unit_source = _OffsetSource(source, u_start)
                unit_pcm[segment_id] = pcm
                if speakers is None:
                    turns_by_unit[segment_id] = speaker_turns(unit_source.words(0.0, seconds(pcm)))
                # Production decode of the staged WAV, once; the worker slices this
                # buffer, so its windows are views the words provider can locate.
                decoded[segment_id] = decode_pcm16_wav(pcm16_to_wav(pcm))
                words_provider.register(segment_id, decoded[segment_id], unit_source)
                # The lab has no funded allowance; spend is capped by the cassette
                # recorder's ledger instead, so dispatch admission always allows.
                current['unit'] = segment_id
                outcomes = worker.process_batch([item], authorize_dispatch=_allow_all)
                current['unit'] = None
                outcome = outcomes[0] if outcomes else None
                unit_report = {
                    'segment_id': segment_id,
                    'start': u_start,
                    'end': u_end,
                    'result': type(outcome).__name__,
                }
                if isinstance(outcome, WorkResult):
                    unit_report['outcome'] = outcome.outcome
                    payload = payloads.get(segment_id) or {}
                    if outcome.outcome == 'success' and payload.get('words'):
                        binding = ProjectionBinding(
                            LAB_UID,
                            f'lab-job-{conversation.conversation_id}',
                            f'lab-content-{conversation.conversation_id}',
                            (segment_id,),
                            record_origin=True,
                            language=conversation.language,
                            data_protection_level='standard',
                            private_cloud_sync_enabled=speakers is not None,
                        )
                        scoped = {'batch_segment_id': segment_id} if speakers is not None else {}
                        for segment in projection_segments(item, binding, payload, **scoped):
                            row = contract_segment(segment, offset=u_start)
                            if speakers is not None:
                                row['product'] = segment.model_dump(mode='json')
                            segments.append(row)
                        if speakers is not None:
                            _register_unit(speakers, item, binding, payload, pcm, conversation.conversation_id)
                else:
                    unit_report['outcome'] = 'not_projected'
                    result.error = f'worker_{type(outcome).__name__}'
                result.driver['units'].append(unit_report)
        finally:
            if worker._io is not None:  # pyright: ignore[reportPrivateUsage]
                worker._io.shutdown(wait=True, cancel_futures=True)  # pyright: ignore[reportPrivateUsage]

    result.driver['worker_counts'] = dict(worker.counts)
    result.driver['unlocated_windows'] = words_provider.unlocated
    if failures:
        result.driver['failures'] = [{'segment_id': s, 'exception': e} for s, e in failures]
    result.segments = sorted(segments, key=lambda s: (s['start'], s['end']))
    if result.segments:
        result.outcome = 'transcript'
    elif result.error or failures:
        result.outcome = 'failed'
        result.error = result.error or 'worker_failure'
    return result


def _register_unit(speakers, item, binding, payload, pcm: bytes, conversation_id: str) -> None:
    from config.policy import ProjectionPolicy
    from testing.pipeline_lab.speakers.scenario import LabUnit

    speakers.register_unit(
        LabUnit(item, binding, ProjectionPolicy(), payload, pcm16_to_wav(pcm), receipt_conversation_id=conversation_id)
    )


def _allow_all(required):
    return {segment_id: None for segment_id in required}


class _OffsetSource:
    """A unit's view of a conversation-level cassette."""

    def __init__(self, source: SpanSource, offset: float):
        self.source, self.offset = source, offset

    def words(self, offset: float, duration: float) -> list[Word]:
        return self.source.words(self.offset + offset, duration)
