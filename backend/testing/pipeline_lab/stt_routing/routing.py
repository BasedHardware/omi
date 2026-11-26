"""Batch STT routing as a lab step: which engine production would send each audio recording to.

Without this step the lab plays whatever cassette the scenario pins, so two arms that route differently
(a kill switch on and off) transcribe identically. With it, each ``audio_file`` recording is routed by the
product's own decisions, under the arm's env, and its words come from the cassette of the engine chosen:

| Step | Here | Production code? |
|---|---|---|
| Admission language / exclusion | ``config.batch_pipeline_language.batch_admission_language`` | yes |
| Exclusion and sampling switches | ``admission_language_exclusion_enabled``, ``admission_language_sample_enabled`` | yes |
| Sampled upload limit | ``intake.SAMPLE_SCAN_SECONDS``: a longer upload is refused to legacy | yes |
| Sampled speech windows | ``intake._speech_windows`` (strict local VAD, 30 s windows) | yes |
| Sampled first window | vendor audio LID, ``LanguageDecision.parakeet_safe`` and ``evidence == 'audio_lid'`` | yes; answer recorded |
| Sampled later windows | ``language_class`` of the self gate's top-1 language | yes; answer from a local Whisper-base, recorded |
| Engine for an admitted upload | the batch GPU worker: Parakeet (``PARAKEET_MODEL_BY_SURFACE[PRERECORDED]``) | yes (by construction) |
| Engine for a legacy upload | per file: vendor LID, then ``get_prerecorded_service`` (``resolve_file``) | yes; files simulated as fixed pieces |
| Capacity fallback (GPU ring saturated) | not run: the batch lane is assumed unsaturated | simulated |
| Legacy mode | assumed ``on`` (today's production) | simulated |

Inputs are private: ``$OMI_PIPELINE_LAB_STT_ROUTING_INPUTS`` names a JSON file outside Git,
``{"user": {...}, "conversations": {"<label>": {...}}, "default_conversation": {...}}``: the owner's user
document fields routing reads (``language``, ``transcription_preferences``, ``live_stt_language_sessions``)
and each recording's conversation fields (``language``). Enable with ``OMI_PIPELINE_LAB_STT_ROUTING=product``
in the scenario or arm env. ``$OMI_PIPELINE_LAB_STT_ROUTE_CASSETTES`` (JSON) maps each route to the cassette
pin that stands in for it, e.g. ``{"parakeet": {"provider": "local", "model": "..."}}``; a route without a
mapping uses the provider and model production selected.
"""

from __future__ import annotations

import contextlib
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional

ROUTING_ENV = 'OMI_PIPELINE_LAB_STT_ROUTING'
INPUTS_ENV = 'OMI_PIPELINE_LAB_STT_ROUTING_INPUTS'
CASSETTES_ENV = 'OMI_PIPELINE_LAB_STT_ROUTE_CASSETTES'
LID_SECRET_FILE_ENV = 'OMI_PIPELINE_LAB_LID_KEY_FILE'  # 0600 file holding the vendor LID key (record only)
SELF_LID_PYTHON_ENV = 'OMI_PIPELINE_LAB_MLX_PYTHON'  # venv with mlx-whisper: the self gate's local stand-in
LEGACY_FILE_SECONDS_ENV = 'OMI_PIPELINE_LAB_LEGACY_FILE_SECONDS'
LEGACY_FILE_SECONDS = 60.0  # legacy sync probes each uploaded file; the lab cuts a recording into pieces this long
LAB_ENV_KEYS = (
    ROUTING_ENV,
    INPUTS_ENV,
    CASSETTES_ENV,
    LID_SECRET_FILE_ENV,
    SELF_LID_PYTHON_ENV,
    LEGACY_FILE_SECONDS_ENV,
)

PARAKEET = 'parakeet'
MULTILINGUAL = 'multilingual'
MIXED = 'mixed'  # a legacy upload whose files went to different engines


class RoutingError(RuntimeError):
    """Routing cannot decide a recording's engine; the message is the scenario's error (no transcript text)."""


@dataclass(frozen=True)
class Route:
    route: str  # parakeet | multilingual | mixed
    reason: str  # admitted_pinned | sampled:admitted | sampled:<refusal> -> legacy | legacy:<reason> | exclusion_off
    provider: str
    model: str
    language: str  # the cassette key language: what production sends the engine
    admission_language: Optional[str] = None
    lid_language: Optional[str] = None
    lid_confidence: Optional[float] = None
    lid_seconds: Optional[float] = None
    self_lid_windows: Optional[int] = None
    pieces: Optional[tuple[tuple[float, float, str], ...]] = None  # legacy: (start, end, route) per file

    def summary(self) -> dict[str, Any]:
        out = {k: v for k, v in asdict(self).items() if v is not None and k != 'pieces'}
        if self.pieces:
            out['pieces'] = [[round(a, 3), round(b, 3), r] for a, b, r in self.pieces]
        return out


def enabled(env: Mapping[str, str]) -> bool:
    return (env.get(ROUTING_ENV) or '').strip().lower() == 'product'


@contextlib.contextmanager
def patched_environ(env: Mapping[str, str]) -> Iterator[None]:
    """The product's switches read ``os.environ`` at call time: route under the arm's env, then restore."""
    product = {k: v for k, v in env.items() if k not in LAB_ENV_KEYS}
    previous = {k: os.environ.get(k) for k in product}
    os.environ.update(product)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# ---- inputs ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Inputs:
    user: Mapping[str, Any]
    conversations: Mapping[str, Mapping[str, Any]]
    default_conversation: Mapping[str, Any]

    def conversation(self, label: str) -> Mapping[str, Any]:
        return self.conversations.get(label) or self.default_conversation

    @classmethod
    def load(cls, env: Mapping[str, str]) -> 'Inputs':
        path = env.get(INPUTS_ENV)
        if not path:
            raise RoutingError(f'{ROUTING_ENV}=product needs {INPUTS_ENV}: a private JSON file of routing inputs')
        raw = json.loads(Path(path).expanduser().read_text(encoding='utf-8'))
        if not isinstance(raw, dict) or not isinstance(raw.get('user'), dict):
            raise RoutingError(f'{INPUTS_ENV}: {{"user": {{...}}, "conversations": {{...}}}}')
        return cls(raw['user'], raw.get('conversations') or {}, raw.get('default_conversation') or {})


def route_cassettes(env: Mapping[str, str]) -> dict[str, dict[str, str]]:
    raw = env.get(CASSETTES_ENV)
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RoutingError(f'{CASSETTES_ENV}: {{"parakeet": {{"provider", "model"}}, "multilingual": {{...}}}}')
    return {str(k): dict(v) for k, v in value.items()}


# ---- LID: the sampled probe, recorded once per probe audio ----------------------------------------


def _probe(pcm16: bytes) -> tuple[bytes, float]:
    from testing.pipeline_lab.cassette.adapters import pcm16_to_wav
    from utils.stt.batch_language import probe_wav

    return probe_wav(pcm16_to_wav(pcm16))


def lid_probe_usd(seconds: float) -> float:
    """List price of one vendor LID probe, from the repo's finops card (``modulate_prices.json``)."""
    from testing.pipeline_lab.cassette.adapters import _PRICES

    micro = json.loads(Path(_PRICES).read_text(encoding='utf-8'))['lid']['micro_usd_per_hour']
    return micro / 1_000_000 * float(seconds) / 3600


class LidCache:
    """``<root>/lid/<sha256 of the probe WAV>.json``: the vendor's answer for one 30 s probe (owner-only)."""

    def __init__(self, root: Path, *, record: bool, secret_file: Optional[str] = None, ledger: Any = None):
        self.directory = Path(root) / 'lid'
        self.record = record
        self.secret_file = secret_file
        self.ledger = ledger  # a SpendGuard: every recorded probe reserves and settles its list price
        self.calls = 0

    def decision(self, pcm16: bytes):
        from utils.stt.batch_language import LanguageDecision

        body, seconds = _probe(pcm16)
        digest = hashlib.sha256(body).hexdigest()
        path = self.directory / f'{digest}.json'
        if path.exists():
            row = json.loads(path.read_text(encoding='utf-8'))
        elif not self.record:
            raise RoutingError(
                f'no recorded LID answer for probe {digest[:12]}; record it with --stt record-vendor '
                f'and {LID_SECRET_FILE_ENV} set (one paid 30 s probe per upload)'
            )
        else:
            if self.ledger is None:
                raise RoutingError('recording a LID answer needs --stt-budget-usd (the spend cap for probes)')
            usd = lid_probe_usd(seconds)
            reservation = self.ledger.reserve(usd, purpose='stt_routing:lid_probe')
            try:
                row = self._detect(body)
            except BaseException:
                self.ledger.release(reservation)
                raise
            self.ledger.settle(reservation, usd)
            from testing.pipeline_lab.store import private_write_text

            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            private_write_text(path, json.dumps(row))
            self.calls += 1
        return LanguageDecision(row['language'], float(row['confidence']), row['evidence'], seconds)

    def _detect(self, body: bytes) -> dict[str, Any]:
        from utils.stt import batch_language

        if not self.secret_file:
            raise RoutingError(f'recording a LID answer needs {LID_SECRET_FILE_ENV} (a 0600 key file)')
        key = Path(self.secret_file).read_text(encoding='utf-8').strip()
        previous = os.environ.get('MODULATE_API_KEY')
        os.environ['MODULATE_API_KEY'] = key  # this process only, for this one call
        try:
            outcomes: list[str] = []
            decision = batch_language.detect(body, outcome_sink=outcomes)
        finally:
            if previous is None:
                os.environ.pop('MODULATE_API_KEY', None)
            else:
                os.environ['MODULATE_API_KEY'] = previous
        if not outcomes or outcomes[0] != 'accepted':
            raise RoutingError(f'LID probe failed: {outcomes[0] if outcomes else "no outcome"}')
        return {'language': decision.language, 'confidence': decision.confidence, 'evidence': decision.evidence}


class PendingSelfLid(Exception):
    """A record run has not classified this window yet: it is queued for one batched local pass."""


class SelfLidCache:
    """``<root>/self_lid/<sha256 of the window WAV>.json``: the local self-gate stand-in's top-1 language.

    A record run queues misses (``pending``) and classifies them in one batched pass (:meth:`flush`), since
    loading Whisper per window would dominate; replay refuses a miss."""

    def __init__(self, root: Path, *, record: bool, python: Optional[str] = None):
        self.directory = Path(root) / 'self_lid'
        self.record = record
        self.python = python
        self.pending: dict[str, bytes] = {}
        self.calls = 0

    def language(self, wav: bytes) -> str:
        digest = hashlib.sha256(wav).hexdigest()
        path = self.directory / f'{digest}.json'
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))['language']
        if not self.record:
            raise RoutingError(
                f'no recorded self-gate answer for window {digest[:12]}; record with --stt record-vendor and '
                f'{SELF_LID_PYTHON_ENV} (a venv with mlx-whisper)'
            )
        self.pending[digest] = wav
        raise PendingSelfLid(digest)

    def flush(self) -> int:
        if not self.pending:
            return 0
        if not self.python:
            raise RoutingError(f'classifying self-gate windows needs {SELF_LID_PYTHON_ENV}')
        import subprocess
        import tempfile

        from testing.pipeline_lab.store import private_write_text

        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.directory) as work:
            paths = {}
            for digest, wav in self.pending.items():
                target = Path(work) / f'{digest}.wav'
                target.write_bytes(wav)
                target.chmod(0o600)
                paths[str(target)] = digest
            listing, result = Path(work) / 'in.json', Path(work) / 'out.json'
            listing.write_text(json.dumps(list(paths)))
            backend = Path(__file__).resolve().parents[3]
            subprocess.run(
                [
                    self.python,
                    '-m',
                    'testing.pipeline_lab.stt_routing.self_lid',
                    '--in',
                    str(listing),
                    '--out',
                    str(result),
                ],
                cwd=backend,
                check=True,
            )
            for row in json.loads(result.read_text(encoding='utf-8')):
                private_write_text(
                    self.directory / f'{paths[row["path"]]}.json', json.dumps({'language': row['language']})
                )
        count = len(self.pending)
        self.calls += count
        self.pending.clear()
        return count


# ---- the decision ---------------------------------------------------------------------------------


def _batch(language: str) -> tuple[str, str, str]:
    """An upload admitted to the batch pipeline is transcribed by its GPU worker: Parakeet, in that language."""
    from config.stt_provider_policy import PARAKEET_MODEL_BY_SURFACE, STTServingSurface

    return PARAKEET, PARAKEET_MODEL_BY_SURFACE[STTServingSurface.PRERECORDED], language


def _service(language: str) -> tuple[str, str, str]:
    from utils.stt.pre_recorded import get_prerecorded_service

    service, provider_language, model = get_prerecorded_service(language)
    return str(getattr(service, 'value', service)), model, provider_language or language


def _route_of(service: str) -> str:
    return PARAKEET if PARAKEET in service.lower() else MULTILINGUAL


def _wav_pcm(wav: bytes) -> bytes:
    import io
    import wave

    with wave.open(io.BytesIO(wav), 'rb') as source:
        return source.readframes(source.getnframes())


def _sample(pcm16: bytes, *, lid: Callable[[bytes], Any], self_lid: Optional[Callable[[bytes], str]]):
    """Intake's ``_sample_language_units`` on one upload.

    Returns (admitted, refusal reason, first-window decision, later windows the self gate classified)."""
    from config.prerecorded_language import language_class
    from testing.pipeline_lab.cassette.adapters import pcm16_to_wav
    from utils.batch_pipeline.intake import SAMPLE_SCAN_SECONDS, _speech_windows

    if len(pcm16) / 32000 > SAMPLE_SCAN_SECONDS:
        return False, 'over_scan_limit', None, 0
    windows = _speech_windows(pcm16_to_wav(pcm16))
    if not windows:
        return False, 'no_speech', None, 0
    first = lid(_wav_pcm(windows[0]))
    if not first.parakeet_safe or first.evidence != 'audio_lid':
        return False, 'first_window_unsafe', first, 0
    if self_lid is None:
        raise RoutingError('the sampled path needs the self-gate stand-in for windows after the first')
    pending = False
    classified = 0
    for window in windows[1:]:
        try:
            language = self_lid(window)
        except PendingSelfLid:
            pending = True
            continue
        classified += 1
        if language_class(language) != 'supported':
            return False, 'later_window_unsupported', first, classified
    if pending:
        raise PendingSelfLid('windows queued')
    return True, None, first, classified


def _legacy(pcm16: bytes, reason: str, *, lid: Callable[[bytes], Any], file_seconds: float) -> 'Route':
    """Legacy sync: ``multi`` through ``resolve_file`` for each uploaded file (simulated as fixed pieces)."""
    step = max(1, int(file_seconds * 16000)) * 2
    pieces = []
    engines = []  # (route, service, model, sent) per file, in file order
    for offset in range(0, len(pcm16), step):
        chunk = pcm16[offset : offset + step]
        if len(chunk) < 32000 and pieces:  # a sub-second tail joins the previous file's engine
            a, _, r = pieces[-1]
            pieces[-1] = (a, (offset + len(chunk)) / 32000, r)
            continue
        decision = lid(chunk)
        service, model, sent = _service(decision.language) if decision.parakeet_safe else _service('multi')
        route = _route_of(service)
        engines.append((route, service, model, sent))
        pieces.append((offset / 32000, (offset + len(chunk)) / 32000, route))
    if not pieces:
        raise RoutingError('the upload has no audio to route')
    routes = {r for _, _, r in pieces}
    if len(routes) == 1:
        # The first file's engine and language: deterministic across runs, unlike a set's order.
        route, service, model, sent = engines[0]
        return Route(route, f'legacy:{reason}', service, model, sent, pieces=tuple(pieces))
    service, model, sent = _service('multi')
    return Route(MIXED, f'legacy:{reason}', service, model, sent, pieces=tuple(pieces))


def decide(
    user: Mapping[str, Any],
    conversation: Mapping[str, Any],
    pcm16: bytes,
    *,
    lid: Callable[[bytes], Any],
    self_lid: Optional[Callable[[bytes], str]] = None,
    legacy_file_seconds: float = LEGACY_FILE_SECONDS,
) -> Route:
    """Production's batch route for one upload (intake route selection with legacy ``on``).

    Admitted (a supported pin) -> the Parakeet batch worker. ``unknown_multilingual_conversation`` with
    sampling on -> intake's sampled classification of the whole upload; admitted -> Parakeet, refused ->
    legacy. Any other exclusion, or a refused sample -> legacy sync, which classifies each file."""
    from config.batch_pipeline_language import (
        MULTILINGUAL_PROFILE,
        admission_language_exclusion_enabled,
        admission_language_sample_enabled,
        batch_admission_language,
    )

    if not admission_language_exclusion_enabled():
        language = str(conversation.get('language') or user.get('language') or 'multi')
        service, model, sent = _batch(language)
        return Route(PARAKEET, 'exclusion_off', service, model, sent, admission_language=language)
    admission, reason = batch_admission_language(dict(user), dict(conversation))
    if reason is None:
        service, model, sent = _batch(admission)
        return Route(PARAKEET, 'admitted_pinned', service, model, sent, admission_language=admission)
    if reason in ('unknown_multilingual_conversation', MULTILINGUAL_PROFILE) and admission_language_sample_enabled():
        admitted, refusal, first, windows = _sample(pcm16, lid=lid, self_lid=self_lid)
        lid_fields = {'self_lid_windows': windows}
        if first is not None:
            lid_fields.update(
                lid_language=first.language,
                lid_confidence=round(float(first.confidence), 4),
                lid_seconds=round(float(first.probe_seconds or 0.0), 3),
            )
        if admitted:
            service, model, sent = _batch(first.language)
            return Route(PARAKEET, 'sampled:admitted', service, model, sent, **lid_fields)
        legacy = _legacy(pcm16, f'sampled_{refusal}', lid=lid, file_seconds=legacy_file_seconds)
        return Route(**{**asdict(legacy), **lid_fields, 'pieces': legacy.pieces})
    return _legacy(pcm16, reason, lid=lid, file_seconds=legacy_file_seconds)


def cassette_pin(route: Route, mapping: Mapping[str, Mapping[str, str]], which: Optional[str] = None) -> dict[str, str]:
    """The cassette keys that stand in for a route (``which`` picks one engine of a mixed route).

    Only keys that resolve are returned, so an unmapped engine of a mixed route keeps the scenario's own pin
    (and misses loudly) instead of becoming a wildcard that matches another engine's cassette."""
    name = which or route.route
    pin = dict(mapping.get(name) or {})
    if name == route.route:
        pin.setdefault('provider', route.provider)
        pin.setdefault('model', route.model)
        pin.setdefault('language', route.language)
    else:
        pin.setdefault('language', 'multi' if name == MULTILINGUAL else 'en')
    return {key: str(value) for key, value in pin.items() if key in ('provider', 'model', 'language') and value}
