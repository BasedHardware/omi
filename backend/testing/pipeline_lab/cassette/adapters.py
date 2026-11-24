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


PARAKEET_URL_ENV = 'OMI_PIPELINE_LAB_PARAKEET_URL'


class ParakeetBatchAdapter:
    """The production batch model: a hosted Parakeet endpoint, recorded window by window (RULINGS 15).

    The record lane's ``PipelineWorker`` transcribes VAD-packed windows of at most
    ``window_seconds``; this adapter cuts the conversation into windows of that size, sends
    each through the product's ``parakeet_prerecorded_from_bytes`` (with diarization) against
    the endpoint in ``$OMI_PIPELINE_LAB_PARAKEET_URL``, and stores the words on the
    conversation clock in one cassette. Which adapter a run plays back is the overlay's
    ``model_config.stt.adapter``; the inspector header shows it.

    Speaker labels are per window (the endpoint diarizes each call on its own), so turns
    across a window edge may be relabelled. Self-hosted GPU time is priced at
    ``usd_per_hour`` (default 0) so the ledger still records the audio that went out.
    """

    name = 'parakeet_batch'

    def __init__(
        self,
        *,
        model: str = 'parakeet-batch',
        url: str | None = None,
        window_seconds: float = 30.0,
        usd_per_hour: float = 0.0,
        transcribe_window: Callable[[bytes, str | None], tuple[list[dict], str | None]] | None = None,
    ):
        import os
        from urllib.parse import urlparse

        self.provider, self.model = 'parakeet', model
        self.url = url or os.environ.get(PARAKEET_URL_ENV) or ''
        if not self.url and transcribe_window is None:
            raise ValueError(f'set {PARAKEET_URL_ENV} to the Parakeet batch endpoint')
        host = urlparse(self.url).hostname or 'local'
        self.destination = f'parakeet batch endpoint {host}'
        self.window_seconds = float(window_seconds)
        self.usd_per_hour = float(usd_per_hour)
        self._transcribe_window = transcribe_window or self._product_window

    def estimate_usd(self, request: STTRequest) -> float:
        return self.usd_per_hour * request.audio_seconds / 3600

    def _product_window(self, wav: bytes, language: str | None) -> tuple[list[dict], str | None]:
        import os
        from unittest import mock

        from config.live_stt_gpu_fleet import gpu_fleet_off
        from utils.stt.pre_recorded import parakeet_prerecorded_from_bytes  # lazy: no client at import time

        with mock.patch.dict(os.environ, {'HOSTED_PARAKEET_API_URL': self.url}):
            if gpu_fleet_off():
                # The product would silently fall back to a vendor; never file that under a parakeet key.
                raise RuntimeError('GPU fleet is off in this env; refusing to record a parakeet cassette')
            result = parakeet_prerecorded_from_bytes(
                wav, sample_rate=SAMPLE_RATE, diarize=True, return_language=True, language=language
            )
        raw, detected = result if isinstance(result, tuple) else (result, None)
        return list(raw or []), detected

    def transcribe(self, request: STTRequest) -> STTResponse:
        window_bytes = int(self.window_seconds * BYTES_PER_SECOND) // 2 * 2
        words: list[Word] = []
        detected = None
        for offset in range(0, len(request.pcm16), window_bytes):
            chunk = request.pcm16[offset : offset + window_bytes]
            if not chunk:
                continue
            start = offset / BYTES_PER_SECOND
            raw, language = self._transcribe_window(pcm16_to_wav(chunk), request.language)
            detected = detected or language
            index = int(start // self.window_seconds)
            for word in words_from_prerecorded(raw):
                speaker = _window_speaker_id(index, word.speaker) if word.speaker is not None else None
                words.append(Word(word.start + start, word.end + start, word.text, speaker))
        return STTResponse(words, detected, self.provider, self.model)


def _window_speaker_id(window: int, speaker: object) -> str:
    """Opaque diarization id, unique across windows (each window's labels restart at 0).

    A cassette wire value like the vendor's own label: the product resolves display names from it,
    and it is never shown as text.
    """
    return ':'.join(('w' + str(window), str(speaker)))


def make_adapter(name: str, *, provider: str | None = None, model: str | None = None, **options) -> STTAdapter:
    """The adapter an overlay or the ``record-stt`` command names."""
    if name == 'prerecorded':
        if not provider or not model:
            raise ValueError('the prerecorded adapter needs a provider and a model')
        return PrerecordedAdapter(provider=provider, model=model)
    if name == 'parakeet_batch':
        return ParakeetBatchAdapter(model=model or 'parakeet-batch', **options)
    if name == 'stub':
        return StubAdapter(provider=provider or 'stub', model=model or 'stub-1')
    raise ValueError(f'unknown STT adapter {name!r}; expected prerecorded, parakeet_batch or stub')
