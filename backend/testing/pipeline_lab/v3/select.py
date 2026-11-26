"""Which pipeline a run replays: the classic per-conversation chain or conversations v3.

- ``model_config.pipeline: "v3" | "classic"`` in the overlay decides outright;
- else ``v3`` when the overlay turns v3 on (``env.CONVERSATIONS_V3`` set and not ``off``, as the
  production runtime env does) **and** the corpus day has v3 recordings;
- else ``classic``.

An explicit ``v3`` on a day without recordings is refused rather than silently replaying the
classic chain.
"""

from __future__ import annotations

from typing import Any, Mapping

PIPELINES = ('classic', 'v3')
V3_ENTRY = 'testing.pipeline_lab.v3.entry'
CLASSIC_ENTRY = 'testing.pipeline_lab.chain.entry'


class PipelineRefused(ValueError):
    pass


def overlay_enables_v3(overlay: Mapping[str, Any]) -> bool:
    value = str((overlay.get('env') or {}).get('CONVERSATIONS_V3', '')).strip().lower()
    return bool(value) and value != 'off'


def select_pipeline(overlay: Mapping[str, Any], *, day_has_v3: bool) -> tuple[str, str]:
    """``(pipeline, reason)``."""
    explicit = (overlay.get('model_config') or {}).get('pipeline')
    if explicit is not None:
        if explicit not in PIPELINES:
            raise PipelineRefused(f'model_config.pipeline must be one of {PIPELINES}')
        if explicit == 'v3' and not day_has_v3:
            raise PipelineRefused('pipeline v3 needs a corpus day with v3 recordings (corpus add-day from a v3 export)')
        return explicit, 'overlay model_config.pipeline'
    if not overlay_enables_v3(overlay):
        return 'classic', 'overlay does not turn CONVERSATIONS_V3 on'
    if not day_has_v3:
        return 'classic', 'corpus day has no v3 recordings'
    return 'v3', 'overlay turns CONVERSATIONS_V3 on and the day has v3 recordings'


def entry_module(pipeline: str) -> str:
    return V3_ENTRY if pipeline == 'v3' else CLASSIC_ENTRY
