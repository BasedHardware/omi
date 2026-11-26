"""Local speech-to-text: the interface a model on this machine implements to record ``local`` cassettes.

A local recognizer is a callable::

    recognize(pcm16: bytes, language: str | None) -> list[LocalWord | dict]

``pcm16`` is canonical 16 kHz mono PCM16LE (the cassette audio basis); ``language`` is the scenario's
language code or ``None``. Each word has ``start`` and ``end`` (seconds from the first sample), ``text``,
and ``speaker`` and ``confidence`` when the model gives them (``None`` otherwise). Nothing leaves the
machine, so recording costs nothing and the vendor log row names a local destination.

Registration, first match wins:

1. ``register_local_recorder(LocalRecorder(...))`` in the current process (tests, notebooks);
2. ``$OMI_PIPELINE_LAB_LOCAL_STT=module:factory``: ``factory()`` returns a ``LocalRecorder``. The model
   and its requirements are an optional extra installed by hand; they never enter the default install;
3. the default, ``cassette/local_parakeet.py``: production's Parakeet checkpoint on this CPU, through the
   product's decoding code, from the optional extra ``requirements-local-stt.txt`` in its own venv
   (``$OMI_PIPELINE_LAB_LOCAL_STT_PYTHON``). Without the extra it is a not-installed recorder whose call
   raises :class:`LocalRecorderNotInstalled` with the install command. No model ships with the lab.

A local cassette is evidence for everything downstream of the words, not for transcription quality.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from typing import Any, Callable, Mapping, Optional, Sequence, Union

from testing.pipeline_lab.cassette.adapters import STTRequest, STTResponse
from testing.pipeline_lab.cassette.format import Word

LOCAL_STT_ENV = 'OMI_PIPELINE_LAB_LOCAL_STT'


@dataclass(frozen=True)
class LocalWord:
    start: float
    end: float
    text: str
    speaker: Optional[str] = None
    confidence: Optional[float] = None


Recognize = Callable[[bytes, Optional[str]], Sequence[Union[LocalWord, Mapping[str, Any]]]]


class LocalRecorderNotInstalled(RuntimeError):
    """No local speech-to-text model is registered on this machine."""


@dataclass(frozen=True)
class LocalRecorder:
    """A local model: ``provider``/``model`` name its cassettes (the key), ``recognize`` does the work."""

    provider: str
    model: str
    recognize: Recognize
    installed: bool = True
    detail: Optional[Mapping[str, Any]] = None  # how the audio was cut (windows, VAD): ``Cassette.source_detail``


INSTALL_HINT = (
    'no local speech-to-text model is installed. Install one as an optional extra (it never enters the '
    'default install): put its requirements in their own file, install them into this venv, and set '
    f'{LOCAL_STT_ENV}=module:factory to a factory returning testing.pipeline_lab.cassette.local.LocalRecorder '
    '(see cassette/local.py). Or replay a committed or recorded cassette (--stt replay), or record one from '
    'a vendor (--stt record-vendor, needs credentials and --stt-budget-usd).'
)


def _not_installed(pcm16: bytes, language: Optional[str]) -> list[LocalWord]:
    raise LocalRecorderNotInstalled(INSTALL_HINT)


NOT_INSTALLED = LocalRecorder(provider='local', model='not-installed', recognize=_not_installed, installed=False)

_registered: Optional[LocalRecorder] = None


def register_local_recorder(recorder: Optional[LocalRecorder]) -> None:
    """Install ``recorder`` for this process (``None`` restores the lookup below)."""
    global _registered
    _registered = recorder


def local_recorder(windows: Optional[str] = None) -> LocalRecorder:
    """The registered recorder, else the one ``$OMI_PIPELINE_LAB_LOCAL_STT`` names, else local Parakeet
    (``windows``: ``vad`` spans, its default, or ``fixed`` 30 s windows; the other two choose their own)."""
    if _registered is not None:
        return _registered
    spec = os.environ.get(LOCAL_STT_ENV, '').strip()
    if not spec:
        from testing.pipeline_lab.cassette.local_parakeet import DEFAULT_WINDOWS, recorder

        return recorder(windows or DEFAULT_WINDOWS)
    module_name, _, attr = spec.partition(':')
    if not module_name or not attr:
        raise LocalRecorderNotInstalled(f'{LOCAL_STT_ENV} must be module:factory, not {spec!r}')
    try:
        factory = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as error:
        raise LocalRecorderNotInstalled(f'{LOCAL_STT_ENV}={spec}: {error}. {INSTALL_HINT}') from None
    recorder = factory()
    if not isinstance(recorder, LocalRecorder):
        raise LocalRecorderNotInstalled(f'{LOCAL_STT_ENV}={spec}: the factory must return a LocalRecorder')
    return recorder


def _word(item: Union[LocalWord, Mapping[str, Any]]) -> Word:
    get = item.get if isinstance(item, Mapping) else (lambda k, d=None: getattr(item, k, d))
    start, end, text = get('start'), get('end'), get('text')
    if start is None or end is None or not isinstance(text, str):
        raise ValueError('a local word needs start, end and text')
    confidence = get('confidence')
    speaker = get('speaker')
    return Word(
        float(start),
        float(end),
        text,
        None if speaker is None else str(speaker),
        None if confidence is None else float(confidence),
    )


class LocalAdapter:
    """A :class:`LocalRecorder` as a cassette ``STTAdapter``: free, no network, ``source='local'``."""

    name = 'local'
    source = 'local'

    def __init__(self, recorder: LocalRecorder):
        self.recorder = recorder
        self.provider, self.model = recorder.provider, recorder.model
        self.source_detail = dict(recorder.detail) if recorder.detail else None
        self.destination = f'local model {recorder.provider}:{recorder.model} (this machine)'

    def estimate_usd(self, request: STTRequest) -> float:
        return 0.0

    def transcribe(self, request: STTRequest) -> STTResponse:
        words = [_word(item) for item in self.recorder.recognize(request.pcm16, request.language)]
        return STTResponse(words, request.language, self.provider, self.model)
