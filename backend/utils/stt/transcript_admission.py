"""One deterministic hallucination admission policy for live and sync transcripts.

Audit receipts contain rule/version, source and a hash of the segment identity and
span, never text, account identity, or speaker identity. Shadow changes no segment.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal, Sequence, TypeVar

from config.refactor_modes import serving_for, shadow_or_serve
from utils.conversations.relevance_content import FLAG, value
from utils.conversations.relevance_media_metrics import observe

logger = logging.getLogger(__name__)
VERSION = 1
Origin = Literal['live', 'sync']
T = TypeVar('T')
_BLOCKLIST = frozenset(('[blank_audio]', '[silence]', '[no speech]', '(silence)', '[music]'))
_CREDITS = re.compile(
    r'^(?:caption\s+credit\s+for|(?:subtitles?|captions?)\s+(?:by|provided by|created by)|'
    r'subtitl(?:es|ing)\s+(?:and|&)\s+(?:translat(?:ion|ed)|captions?)\s+by)\s+[^.!?。！？]{1,100}[.!?。！？]?$',
    re.I,
)
_SENTENCES = re.compile(r'[.!?。！？]+')


@dataclass(frozen=True)
class AdmissionReceipt:
    fingerprint: str
    rule: str
    origin: Origin
    dropped: bool
    version: int = VERSION


def hallucination_rule(segment: Any) -> str | None:
    text = ' '.join(unicodedata.normalize('NFKC', str(value(segment, 'text', '') or '')).split())
    if text.casefold() in _BLOCKLIST:
        return 'silence_marker'
    if _CREDITS.fullmatch(text):
        return 'subtitle_credit'
    # Protect known owner speech. A foreign language by itself is never noise.
    if value(segment, 'is_user', False):
        return None
    sentences = [s.strip().casefold() for s in _SENTENCES.split(text) if s.strip()]
    if len(sentences) >= 3 and len(set(sentences)) == 1 and len(sentences[0]) >= 6:
        if any(c.isalpha() and not c.isascii() for c in sentences[0]):
            return 'repeated_sentence'
    return None


@dataclass
class AdmissionState:
    """Session-local repetition evidence; retains only a digest and bounded scalars."""

    signature: str | None = None
    count: int = 0
    previous_end: float | None = None
    previous_id: str | None = None

    def repeated(self, segment: Any) -> bool:
        text = ' '.join(unicodedata.normalize('NFKC', str(value(segment, 'text', '') or '')).casefold().split())
        sentences = [s.strip() for s in _SENTENCES.split(text) if s.strip()]
        start, end = value(segment, 'start'), value(segment, 'end')
        usable = (
            not value(segment, 'is_user', False)
            and len(sentences) == 1
            and len(sentences[0]) >= 6
            and any(c.isalpha() and not c.isascii() for c in text)
            and isinstance(start, (int, float))
            and isinstance(end, (int, float))
            and math.isfinite(start)
            and math.isfinite(end)
            and end >= start
        )
        if not usable:
            self.signature, self.count, self.previous_end, self.previous_id = None, 0, None, None
            return False
        signature = hashlib.sha256(sentences[0].encode()).hexdigest()
        segment_id = value(segment, 'id')
        if segment_id and segment_id == self.previous_id:
            return self.count >= 3 and signature == self.signature
        contiguous = self.previous_end is not None and 0 <= start - self.previous_end <= 10
        self.count = min(3, self.count + 1) if contiguous and self.signature == signature else 1
        self.signature, self.previous_end, self.previous_id = signature, end, segment_id
        return self.count >= 3


def filter_admission(
    uid: str, segments: Sequence[T], *, origin: Origin, state: AdmissionState | None = None
) -> tuple[list[T], list[AdmissionReceipt]]:
    if not shadow_or_serve(FLAG):
        return list(segments), []
    serve = serving_for(FLAG, uid)
    state = state if state is not None else AdmissionState()
    admitted, receipts = [], []
    for segment in segments:
        repeated = state.repeated(segment)
        rule = hallucination_rule(segment) or ('repeated_sentence_run' if repeated else None)
        if rule is None:
            admitted.append(segment)
            continue
        identity = ':'.join(str(value(segment, name, '')) for name in ('id', 'start', 'end'))
        receipt = AdmissionReceipt(hashlib.sha256(f'{origin}:{identity}'.encode()).hexdigest(), rule, origin, serve)
        receipts.append(receipt)
        if not serve:
            admitted.append(segment)
        else:
            logger.info(
                'event=transcript_admission version=%s origin=%s rule=%s dropped=true receipt=%s',
                VERSION,
                origin,
                rule,
                receipt.fingerprint,
            )
    observe(f'admission_{origin}', 'disagree' if receipts else 'agree')
    return admitted, receipts


def admit_segments(uid: str, segments: Sequence[T], *, origin: Origin, state: AdmissionState | None = None) -> list[T]:
    return filter_admission(uid, segments, origin=origin, state=state)[0]
