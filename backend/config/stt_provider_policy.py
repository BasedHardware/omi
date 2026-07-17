"""Authoritative serving policy for every speech-to-text provider.

This module is deliberately code-owned rather than environment-owned: changing a
provider's serving availability requires one reviewed change here. Deployment
manifests may choose ordering, but cannot reactivate a provider absent from this
policy. Add a provider to selected surfaces below only after its credentials,
traffic contract, and regression coverage are ready.
"""

from __future__ import annotations

from enum import Enum
from typing import Final, Mapping


class STTServingSurface(str, Enum):
    STREAMING = 'streaming'
    PRERECORDED = 'prerecorded'
    PTT = 'ptt'


DEEPGRAM_PROVIDER: Final = 'deepgram'
MODULATE_PROVIDER: Final = 'modulate'
PARAKEET_PROVIDER: Final = 'parakeet'

# This is the single source of truth for provider enablement. Deepgram is
# intentionally absent from every serving surface. Future availability changes
# start here: enable all audited surfaces for a global switch, or only the
# intended surfaces for granular rollout, after provider wiring is ready.
PROVIDER_SERVING_SURFACES: Final[Mapping[str, frozenset[STTServingSurface]]] = {
    DEEPGRAM_PROVIDER: frozenset(),
    MODULATE_PROVIDER: frozenset(
        {
            STTServingSurface.STREAMING,
            STTServingSurface.PRERECORDED,
            STTServingSurface.PTT,
        }
    ),
    PARAKEET_PROVIDER: frozenset(
        {
            STTServingSurface.STREAMING,
            STTServingSurface.PRERECORDED,
            STTServingSurface.PTT,
        }
    ),
}

# Defaults are also policy-owned so a deployment fallback cannot drift from the
# providers approved above. A deployment's literal ordering is checked against
# these values by validate-backend-runtime-env.py.
DEFAULT_MODELS_BY_SURFACE: Final[Mapping[STTServingSurface, tuple[str, ...]]] = {
    STTServingSurface.STREAMING: ('parakeet', 'modulate-velma-2'),
    STTServingSurface.PRERECORDED: ('parakeet', 'modulate-velma-2'),
    STTServingSurface.PTT: ('parakeet', 'modulate-velma-2'),
}


def provider_for_model_token(model: str) -> str | None:
    """Return the provider owning a known model token, including retired tokens."""
    normalized = model.strip().lower()
    if normalized == 'parakeet':
        return PARAKEET_PROVIDER
    if normalized == 'modulate-velma-2':
        return MODULATE_PROVIDER
    if normalized in {'deepgram', 'nova-2', 'nova-3', 'dg-nova-2', 'dg-nova-3'}:
        return DEEPGRAM_PROVIDER
    return None


def provider_is_enabled(provider: str, surface: STTServingSurface) -> bool:
    """Return whether a provider may serve the specified product surface."""
    return surface in PROVIDER_SERVING_SURFACES.get(provider, frozenset())


def model_is_enabled(model: str, surface: STTServingSurface) -> bool:
    provider = provider_for_model_token(model)
    return provider is not None and provider_is_enabled(provider, surface)


def default_models_for_surface(surface: STTServingSurface) -> tuple[str, ...]:
    """Return the canonical model ordering for one serving surface."""
    return tuple(model for model in DEFAULT_MODELS_BY_SURFACE[surface] if model_is_enabled(model, surface))


def canonical_model_config(surface: STTServingSurface) -> str:
    """Return the deployment-safe comma-separated model preference."""
    return ','.join(default_models_for_surface(surface))
