# LIFECYCLE: permanent
"""Runtime ramp percents and the legacy-sync mode, read from ``rollout_cohorts/_ramp`` (contracts (f), (h)).

Signatures only (lane 1 stub); lane 6 implements. Semantics fixed by the contract:

- one process-wide cache entry, TTL 30s, read off the event loop with a 1s timeout and SDK retries off;
- on read error or a malformed document serve last-known-good indefinitely (``source="lkg"``), never higher
  than LKG; a cold start with no LKG returns ``env_default`` (``source="env_default"``);
- values outside [0, 100] or non-finite are malformed;
- ``batch-live-stt-retire`` is clamped at read time to <= ``batch-pipeline``;
- the environment key is ``OMI_DEPLOYMENT`` when set (``staging``), else ``rollout_environment()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

RAMP_NAMES = ('batch-pipeline', 'first-summary', 'batch-live-stt-retire')
RAMP_DOC_ID = '_ramp'

LegacySyncMode = Literal['on', 'draining', 'dark']


@dataclass(frozen=True)
class RampSnapshot:
    revision: int
    percents: Mapping[str, float]
    legacy_sync: LegacySyncMode
    locked_by: str | None
    source: Literal['firestore', 'lkg', 'env_default']


def runtime_percent(name: str, *, env_default: float) -> float:
    raise NotImplementedError('runtime_percent: lane 6')


def legacy_sync_mode() -> LegacySyncMode:
    raise NotImplementedError('legacy_sync_mode: lane 6')


def ramp_snapshot() -> RampSnapshot:
    raise NotImplementedError('ramp_snapshot: lane 6')


def write_ramp(env: str, change: Mapping[str, Any], *, expected_revision: int, actor: str, reason: str) -> int:
    """CAS on revision; writes ``_ramp/history`` in the same transaction. Controller and operator CLI only."""
    raise NotImplementedError('write_ramp: lane 6')
