"""Best-effort observation of existing read verdicts. Never changes a reader's result.

Boolean projections are deliberately independent of lane, age and reader-specific
policy gates. Disagreements include those gates as well as contradictory legacy
state. Samples count reads, not distinct recordings; nested readers can each emit.
"""

import math
import os
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, TypeVar, cast

from prometheus_client import Counter, Histogram

from utils.conversations.phase import ConversationPhase as C, EpisodePhase as E
from utils.conversations.phase import derive_conversation_phase, derive_episode_phase
from utils.episodes.metrics import reuse_or_create

READERS = frozenset(
    {
        'home_visibility',
        'settling_hold',
        'episode_member',
        'processing_attention',
        'summary_repair',
        'batch_admission',
        'episode_composer',
    }
)
VISIBLE = frozenset({C.COMPLETE, C.SETTLED, C.DEAD_LETTER, C.FAILED})
WAITING = frozenset({C.SEALED, C.PROCESSING, C.TRANSCRIBED})
SHADOW = reuse_or_create(
    Counter,
    'omi_phase_shadow_total',
    'Legacy reader verdict agreement with derived phase',
    ['reader', 'derived_phase', 'agrees'],
)
ERRORS = reuse_or_create(
    Counter, 'omi_phase_shadow_errors_total', 'Shadow observation failures; legacy result preserved', ['reader']
)
AGE = reuse_or_create(
    Histogram,
    'omi_phase_age_seconds',
    'Observed legacy lifecycle or summary-debt age, sampled at readers',
    ['phase'],
    buckets=(30, 60, 300, 900, 1800, 3600, 7200, 14400, 86400),
)


F = TypeVar('F', bound=Callable[..., Any])


def _timestamp(value: Any) -> float | None:
    if isinstance(value, datetime):
        value = (value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)).timestamp()
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0
        else None
    )


def phase_entered_at(row: Mapping[str, Any], phase: C | E) -> float | None:
    """Use existing event timestamps only; never created_at as a guessed seal clock.

    No seal timestamp is persisted today, so sealed dwell is unavailable. For
    transcribed rows summary_first_pending_at measures summary-debt age, not
    an exact transcript-entry time (debt may predate or follow transcription).
    processing_admitted_at measures processing, including waiting for batch; a
    queued-only row uses summary_first_pending_at when available. No new reads.
    """
    fields = {
        C.CAPTURING: ('started_at',),
        C.PROCESSING: ('processing_admitted_at', 'summary_first_pending_at'),
        C.TRANSCRIBED: ('summary_first_pending_at',),
        C.COMPLETE: ('summary_completed_at',),
        C.SETTLED: ('summary_completed_at',),
        E.LIVE: ('started_at',),
        E.CLOSING: ('wrap_up_requested_at',),
        E.CLOSED: ('closed_at',),
        E.COMPOSED: ('composed_at',),
    }
    for field in fields.get(phase, ()):
        stamp = _timestamp(row.get(field))
        if stamp is not None:
            return stamp
    return None


def observe(
    reader: str,
    doc: Mapping[str, Any] | None,
    verdict: bool,
    *,
    episode: Mapping[str, Any] | None = None,
    now: float | None = None,
) -> None:
    """All shadow work, including the kill switch and metric errors, is fenced here."""
    label = reader if reader in READERS else 'other'
    try:
        if os.getenv('PHASE_SHADOW_ENABLED', 'true').strip().lower() in {'false', '0', 'off', 'no'}:
            return
        phase = derive_episode_phase(doc) if reader == 'episode_composer' else derive_conversation_phase(doc, episode)
        expected = {
            'home_visibility': phase in VISIBLE,
            'episode_member': phase in VISIBLE,
            'settling_hold': phase in WAITING,
            'processing_attention': phase in WAITING,
            'summary_repair': phase == C.TRANSCRIBED,
            'batch_admission': phase == C.SEALED,
            'episode_composer': phase == E.CLOSED,
        }.get(reader, False)
        SHADOW.labels(label, phase.value, 'true' if bool(verdict) == expected else 'false').inc()
        entered = phase_entered_at(doc, phase) if isinstance(doc, Mapping) else None
        if phase == C.SETTLED and episode is not None:
            entered = _timestamp(episode.get('composed_at'))
        if entered is not None:
            current = time.time() if now is None else now
            AGE.labels(phase.value).observe(max(0.0, current - entered))
    except Exception:
        try:
            ERRORS.labels(label).inc()
        except Exception:
            pass  # Even an unavailable collector must not affect the legacy reader.


def compare(reader: str, *, accepts: Callable[[Any], bool] = bool) -> Callable[[F], F]:
    """Observe every early return without editing the legacy predicate."""

    def decorate(fn: F) -> F:
        @wraps(fn)
        def wrapped(doc: Any, *args: Any, **kwargs: Any) -> Any:
            result = fn(doc, *args, **kwargs)
            # accepts is fixed by this module's callers, never supplied by a request.
            observe(reader, doc, accepts(result), now=kwargs.get('now'))
            return result

        return cast(F, wrapped)

    return decorate
