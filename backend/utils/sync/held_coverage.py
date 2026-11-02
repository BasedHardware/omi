"""Read-only S1 proof for a held WAV, never an inference from its capture clock."""

from utils.observability.reasons import ReasonFamily, reason_label, CaptureCoverageOutcome
from dataclasses import dataclass
import wave
from typing import Any

from config import refactor_modes
from models.capture_coverage import FrameRange
from utils.capture import coverage
from utils.capture.sync_coverage import failed, key_for_claim
from utils.capture_evidence import source_coordinate


@dataclass(frozen=True)
class HeldProof:
    mapping: dict
    sample_start: int
    sample_count: int
    uncovered: tuple[tuple[int, int], ...]
    state: str


def proof(uid: str, path: str, meta: dict[str, Any]) -> HeldProof | None:
    if not refactor_modes.shadow_or_serve(coverage.FLAG):
        return None
    try:
        position = meta.get('source_position_map')
        mapping = (position[0] if position else None) if 'source_position_map' in meta else meta.get('source_frame_map')
        sample_start = position[1] if position else 0
        if not mapping:
            return None
        claim, offsets = mapping['claim'], mapping['offsets']
        if type(sample_start) is not int or sample_start < 0 or not offsets or offsets[0] != 0:
            return None
        if any(type(n) is not int for n in offsets) or any(b <= a for a, b in zip(offsets, offsets[1:])):
            return None
        with wave.open(path, 'rb') as audio:
            count = audio.getnframes()
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, claim['rate_hz']):
                return None
        start, end = source_coordinate(mapping, sample_start), source_coordinate(mapping, sample_start + count)
        if start is None or end is None or count <= 0:
            return None
        first, last = start[0], end[0] + bool(end[1])
        decision = coverage.admit(
            uid,
            key_for_claim(claim, meta.get('client_device_id'), meta.get('recording_session_id')),
            [FrameRange(start=first, end=last)],
            origin='batch' if meta.get('_batch_coverage') else 'sync',
        )
        state = 'covered' if not decision.uncovered else 'partial' if decision.covered else 'uncovered'
        kept = []
        base = claim['source_frame_start']
        for span in decision.uncovered:
            low = max(sample_start, offsets[span.start - base])
            high = min(sample_start + count, offsets[span.end - base])
            if low < high:
                kept.append((low, high))
        return HeldProof(mapping, sample_start, count, tuple(kept), state)
    except Exception as error:
        failed('held_proof', error)
        return None


def observe(decision: HeldProof, origin: str, outcome: str) -> None:
    from utils.capture.coverage_metrics import SECONDS

    seconds = (decision.sample_count - sum(high - low for low, high in decision.uncovered)) / decision.mapping['claim'][
        'rate_hz'
    ]
    if seconds > 0:
        try:
            SECONDS.labels(
                origin=origin, outcome=reason_label(ReasonFamily.HELD_CONTENT, outcome, CaptureCoverageOutcome)
            ).inc(seconds)
        except Exception:
            pass


def piece_state(uid: str, path: str, meta: dict[str, Any], context: dict[str, Any]) -> HeldProof | None:
    decision = proof(uid, path, {**meta, **context})
    if decision is None:
        return None
    if not refactor_modes.serving_for(coverage.FLAG, uid):
        observe(decision, 'sync', 'would_skip')
        return None
    if decision.state == 'uncovered':
        return None
    if decision.state == 'covered':
        observe(decision, 'sync', 'skipped')
    return decision


def covered_receipt(previous: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        **(previous or {}),
        'state': 'transcribed',
        'has_content': False,
        'seconds': 0,
        'coverage_committed': True,
        'response': {'new_memories': [], 'updated_memories': []},
    }
