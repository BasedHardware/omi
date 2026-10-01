"""Declarative live routing targets; credentials remain environment bindings."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from config.stt_provider_policy import MODULATE_SUPPORTED_LANGUAGES, STTServingSurface, parakeet_supports_language


@dataclass(frozen=True)
class Target:
    id: str
    family: str
    cost_per_audio_hour: float
    ramp_percent: float = 100
    languages: tuple[str, ...] = ()
    features: tuple[str, ...] = ('streaming',)
    endpoint: str | None = None
    capacity_env: str | None = None

    def capable(self, language: str | None, features: frozenset[str] = frozenset({'streaming'})) -> bool:
        lang = (language or 'multi').lower().split('-', 1)[0]
        if not features.issubset(self.features) or (self.languages and lang not in self.languages):
            return False
        if self.family == 'parakeet':
            return parakeet_supports_language(STTServingSurface.PRERECORDED, lang)
        if self.family == 'modulate':
            return lang in MODULATE_SUPPORTED_LANGUAGES
        return self.family == 'soniox'

    def ramp(self) -> float:
        return percent('PARAKEET_WINDOW_ALLOCATION_PERCENT', 0) if self.id == 'parakeet-window' else self.ramp_percent

    def at_capacity(self) -> bool:
        return bool(self.capacity_env and os.getenv(self.capacity_env, 'false').lower() == 'true')


def percent(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError(f'invalid {name}')
    return value


def assigned(uid: str | None, salt: str, share: float) -> bool:
    if not uid:
        return False
    bucket = int.from_bytes(hashlib.sha256(f'{salt}:{uid}'.encode()).digest()[:8], 'big')
    return bucket / 2**64 * 100 < share


def routing_on(uid: str | None) -> bool:
    return os.getenv('STT_ROUTING_MODE', 'off').lower() == 'on' and assigned(
        uid, 'stt-routing-on', percent('STT_ROUTING_ON_PERCENT', 0)
    )


DEFAULT_TARGETS = (
    Target('parakeet-window', 'parakeet', 0.02),
    Target('modulate-velma-2', 'modulate', 0.055),
    Target('soniox', 'soniox', 0.0754),
)
DEFAULT_IDS = {target.family: target.id for target in DEFAULT_TARGETS}


def registry() -> tuple[Target, ...]:
    raw = os.getenv('STT_ROUTING_TARGETS_JSON', '').strip()
    targets = tuple(Target(**entry) for entry in json.loads(raw)) if raw else DEFAULT_TARGETS
    if not 1 <= len(targets) <= 16 or len({target.id for target in targets}) != len(targets):
        raise ValueError('live STT registry must have 1-16 unique targets')
    for target in targets:
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', target.id):
            raise ValueError('invalid live STT target id')
        if (
            target.family not in DEFAULT_IDS
            or not math.isfinite(target.cost_per_audio_hour)
            or target.cost_per_audio_hour < 0
        ):
            raise ValueError('invalid live STT target family or cost')
        if not math.isfinite(target.ramp_percent) or not 0 <= target.ramp_percent <= 100:
            raise ValueError('invalid live STT ramp')
        if target.endpoint and (
            target.family != 'modulate' or not target.endpoint.startswith('wss://') or '?' in target.endpoint
        ):
            raise ValueError('endpoint must be a Modulate wss URL without query parameters')
    return targets
