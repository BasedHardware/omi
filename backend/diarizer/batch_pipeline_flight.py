"""Flight-level pyannote batching for the dedicated batch GPU chain.

The serial chain runs the community-1 segmentation model twice per item (once
inside VAD, once inside diarization) and the WeSpeaker ResNet trunk once per
(chunk, local speaker) pair, although the waveform is identical for the three
local speakers of a chunk. This adapter removes that duplicated model work and
packs the remaining forwards across the items of one locked flight:

* one raw segmentation pass per item, packed across items, shared by VAD
  (CPU aggregation/binarization) and diarization (``get_segmentations``);
* one ResNet trunk forward per chunk, pooled per local speaker with the same
  masks and statistics pooling, packed across items.

Each forward keeps the deployment's pinned model batch size, so a single
forward is never larger than in the serial path and peak VRAM does not grow.
``budget_seconds`` bounds the audio packed into one group (host-side features
held between stages). A unit longer than the budget, an unsupported model
layout, any non-fatal failure, or a CUDA out-of-memory error inside the packed
path falls back to the unchanged serial pyannote calls. Other fatal CUDA
errors propagate to the chain's quarantine.

Clustering, reconstruction and labelling remain pyannote's own ``apply``; only
its two model-feature hooks read the precomputed values.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import logging
import math
import warnings
from typing import Any, Callable, Sequence

import numpy as np

try:
    import torch as _torch  # type: ignore[reportMissingImports]  # GPU runtime dependency
    import torch.nn.functional as _functional  # type: ignore[reportMissingImports]
    import pyannote.core as _core  # type: ignore[reportMissingImports]
    from pyannote.audio.core import task as _task  # type: ignore[reportMissingImports]
    from pyannote.audio.utils import reproducibility as _reproducibility  # type: ignore[reportMissingImports]
except ImportError:
    _torch = _functional = _core = _task = _reproducibility = None

# Optional GPU-image modules; the model-free backend venv imports this file too.
torch: Any = _torch
functional: Any = _functional
Segment: Any = getattr(_core, 'Segment', None)
SlidingWindow: Any = getattr(_core, 'SlidingWindow', None)
SlidingWindowFeature: Any = getattr(_core, 'SlidingWindowFeature', None)
Resolution: Any = getattr(_task, 'Resolution', None)
fix_reproducibility: Any = getattr(_reproducibility, 'fix_reproducibility', None)

from diarizer.batch_pipeline import SAMPLE_RATE, crop_model_vad_spans, is_fatal_cuda_error
from utils.stt.diarization_turns import exclusive_from_activity, overlap_regions
from utils.batch_pipeline import leaf_timings

logger = logging.getLogger(__name__)

SEGMENTATION_KEY = 'omi_flight_segmentation'
EMBEDDINGS_KEY = 'omi_flight_embeddings'


def is_out_of_memory(exc) -> bool:
    """Allocator exhaustion only; never device asserts or illegal accesses."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if type(exc).__name__ == 'OutOfMemoryError' or isinstance(exc, MemoryError):
            return True
        if 'out of memory' in str(exc).lower():
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def flight_groups(seconds: Sequence[float], budget_seconds: float) -> tuple[list[list[int]], list[int]]:
    """Pack indices in order into groups of at most ``budget_seconds`` audio.

    Units longer than the budget are returned separately for the serial path.
    """
    groups, current, total, serial = [], [], 0.0, []
    for index, value in enumerate(seconds):
        if value > budget_seconds:
            serial.append(index)
            continue
        if current and total + value > budget_seconds:
            groups.append(current)
            current, total = [], 0.0
        current.append(index)
        total += value
    if current:
        groups.append(current)
    return groups, serial


def packed_batches(counts: Sequence[int], batch_size: int):
    """Yield [(owner, local_index), ...] batches over concatenated per-owner rows."""
    batch = []
    for owner, count in enumerate(counts):
        for local in range(count):
            batch.append((owner, local))
            if len(batch) == batch_size:
                yield batch
                batch = []
    if batch:
        yield batch


@dataclass
class FlightFeatures:
    """Raw (non-aggregated, multilabel) segmentation of one decoded unit."""

    segmentation: Any
    num_samples: int
    has_last_chunk: bool


def diarization_payload(output) -> dict:
    activity = [
        {'start': float(t.start), 'end': float(t.end), 'speaker': str(s)} for t, s in output.speaker_diarization
    ]
    exclusive = getattr(output, 'exclusive_speaker_diarization', None)
    turns = (
        [{'start': float(t.start), 'end': float(t.end), 'speaker': str(s)} for t, s in exclusive]
        if exclusive is not None
        else exclusive_from_activity(activity)
    )
    return {'turns': turns, 'overlaps': overlap_regions(activity), 'backend': 'pyannote'}


def unsupported_reason(diarizer, vad) -> str | None:
    """Return why the packed path cannot reproduce the serial calls, if it cannot."""
    if torch is None or SlidingWindowFeature is None or fix_reproducibility is None:
        return 'runtime_unavailable'
    try:
        seg, vseg = diarizer._segmentation, vad._segmentation
        spec = seg.model.specifications
        checks = {
            'shared_model': seg.model is vseg.model,
            'same_chunking': seg.duration == vseg.duration and seg.step == vseg.step,
            'same_forward_batch': seg.batch_size == vseg.batch_size,
            'raw_diarization_segmentation': seg.skip_aggregation is True,
            'aggregated_vad': vseg.skip_aggregation is False and vseg.pre_aggregation_hook is not None,
            'multilabel_conversion': seg.skip_conversion is False and vseg.skip_conversion is False,
            'single_frame_task': not isinstance(spec, tuple) and spec.resolution == Resolution.FRAME,
            'powerset': bool(getattr(spec, 'powerset', False)),
            'not_training': not diarizer.training and not vad.training,
            'vad_binarize': callable(getattr(vad, '_binarize', None)),
            'pipeline_hooks': all(
                callable(getattr(diarizer, name, None)) for name in ('get_segmentations', 'get_embeddings')
            ),
        }
    except Exception:
        return 'model_layout'
    failed = sorted(name for name, ok in checks.items() if not ok)
    return failed[0] if failed else None


def _shared_trunk_supported(diarizer) -> bool:
    try:
        embedding = diarizer._embedding
        model = embedding.model_
        return (
            type(embedding).__name__ == 'PyannoteAudioPretrainedSpeakerEmbedding'
            and callable(getattr(model, 'forward_frames', None))
            and callable(getattr(model, 'forward_embedding', None))
            and not getattr(model, 'fbank_only', False)
            and int(diarizer.embedding_batch_size) >= 1
        )
    except Exception:
        return False


class FlightPyannote:
    """Packed VAD/diarization features for one process-owned pyannote pair."""

    def __init__(self, diarizer, vad, *, budget_seconds: float, convert: Callable = diarization_payload):
        self.diarizer, self.vad = diarizer, vad
        self.segmentation, self.vad_segmentation = diarizer._segmentation, vad._segmentation
        self.budget_seconds = float(budget_seconds)
        self.convert = convert
        self.shared_trunk = _shared_trunk_supported(diarizer)
        self.counts = {'packed_items': 0, 'serial_items': 0, 'oom_fallbacks': 0, 'error_fallbacks': 0}
        self._install_feature_hooks()

    @classmethod
    def create(cls, diarizer, vad, *, budget_seconds: float):
        reason = unsupported_reason(diarizer, vad)
        if reason is not None:
            logger.warning('event=batch_flight_models outcome=disabled reason=%s', reason)
            return None
        flight = cls(diarizer, vad, budget_seconds=budget_seconds)
        logger.info(
            'event=batch_flight_models outcome=enabled budget_seconds=%.0f shared_trunk=%s',
            flight.budget_seconds,
            flight.shared_trunk,
        )
        return flight

    def _install_feature_hooks(self):
        original_segmentations = self.diarizer.get_segmentations
        original_embeddings = self.diarizer.get_embeddings

        def get_segmentations(file, hook=None):
            cached = file.get(SEGMENTATION_KEY) if isinstance(file, Mapping) else None
            return cached if cached is not None else original_segmentations(file, hook=hook)

        def get_embeddings(file, binary_segmentations, exclude_overlap=False, hook=None):
            cached = file.get(EMBEDDINGS_KEY) if isinstance(file, Mapping) else None
            if cached is None:
                # Uncached calls (e.g. speech-only compacted waveforms) still
                # get the shared trunk for this one file.
                return self._shared_or_serial(
                    original_embeddings, file, binary_segmentations, exclude_overlap=exclude_overlap, hook=hook
                )
            chunks, _, speakers = binary_segmentations.data.shape
            if cached.shape[:2] != (chunks, speakers):
                # Never cluster mismatched rows: recompute serially instead.
                logger.warning('event=batch_flight_fallback stage=embedding reason=shape_mismatch')
                return original_embeddings(file, binary_segmentations, exclude_overlap=exclude_overlap, hook=hook)
            return cached

        # Bypass pyannote's attribute bookkeeping: these are plain callables
        # that preserve the original behavior whenever no feature is supplied.
        object.__setattr__(self.diarizer, 'get_segmentations', get_segmentations)
        object.__setattr__(self.diarizer, 'get_embeddings', get_embeddings)

    def _shared_or_serial(self, original, file, binarized, *, exclude_overlap, hook):
        if self.shared_trunk and isinstance(file, Mapping):
            try:
                return self.embed_group([file], [binarized], exclude_overlap=exclude_overlap)[0]
            except Exception as exc:
                if not self._recoverable(exc, 'embedding'):
                    raise
        return original(file, binarized, exclude_overlap=exclude_overlap, hook=hook)

    # ---- segmentation -------------------------------------------------

    def _waveform(self, samples):
        file = {'waveform': torch.from_numpy(np.asarray(samples, dtype=np.float32)).unsqueeze(0)}
        file['sample_rate'] = SAMPLE_RATE
        return self.segmentation.model.audio(file)

    def _chunks(self, samples):
        """Exactly Inference.slide's complete chunks plus zero-padded last chunk."""
        inference = self.segmentation
        waveform, sample_rate = self._waveform(samples)
        if sample_rate != SAMPLE_RATE:
            raise ValueError('segmentation resampled the canonical waveform')
        window_size = inference.model.audio.get_num_samples(inference.duration)
        step_size = round(inference.step * sample_rate)
        _, num_samples = waveform.shape
        chunks = []
        if num_samples >= window_size:
            unfolded = waveform.unfold(1, window_size, step_size).permute(1, 0, 2)
            chunks = list(unfolded)
        has_last_chunk = (num_samples < window_size) or (num_samples - window_size) % step_size > 0
        if has_last_chunk:
            last = waveform[:, len(chunks) * step_size :]
            chunks.append(functional.pad(last, (0, window_size - last.shape[1])))
        return chunks, num_samples, has_last_chunk

    def _segment_group(self, samples_list):
        inference = self.segmentation
        fix_reproducibility(inference.device)
        prepared = [self._chunks(samples) for samples in samples_list]
        outputs = [[] for _ in prepared]
        for batch in packed_batches([len(chunks) for chunks, _, _ in prepared], inference.batch_size):
            stacked = torch.stack([prepared[owner][0][local] for owner, local in batch])
            scores = inference.infer(stacked)
            for row, (owner, _) in enumerate(batch):
                outputs[owner].append(scores[row])
        frames = SlidingWindow(start=0.0, duration=inference.duration, step=inference.step)
        return [
            FlightFeatures(SlidingWindowFeature(np.stack(rows), frames), num_samples, has_last_chunk)
            for rows, (_, num_samples, has_last_chunk) in zip(outputs, prepared)
        ]

    def segment(self, samples_list: Sequence) -> list:
        """Raw segmentation per unit, or None where the serial VAD must run."""
        result: list = [None] * len(samples_list)
        groups, serial = flight_groups([len(s) / SAMPLE_RATE for s in samples_list], self.budget_seconds)
        self.counts['serial_items'] += len(serial)
        for group in groups:
            try:
                features = self._segment_group([samples_list[i] for i in group])
            except Exception as exc:
                if not self._recoverable(exc, 'segmentation'):
                    raise
                continue
            for index, feature in zip(group, features):
                result[index] = feature
            self.counts['packed_items'] += len(group)
        return result

    def vad_spans(self, samples, features: FlightFeatures):
        """VoiceActivityDetection.apply's aggregation/binarization on shared scores."""
        inference = self.vad_segmentation
        scores = inference.pre_aggregation_hook(features.segmentation.data)
        aggregated = inference.aggregate(
            SlidingWindowFeature(scores, SlidingWindow(start=0.0, duration=inference.duration, step=inference.step)),
            inference.model.receptive_field,
            warm_up=inference.warm_up,
            hamming=True,
            missing=0.0,
        )
        if features.has_last_chunk:
            aggregated.data = aggregated.crop(Segment(0.0, features.num_samples / SAMPLE_RATE), mode='loose')
        speech = self.vad._binarize(aggregated)
        return crop_model_vad_spans(
            [(float(t.start), float(t.end)) for t in speech.get_timeline().support()], len(samples) / SAMPLE_RATE
        )

    # ---- embeddings ---------------------------------------------------

    def _embedding_rows(self, file, binarized, exclude_overlap):
        """SpeakerDiarization.get_embeddings' crops and masks, one row per chunk.

        Lazy like the serial generator: only one model batch of 10s crops is
        materialized at a time, never the whole group.
        """
        embedding = self.diarizer._embedding
        duration = binarized.sliding_window.duration
        _, num_frames, _ = binarized.data.shape
        if exclude_overlap:
            min_num_samples = embedding.min_num_samples
            num_samples = duration * embedding.sample_rate
            min_num_frames = math.ceil(num_frames * min_num_samples / num_samples)
            clean_frames = 1.0 * (np.sum(binarized.data, axis=2, keepdims=True) < 2)
            clean = SlidingWindowFeature(binarized.data * clean_frames, binarized.sliding_window)
        else:
            min_num_frames = -1
            clean = SlidingWindowFeature(binarized.data, binarized.sliding_window)
        for (chunk, masks), (_, clean_masks) in zip(binarized, clean):
            waveform, _ = self.diarizer._audio.crop(file, chunk, mode='pad')
            masks = np.nan_to_num(masks, nan=0.0).astype(np.float32)
            clean_masks = np.nan_to_num(clean_masks, nan=0.0).astype(np.float32)
            used = [
                clean_mask if np.sum(clean_mask) > min_num_frames else mask
                for mask, clean_mask in zip(masks.T, clean_masks.T)
            ]
            yield waveform, np.stack(used)

    def embed_group(self, files, binarized_list, *, exclude_overlap=None):
        return leaf_timings.call(
            'flight_embedding', self._embed_group, files, binarized_list, exclude_overlap=exclude_overlap
        )

    def _embed_group(self, files, binarized_list, *, exclude_overlap=None):
        embedding = self.diarizer._embedding
        model = embedding.model_
        if exclude_overlap is None:
            exclude_overlap = self.diarizer.embedding_exclude_overlap
        rows = [self._embedding_rows(f, b, exclude_overlap) for f, b in zip(files, binarized_list)]
        counts = [b.data.shape[0] for b in binarized_list]
        outputs = [[] for _ in rows]
        for batch in packed_batches(counts, int(self.diarizer.embedding_batch_size)):
            # packed_batches visits owners and their rows strictly in order.
            pulled = [next(rows[owner]) for owner, _ in batch]
            waveforms = torch.vstack([waveform[None] for waveform, _ in pulled])
            masks = torch.from_numpy(np.stack([mask for _, mask in pulled]))
            with torch.inference_mode(), warnings.catch_warnings():
                warnings.simplefilter('ignore')
                # The trunk depends only on the waveform; pool it once per
                # local speaker exactly as the per-pair forward does.
                frames = model.forward_frames(waveforms.to(embedding.device))
                pooled = model.forward_embedding(frames, weights=masks.to(embedding.device))
            pooled = pooled.cpu().numpy()
            for row, (owner, _) in enumerate(batch):
                outputs[owner].append(pooled[row])
        return [np.stack(rows_out) for rows_out in outputs]

    def speaking(self, segmentation) -> bool:
        count = self.diarizer.speaker_count(segmentation, self.segmentation.model.receptive_field, warm_up=(0.0, 0.0))
        return bool(np.nanmax(count.data) > 0)

    def diarize_many(self, entries: Sequence[tuple[Any, FlightFeatures | None]]) -> list:
        """Per-unit diarization dict or exception, never pooling speakers across units."""
        files, segmentations = [], []
        for samples, features in entries:
            file = {'waveform': torch.from_numpy(np.asarray(samples, dtype=np.float32)).unsqueeze(0)}
            file['sample_rate'] = SAMPLE_RATE
            segmentation = features.segmentation if features is not None else None
            if segmentation is not None:
                file[SEGMENTATION_KEY] = segmentation
            files.append(file)
            segmentations.append(segmentation)
        if self.shared_trunk:
            seconds = [len(samples) / SAMPLE_RATE for samples, _ in entries]
            groups, _ = flight_groups(seconds, self.budget_seconds)
            for group in groups:
                eligible = [i for i in group if segmentations[i] is not None and self.speaking(segmentations[i])]
                if not eligible:
                    continue
                try:
                    embeddings = self.embed_group([files[i] for i in eligible], [segmentations[i] for i in eligible])
                except Exception as exc:
                    if not self._recoverable(exc, 'embedding'):
                        raise
                    for i in group:
                        # Fully serial pyannote for the affected units.
                        files[i].pop(SEGMENTATION_KEY, None)
                    continue
                for i, value in zip(eligible, embeddings):
                    files[i][EMBEDDINGS_KEY] = value
        results = []
        for file in files:
            try:
                with torch.inference_mode():
                    results.append(self.convert(self.diarizer(file)))
            except Exception as exc:
                if is_fatal_cuda_error(exc):
                    raise  # The serial pyannote call: unchanged quarantine.
                results.append(exc)
        return results

    def _recoverable(self, exc, stage) -> bool:
        if is_out_of_memory(exc):
            self.counts['oom_fallbacks'] += 1
            if torch is not None and torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.warning('event=batch_flight_fallback stage=%s reason=out_of_memory', stage)
            return True
        if is_fatal_cuda_error(exc):
            return False
        self.counts['error_fallbacks'] += 1
        logger.warning('event=batch_flight_fallback stage=%s reason=error exception_type=%s', stage, type(exc).__name__)
        return True
