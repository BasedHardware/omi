"""Cassette recorder: the only path by which lab audio reaches an STT vendor.

Order per miss (BRIEF audio rule, DESIGN L2/L6, red-team "reserve before every
billable attempt"):

1. look the key up; a hit costs nothing and logs nothing;
2. reserve the adapter's estimate on the spend ledger (raises over the cap,
   so no audio leaves the machine);
3. call the adapter;
4. settle: actual estimate on success, the full reservation on failure or
   uncertain completion (the audio was sent either way);
5. append one ``vendor_log.jsonl`` row (sent, even when the call failed);
6. write the cassette atomically.

Lane ``core`` owns the real USD ledger (``pipeline_lab/ledger.py``). This file
only states the three-call Protocol it needs; ``InMemoryLedger`` is the test
double and the shape the lead adapts at integration.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from testing.pipeline_lab.cassette.adapters import STTAdapter, STTRequest
from testing.pipeline_lab.cassette.format import BYTES_PER_SECOND, Cassette, CassetteKey, derive_segments, load
from testing.pipeline_lab.contracts import utc_iso as iso
from testing.pipeline_lab.ledger import SpendCapReached
from testing.pipeline_lab.store import append_jsonl


class SpendLedger(Protocol):
    def reserve(self, usd: float, *, purpose: str) -> Any:
        """Hold ``usd`` against the cap or raise; returns an opaque reservation."""

    def settle(self, reservation: Any, usd: float) -> None:
        """Replace the hold with the final charge."""


class BudgetExceeded(SpendCapReached):
    """Non-retryable: the reservation would cross the hard cap.

    A ``SpendCapReached``, so the orchestrator stops the run (exit 4) whichever ledger raised it.
    Core's persistent ``ledger.SpendLedger`` satisfies the Protocol above directly (RULINGS 9).
    """


class InMemoryLedger:
    def __init__(self, cap_usd: float):
        self.cap_usd = float(cap_usd)
        self.held: dict[int, float] = {}
        self.spent = 0.0
        self.purposes: list[str] = []
        self._next = 0

    @property
    def committed(self) -> float:
        return self.spent + sum(self.held.values())

    def reserve(self, usd: float, *, purpose: str) -> int:
        if usd < 0 or self.committed + usd > self.cap_usd + 1e-12:
            raise BudgetExceeded('STT reservation exceeds the run cap')
        self._next += 1
        self.held[self._next] = usd
        self.purposes.append(purpose)
        return self._next

    def settle(self, reservation: int, usd: float) -> None:
        self.held.pop(reservation)
        self.spent += usd


class Recorder:
    def __init__(
        self,
        adapter: STTAdapter,
        ledger: SpendLedger,
        *,
        vendor_log: str | Path,
        root: str | Path | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.adapter, self.ledger, self.root = adapter, ledger, root
        self.vendor_log = Path(vendor_log)
        self.clock = clock
        self.hits = 0
        self.misses = 0

    def key_for(self, pcm16: bytes, *, language: str | None, vocabulary: Sequence[str] = ()) -> CassetteKey:
        return CassetteKey.for_audio(
            pcm16, provider=self.adapter.provider, model=self.adapter.model, language=language, vocabulary=vocabulary
        )

    def ensure(
        self, pcm16: bytes, *, language: str | None, vocabulary: Sequence[str] = (), purpose: str = 'stt_cassette'
    ) -> Cassette:
        if not pcm16 or len(pcm16) % 2:
            raise ValueError('cassette audio must be non-empty PCM16')
        key = self.key_for(pcm16, language=language, vocabulary=vocabulary)
        existing = load(key, self.root)
        if existing is not None:
            self.hits += 1
            return existing
        self.misses += 1
        request = STTRequest(pcm16, language, tuple(vocabulary))
        estimate = float(self.adapter.estimate_usd(request))
        reservation = self.ledger.reserve(estimate, purpose=purpose)  # raises before any audio leaves
        charged = estimate
        try:
            response = self.adapter.transcribe(request)
        except BaseException:
            self.ledger.settle(reservation, charged)
            self._log(request, charged, purpose, outcome='error')
            raise
        self.ledger.settle(reservation, charged)
        self._log(request, charged, purpose, outcome='ok')
        cassette = Cassette(
            key=key,
            audio_seconds=len(pcm16) / BYTES_PER_SECOND,
            words=response.words,
            detected_language=response.detected_language,
            served_provider=response.served_provider,
            served_model=response.served_model,
            adapter=self.adapter.name,
            recorded_at=iso(datetime.fromtimestamp(self.clock(), tz=timezone.utc)),
            usd=charged,
            segments=derive_segments(response.words),
            source=getattr(self.adapter, 'source', 'vendor'),
            source_detail=getattr(self.adapter, 'source_detail', None),
        )
        cassette.save(self.root)
        return cassette

    def _log(self, request: STTRequest, usd: float, purpose: str, *, outcome: str) -> None:
        # DESIGN vendor_log row, plus the outcome. No audio, text or identity.
        append_jsonl(
            self.vendor_log,
            [
                {
                    'at': iso(datetime.fromtimestamp(self.clock(), tz=timezone.utc)),
                    'vendor': self.adapter.provider,
                    'purpose': purpose,
                    'audio_seconds': round(request.audio_seconds, 3),
                    'usd': round(usd, 6),
                    'destination': self.adapter.destination,
                    'outcome': outcome,
                }
            ],
        )
