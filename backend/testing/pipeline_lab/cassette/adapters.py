"""STT provider adapters used by the cassette recorder.

``PrerecordedAdapter`` calls the product's prerecorded entry point
(``utils.stt.pre_recorded.prerecorded_from_bytes``), so provider selection,
language routing and vendor clients are production code under the run's env.
It is the only adapter that reaches a vendor, and the recorder only calls it
after the spend ledger reserved the estimate. ``StubAdapter`` is for tests.
"""

from __future__ import annotations

import io
import json
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, Sequence

from testing.pipeline_lab.cassette.format import BYTES_PER_SECOND, SAMPLE_RATE, Word

_PRICES = Path(__file__).resolve().parents[3] / 'scripts' / 'finops' / 'modulate_prices.json'


@dataclass(frozen=True)
class STTRequest:
    pcm16: bytes
    language: str | None
    vocabulary: tuple[str, ...] = ()

    @property
    def audio_seconds(self) -> float:
        return len(self.pcm16) / BYTES_PER_SECOND


@dataclass(frozen=True)
class STTResponse:
    words: list[Word]
    detected_language: str | None
    served_provider: str
    served_model: str


class STTAdapter(Protocol):
    name: str
    provider: str
    model: str
    destination: str

    def estimate_usd(self, request: STTRequest) -> float: ...

    def transcribe(self, request: STTRequest) -> STTResponse: ...


def pcm16_to_wav(pcm16: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm16)
    return output.getvalue()


def words_from_prerecorded(raw: Sequence[dict]) -> list[Word]:
    """Product prerecorded words are ``{timestamp: [s, e], speaker, text}``."""
    words = []
    for item in raw or []:
        start, end = item['timestamp']
        words.append(
            Word(float(start), float(end if end is not None else start), str(item['text']), item.get('speaker'))
        )
    return words


def words_to_prerecorded(words: Sequence[Word]) -> list[dict]:
    return [{'timestamp': [w.start, w.end], 'speaker': w.speaker, 'text': w.text} for w in words]


class StubAdapter:
    """Deterministic, offline. ``script(request) -> list[Word]``; default: no words."""

    name = 'stub'
    destination = 'local stub (no vendor)'

    def __init__(
        self,
        script: Callable[[STTRequest], list[Word]] | None = None,
        *,
        provider: str = 'stub',
        model: str = 'stub-1',
        usd_per_hour: float = 0.0,
        detected_language: str | None = 'en',
    ):
        self.provider, self.model = provider, model
        self.script = script or (lambda request: [])
        self.usd_per_hour = usd_per_hour
        self.detected_language = detected_language
        self.calls: list[STTRequest] = []

    def estimate_usd(self, request: STTRequest) -> float:
        return self.usd_per_hour * request.audio_seconds / 3600

    def transcribe(self, request: STTRequest) -> STTResponse:
        self.calls.append(request)
        return STTResponse(list(self.script(request)), self.detected_language, self.provider, self.model)


def modulate_card_usd(audio_seconds: float, *, with_lid: bool, prices_path: Path = _PRICES) -> float:
    """List-price estimate from the repo's finops card (micro-USD per audio hour)."""
    prices = json.loads(prices_path.read_text())
    micro = prices['batch_stt']['micro_usd_per_hour'] + (prices['lid']['micro_usd_per_hour'] if with_lid else 0)
    return micro / 1_000_000 * audio_seconds / 3600


class PrerecordedAdapter:
    """The product's prerecorded STT entry point, under the current process env.

    ``provider``/``model`` name the cassette key and must match what the run's
    overlay selects (``STT_PRERECORDED_MODEL``); the served pair the product
    reports is stored in the cassette and a mismatch is an error, so a silent
    provider fallback never files a cassette under the wrong key.
    """

    name = 'prerecorded'

    def __init__(self, *, provider: str, model: str, estimate: Callable[[STTRequest], float] | None = None):
        self.provider, self.model = provider, model
        self.destination = f'{provider}:{model} prerecorded API'
        self._estimate = estimate or (
            lambda request: modulate_card_usd(request.audio_seconds, with_lid=(request.language or 'multi') == 'multi')
        )

    def estimate_usd(self, request: STTRequest) -> float:
        return self._estimate(request)

    def transcribe(self, request: STTRequest) -> STTResponse:
        from utils.stt.pre_recorded import prerecorded_from_bytes  # lazy: no client at import time

        result, served_provider, served_model = prerecorded_from_bytes(
            pcm16_to_wav(request.pcm16),
            sample_rate=SAMPLE_RATE,
            diarize=True,
            language=request.language,
            return_language=True,
            keywords=list(request.vocabulary) or None,
            return_provider=True,
        )
        raw, detected = result if isinstance(result, tuple) else (result, None)
        served_provider, served_model = str(served_provider), str(served_model)
        if (served_provider, served_model) != (self.provider, self.model):
            raise RuntimeError('prerecorded STT served a different provider/model than the cassette key')
        return STTResponse(words_from_prerecorded(raw), detected, served_provider, served_model)
