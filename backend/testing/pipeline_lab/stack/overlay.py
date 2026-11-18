"""Run overlay: explicit env, serve-mode pins and gate pins, plus ``decisions.jsonl``.

Production picks many paths by uid cohort (``config.refactor_modes.serving_for``:
``<NAME>_SERVE_PERCENT`` buckets and ``<NAME>_SERVE_UID_SHA256S`` digests). The lab
runs as ``local-dev-user`` (DESIGN L4), which lands in different buckets, so every
cohort decision is pinned in the overlay instead:

``serving: {NAME: true}``  the lab uid joins NAME's cohort through the product's own
digest list, so ``mode`` keeps its production meaning (``shadow`` stays shadow
for everyone else; serve-for-cohort serves us).
``serving: {NAME: false}`` the cohort is emptied (percent 0, no digests).

Each pinned name is resolved once through the product's ``serving_for`` and written
to ``decisions.jsonl``. At run time every ``serving_for`` call is traced too: an
unpinned name is logged with ``source: unpinned`` and, under ``strict``, refused.

Gate pins replace usage/fair-use/funded-budget/desktop-deferral helpers with a
fixed answer so a replay is never blocked by the lab account's empty billing state.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field
import hashlib
import importlib
import json
from pathlib import Path
import threading
from typing import Any, Callable, Mapping

from testing.pipeline_lab.stack import LAB_UID
from testing.pipeline_lab.stack.io import append_jsonl
from testing.pipeline_lab.stack.patching import replace_everywhere


class UnpinnedDecision(RuntimeError):
    """A cohort decision ran that the strict overlay did not pin."""


# (module, attribute) -> pinned return value. Defaults model an entitled account
# whose processing is never deferred, held or budget-denied. Override per run.
DEFAULT_GATE_PINS: dict[str, Any] = {
    'utils.funded_processing:enabled': False,
    'utils.funded_processing:processing_allowed': True,
    'utils.subscription:should_defer_desktop_processing': False,
    'utils.subscription:should_skip_omi_paid_postprocessing': False,
    'utils.generated_compute:generated_compute_allowed': True,
}

# Env the lab always pins (DESIGN/derisk): no Cloud Tasks dispatch, no meeting
# evidence wait. Production values for the lazy-effects switch must come from
# the overlay because they changed over time.
DEFAULT_ENV: dict[str, str] = {
    'LISTEN_FINALIZATION_DISPATCH_MODE': 'inline',
    'AUDIO_MERGE_DISPATCH_MODE': 'inline',
    'MEETING_NOTES_EVIDENCE_WAIT_SECONDS': '0',
}

_COHORT_SUFFIXES = ('_SERVE_PERCENT', '_SERVE_UID_SHA256S')


def overlay_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@dataclass
class Overlay:
    env: dict[str, str] = field(default_factory=dict)
    serving: dict[str, bool] = field(default_factory=dict)
    gates: dict[str, Any] = field(default_factory=dict)
    strict: bool = False
    name: str = ''
    model_config: dict[str, Any] = field(default_factory=dict)  # resolved model choices; part of the cache key

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> 'Overlay':
        """The one overlay schema (RULINGS 7): ``{name, env, model_config, serving, gates, strict}``."""
        unknown = set(payload) - {'env', 'serving', 'gates', 'strict', 'name', 'model_config'}
        if unknown:
            raise ValueError(f'unknown overlay keys: {sorted(unknown)} (cohorts go in "serving", not "pins")')
        env = {str(k): str(v) for k, v in (payload.get('env') or {}).items()}
        serving = {str(k): bool(v) for k, v in (payload.get('serving') or {}).items()}
        for key in env:
            if key.endswith(_COHORT_SUFFIXES):
                raise ValueError(f'{key}: pin cohorts with "serving", never raw percent/digest env')
        gates = dict(payload.get('gates') or {})
        for key in gates:
            if ':' not in key:
                raise ValueError(f'gate pin {key!r} must be "module:function"')
        return cls(
            env=env,
            serving=serving,
            gates=gates,
            strict=bool(payload.get('strict')),
            name=str(payload.get('name') or ''),
            model_config=dict(payload.get('model_config') or {}),
        )

    @classmethod
    def load(cls, path: Path | None) -> 'Overlay':
        if path is None:
            return cls()
        return cls.from_mapping(json.loads(Path(path).read_text(encoding='utf-8')))

    def to_mapping(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'env': self.env,
            'model_config': self.model_config,
            'serving': self.serving,
            'gates': self.gates,
            'strict': self.strict,
        }

    def digest(self) -> str:
        return overlay_hash(self.to_mapping())

    def effective_gates(self) -> dict[str, Any]:
        return {**DEFAULT_GATE_PINS, **self.gates}

    def render_env(self, uid: str = LAB_UID) -> dict[str, str]:
        """Env for the product process: defaults, then overlay env, then cohort pins."""
        from config.refactor_modes import _COHORT_ENVS

        env = {**DEFAULT_ENV, **self.env}
        digest = hashlib.sha256(uid.encode()).hexdigest()
        for name, serves in self.serving.items():
            percent_env, digests_env = _COHORT_ENVS.get(name, (f'{name}_SERVE_PERCENT', f'{name}_SERVE_UID_SHA256S'))
            env[percent_env] = '0'
            env[digests_env] = digest if serves else ''
        return env


class DecisionLog:
    """Append-only ``decisions.jsonl``: ``{at, name, mode, source}`` plus detail fields."""

    def __init__(self, path: Path | None, *, clock: Callable[[], Any] | None = None):
        self.path = Path(path) if path is not None else None
        self.rows: list[dict] = []
        self._seen: set[tuple] = set()
        self._lock = threading.Lock()
        self._clock = clock

    def _now(self) -> str:
        from testing.pipeline_lab.stack.clock import real_now
        from testing.pipeline_lab.stack.io import iso

        return iso(self._clock() if self._clock is not None else real_now())

    def record(self, name: str, mode: Any, source: str, *, once: bool = True, **detail: Any) -> None:
        key = (name, str(mode), source, json.dumps(detail, sort_keys=True, default=str))
        with self._lock:
            if once and key in self._seen:
                return
            self._seen.add(key)
            row = {'at': self._now(), 'name': name, 'mode': mode, 'source': source, **detail}
            self.rows.append(row)
        if self.path is not None:
            append_jsonl(self.path, row)


def resolve_pins(overlay: Overlay, log: DecisionLog, *, environ: Mapping[str, str], uid: str = LAB_UID) -> None:
    """Resolve each pinned cohort through the product parser and log the outcome."""
    from config import refactor_modes

    for name in sorted(overlay.serving):
        wanted = overlay.serving[name]
        mode = refactor_modes.mode(name, environ=environ)
        served = refactor_modes.serving_for(name, uid, environ=environ)
        log.record(name, mode, 'overlay', serving=served, pinned=wanted)
        if served != wanted:
            # e.g. pinned true while the mode env is "off": the product never serves then.
            log.record(name, mode, 'overlay_conflict', serving=served, pinned=wanted)
    for key, value in sorted(overlay.env.items()):
        if key.endswith('_MODE'):
            log.record(key, refactor_modes.mode(key, environ=environ), 'overlay_env', raw=value)


def trace_serving_for(stack: ExitStack, overlay: Overlay, log: DecisionLog) -> None:
    """Wrap ``serving_for`` wherever it is bound; log each distinct runtime decision."""
    from config import refactor_modes

    original = refactor_modes.serving_for

    def traced(name: str, uid: str | None, default: Any = 'shadow', *, environ: Mapping[str, str] | None = None):
        result = original(name, uid, default, environ=environ)
        pinned = name in overlay.serving
        source = 'overlay' if pinned else 'unpinned'
        log.record(name, refactor_modes.mode(name, default, environ=environ), source, serving=result, runtime=True)
        if overlay.strict and not pinned:
            raise UnpinnedDecision(f'serve mode {name} is not pinned in the strict overlay')
        return result

    replace_everywhere(stack, original, traced)


def install_gate_pins(stack: ExitStack, overlay: Overlay, log: DecisionLog) -> dict[str, int]:
    """Replace each gate helper with its pinned answer; log every call once per value."""
    installed: dict[str, int] = {}
    for key, value in sorted(overlay.effective_gates().items()):
        module_name, _, attribute = key.partition(':')
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            log.record(key, 'missing', 'gate_pin')
            continue
        original = getattr(module, attribute, None)
        if original is None:
            log.record(key, 'missing', 'gate_pin')
            continue

        def pinned(*args, __key=key, __value=value, **kwargs):
            log.record(__key, __value, 'gate_pin', runtime=True)
            return __value

        installed[key] = replace_everywhere(stack, original, pinned)
        log.record(key, value, 'gate_pin', bound=installed[key])
    return installed
