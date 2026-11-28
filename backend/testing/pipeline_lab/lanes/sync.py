"""Offline sync lane replay (``/v2/sync-local-files`` -> ``utils/sync/pipeline.py``).

Production path per uploaded file: decode WAL ``.bin`` -> WAV
(``decode_files_to_wav``) -> VAD split into segment files
(``retrieve_vad_segments``) -> per segment: provider select, prerecorded STT
(``prerecorded`` on a signed URL), ``postprocess_words``, transcript admission,
speaker identification, then lifecycle ingest into the closest/target
conversation and ``process_conversation``.

What this driver runs:

| Step | Here | Production code? |
|---|---|---|
| WAL decode | ``utils.sync.files.decode_files_to_wav`` when the corpus clip is an original ``.bin`` upload; otherwise the clip is already PCM | yes / skipped |
| VAD split | real ``utils.sync.legacy_segment_core.retrieve_vad_segments`` (merge/cap, <1 s drop, segment naming) | yes |
| VAD model | ``vad_is_empty`` routed to its own local Silero fallback (``utils.stt.vad._run_file_vad``); prod calls hosted pyannote first | partly |
| STT | cassette: ``exact`` per segment file (what prod sends) or ``span`` from a conversation cassette | simulated |
| Empty-result retry, cap/allowance admission, provider selection | not run | - |
| Word grouping + first-word clock | real ``postprocess_words`` + ``first_word_offset`` | yes |
| Transcript admission (noise filter) | not run | needs flags/state |
| Speaker identification (voiceprints, owner) | not run | needs embeddings + emulator |
| Conversation targeting / merge / lifecycle ingest | not run; segments are placed on the baseline conversation's clock | needs Firestore |
"""

from __future__ import annotations

import contextlib
import shutil
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from unittest import mock

from testing.pipeline_lab.cassette.adapters import pcm16_to_wav, words_to_prerecorded
from testing.pipeline_lab.cassette.format import Word
from testing.pipeline_lab.cassette.player import CassetteMiss, Player, SpanSource
from testing.pipeline_lab.cassette.recorder import Recorder
from testing.pipeline_lab.lanes.output import IngestResult, contract_segment
from testing.pipeline_lab.contracts import parse_time

DRIVER = 'sync_v1'
PRODUCTION_STEPS = ['retrieve_vad_segments', 'merge_and_cap_vad_segments', 'postprocess_words', 'first_word_offset']
SIMULATED_STEPS = ['stt(cassette)', 'vad_model(local silero)', 'conversation_targeting(baseline clock)']

FileVad = Callable[[str], list[dict]]


@dataclass(frozen=True)
class SyncConversation:
    conversation_id: str
    pcm16: bytes
    started_at: str | None
    finished_at: str | None
    language: str | None = None
    baseline_id: str | None = None
    evaluable: dict | None = None
    original_bin: Path | None = None  # original WAL upload, when the corpus kept it


def local_file_vad(path: str) -> list[dict]:
    from utils.stt.vad import _run_file_vad  # pyright: ignore[reportPrivateUsage]

    return _run_file_vad(path)


class _SegmentSTT:
    def __init__(
        self, *, player: Player | None, span: SpanSource | None, recorder: Recorder | None = None, request=None
    ):
        if sum(x is not None for x in (player, span, recorder)) != 1:
            raise ValueError('pass exactly one of player (exact), span or recorder')
        self.player, self.span, self.recorder = player, span, recorder
        self.request = request or {}
        self.digests: list[str] = []

    @property
    def mode(self) -> str:
        return 'span' if self.span else 'exact'

    def words(self, pcm16: bytes, offset: float, duration: float) -> list[Word]:
        if self.recorder is not None:
            cassette = self.recorder.ensure(pcm16, purpose='stt_cassette:sync_segment', **self.request)
            self.digests.append(cassette.key.digest)
            return list(cassette.words)
        if self.player is not None:
            cassette = self.player.get(pcm16)
            self.digests.append(cassette.key.digest)
            return list(cassette.words)
        assert self.span is not None
        return self.span.words(offset, duration)


def private_scratch(root: str | Path | None = None) -> Path:
    """Owner-only directory for the sync lane's WAV work files: ``<root>/tmp/sync`` for a day replay's store root,
    else under the scenario lab root (``scenario/paths.py``)."""
    from testing.pipeline_lab.store import ensure_private_dir

    if root is None:
        from testing.pipeline_lab.scenario.paths import private_lab_root

        root = private_lab_root()
    return ensure_private_dir(Path(root) / 'tmp' / 'sync')


def replay_sync_lane(
    conversation: SyncConversation,
    *,
    player: Player | None = None,
    span: SpanSource | None = None,
    recorder: Recorder | None = None,
    vocabulary: tuple[str, ...] = (),
    file_vad: FileVad | None = None,
    stt: dict | None = None,
    scratch: str | Path | None = None,
) -> IngestResult:
    """Replay one conversation. ``recorder`` instead of ``player`` records the
    exact per-segment cassettes a later ``player`` run needs (cold STT step)."""
    from utils.stt.pre_recorded import postprocess_words
    from utils.sync import legacy_segment_core as sync_pipeline
    from utils.sync.word_timing import first_word_offset

    stt_source = _SegmentSTT(
        player=player,
        span=span,
        recorder=recorder,
        request={'language': conversation.language, 'vocabulary': vocabulary},
    )
    result = IngestResult(
        id=conversation.conversation_id,
        baseline_id=conversation.baseline_id or conversation.conversation_id,
        lane='sync',
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
        stt={**(stt or {}), 'mode': stt_source.mode},
        driver={'name': DRIVER, 'production': list(PRODUCTION_STEPS), 'simulated': list(SIMULATED_STEPS), 'files': []},
    )
    start = parse_time(conversation.started_at)
    if start is None:
        result.outcome, result.error = 'failed', 'no_start_time'
        return result
    epoch = round(start.timestamp(), 3)
    if scratch is None:  # owner audio as WAV files: under the private lab root, never the system temp directory
        scratch = private_scratch()
    work = Path(tempfile.mkdtemp(prefix='plab-sync-', dir=scratch))
    try:
        source_wav = _source_wav(conversation, work, epoch, result)
        segmented: set[str] = set()
        errors: list[str] = []
        vad = file_vad or local_file_vad
        with mock.patch.object(
            sync_pipeline, 'vad_is_empty', lambda path, return_segments=False, cache=False: vad(path)
        ):
            sync_pipeline.retrieve_vad_segments(str(source_wav), segmented, errors)
        if errors:
            result.outcome, result.error = 'failed', errors[0]
            return result
        segments: list[dict] = []
        for path in sorted(segmented, key=lambda p: float(sync_pipeline.get_timestamp_from_path(p))):
            pcm = _read_wav_pcm(path)
            offset = float(sync_pipeline.get_timestamp_from_path(path)) - epoch
            duration = len(pcm) / 32000
            file_report = {'offset': round(offset, 3), 'seconds': round(duration, 3)}
            try:
                words = stt_source.words(pcm, offset, duration)
            except CassetteMiss as miss:
                result.outcome, result.error = 'failed', 'cassette_miss'
                file_report['error'] = str(miss)
                result.driver['files'].append(file_report)
                return result
            raw = words_to_prerecorded(words)
            file_report['words'] = len(raw)
            result.driver['files'].append(file_report)
            if not raw:
                continue  # production: one empty retry, then expected silence
            speech_offset = first_word_offset(raw)
            for segment in postprocess_words(raw, 0):
                segments.append(contract_segment(segment, offset=offset + speech_offset))
        result.segments = sorted(segments, key=lambda s: (s['start'], s['end']))
        result.outcome = 'transcript' if result.segments else 'silence'
        if stt_source.digests:
            result.stt['cassettes'] = stt_source.digests
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _source_wav(conversation: SyncConversation, work: Path, epoch: float, result: IngestResult) -> Path:
    if conversation.original_bin is not None:
        from utils.sync.files import decode_files_to_wav

        staged = work / f'lab_{epoch}{"".join(Path(conversation.original_bin).suffixes) or ".bin"}'
        shutil.copyfile(conversation.original_bin, staged)
        wavs = decode_files_to_wav([str(staged)])
        if wavs:
            result.driver['production'].insert(0, 'decode_files_to_wav')
            return Path(wavs[0])
    path = work / f'lab_{epoch}.wav'
    path.write_bytes(pcm16_to_wav(conversation.pcm16))
    return path


def _read_wav_pcm(path: str) -> bytes:
    with contextlib.closing(wave.open(path, 'rb')) as handle:
        if (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) != (1, 2, 16000):
            from testing.pipeline_lab.lanes.audio import load_pcm16

            return load_pcm16(path)
        return handle.readframes(handle.getnframes())
