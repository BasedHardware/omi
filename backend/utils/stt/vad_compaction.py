"""Bounded PCM speech compaction with an exact original-sample timeline.

Detection is injected. Failed VAD or ambiguous word clocks retain original audio;
never infer silence from a detector exception. No model/client initialization.
"""

from bisect import bisect_right
from dataclasses import dataclass
import math

from config.final_pass_vad import final_pass_vad_compaction_enabled
from utils.observability.fallback import record_fallback

RATE = 16000


@dataclass(frozen=True)
class SpeechCompaction:
    pcm: bytes
    # (compact_start_sample, original_start_sample, sample_count)
    spans: tuple[tuple[int, int, int], ...]
    original_samples: int

    def map_words(self, words):
        starts = [p[0] for p in self.spans]
        mapped = []
        for word in words:
            left, right = map(float, word['timestamp'])
            if (
                not all(math.isfinite(v) for v in (left, right))
                or not 0 <= left <= right <= len(self.pcm) / 32000 + 0.001
            ):
                raise ValueError('invalid compacted word clock')
            a, b = round(left * RATE), min(round(right * RATE), len(self.pcm) // 2)
            index = max(0, bisect_right(starts, a) - 1)
            compact, original, count = self.spans[index]
            # A word crossing a removed interval has no trustworthy clock. Retry
            # current uncompressed behavior rather than dropping or stretching it.
            if a < compact or a > compact + count or b < a or b > compact + count:
                raise ValueError('word crosses compaction seam')
            mapped.append({**word, 'timestamp': [(original + a - compact) / RATE, (original + b - compact) / RATE]})
        return mapped

    def map_regions(self, regions):
        mapped = []
        for region in regions:
            left, right = float(region['start']), float(region['end'])
            if (
                not all(math.isfinite(v) for v in (left, right))
                or not 0 <= left < right <= len(self.pcm) / 32000 + 0.01
            ):
                raise ValueError('invalid compacted turn clock')
            for compact, original, count in self.spans:
                a, b = max(round(left * RATE), compact), min(round(right * RATE), compact + count)
                if b > a:
                    mapped.append(
                        {**region, 'start': (original + a - compact) / RATE, 'end': (original + b - compact) / RATE}
                    )
        return mapped


def compact_speech(pcm, segments, *, onset_seconds=0.3, tail_seconds=0.5):
    if not pcm or len(pcm) % 2 or len(pcm) > 7200 * 32000:
        raise ValueError('invalid canonical PCM length')
    if not 0 <= onset_seconds <= 1 or not 0 <= tail_seconds <= 1:
        raise ValueError('padding must be bounded to one second')
    total = len(pcm) // 2
    merged = []
    for segment in segments:
        left, right = float(segment['start']), float(segment['end'])
        if not all(math.isfinite(v) for v in (left, right)) or not 0 <= left < right <= total / RATE + 0.001:
            raise ValueError('invalid speech region')
        a, b = max(0, math.floor((left - onset_seconds) * RATE)), min(total, math.ceil((right + tail_seconds) * RATE))
        merged.append((a, b))
    ordered = []
    for a, b in sorted(merged):
        if ordered and a <= ordered[-1][1]:
            ordered[-1] = (ordered[-1][0], max(b, ordered[-1][1]))
        else:
            ordered.append((a, b))
    spans, parts, position = [], [], 0
    for a, b in ordered:
        spans.append((position, a, b - a))
        parts.append(pcm[a * 2 : b * 2])
        position += b - a
    return SpeechCompaction(b''.join(parts), tuple(spans), total)


def _abstain():
    record_fallback(
        component='vad',
        from_mode='stored_speech_compaction',
        to_mode='original_audio',
        reason='other',
        outcome='degraded',
    )


def detect_compaction(pcm, detect):
    try:
        return compact_speech(pcm, detect(pcm))
    except Exception:
        _abstain()
        return None


def transcribe_with_speech_compaction(pcm, transcribe, detect):
    if not final_pass_vad_compaction_enabled():
        return transcribe(pcm)
    compact = detect_compaction(pcm, detect)
    if compact is None:
        return transcribe(pcm)
    if not compact.spans:
        return []
    result = transcribe(compact.pcm)
    try:
        if isinstance(result, tuple):
            return (compact.map_words(result[0]), *result[1:])
        return compact.map_words(result)
    except (KeyError, TypeError, ValueError, IndexError):
        _abstain()
        return transcribe(pcm)


def diarize_with_speech_compaction(pcm, backend, detect, **kwargs):
    # Legacy resolution clocks already refer to original audio. Only the
    # pyannote HTTP adapter consumes compact audio; no Nemotron route is added.
    if not final_pass_vad_compaction_enabled() or getattr(backend, 'backend', None) != 'pyannote':
        return backend.diarize(pcm, **kwargs).model_dump()
    compact = detect_compaction(pcm, detect)
    # Existing words must never lose all speaker evidence because VAD says empty.
    if compact is None or not compact.spans:
        return backend.diarize(pcm, **kwargs).model_dump()
    output = backend.diarize(compact.pcm, **kwargs).model_dump()
    try:
        output['turns'] = compact.map_regions(output['turns'])
        output['overlaps'] = compact.map_regions(output.get('overlaps', []))
        output['provenance'] = {**output['provenance'], 'speech_compaction': 'silero-original-sample-map'}
        return output
    except (KeyError, TypeError, ValueError):
        _abstain()
        return backend.diarize(pcm, **kwargs).model_dump()
